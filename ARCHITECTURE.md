# Browser Harness Architecture

**Purpose:** A minimal, robust testing engine built on Chrome DevTools Protocol (CDP). Drives a real Chrome browser in developer mode via WebSocket, exposing a thin Python API for UI/E2E testing.

**Design philosophy:** Transparent mapping. Every function is a direct, traceable path to one CDP command. No business logic, no state machines, no retry loops — just the shortest path from Python call to browser action.

**Scope:** Testing workflow only. The harness runs tests, captures failures, and optionally self-heals broken selectors/assertions via an AI agent layer. No production traffic, no live app monitoring.

---

## Architecture Overview

```
Chrome (dev mode, port 9222)
    └── WebSocket (ws://127.0.0.1:9222/devtools/...)
            │
            ▼
    ┌───────────────────┐
    │  Bridge (daemon)  │  ← asyncio WebSocket client + Unix socket server
    │   daemon.py       │    One process. Handles session lifecycle.
    └─────────┬─────────┘
              │ Unix socket (/tmp/bu-<NAME>.sock)
              │ JSON lines — one request per line
              ▼
    ┌───────────────────┐
    │  Core Helpers     │  ← Thin wrappers: goto_url, click, js, screenshot
    │  helpers.py       │    One function = one CDP command. No logic.
    └─────────┬─────────┘
              │
    ┌─────────┴─────────┐
    │  UI Helpers       │  ← DOM-centric: find_element, wait, is_visible, text
    │  harness/helpers  │
    └─────────┬─────────┘
              │
    ┌─────────┴─────────┐
    │  Assertions       │  ← Test language: assert_visible, assert_text, etc.
    │  harness/assert   │    Screenshot on failure. No retry. Fail fast.
    └─────────┬─────────┘
              │
    ┌─────────┴─────────┐
    │  Test Runner      │  ← discovers test_*.py files, runs, reports
    │  harness/runner   │
    └─────────┬─────────┘
              │
    ┌─────────┴─────────┐
    │  Agent (optional) │  ← AppModel, TestAuthor, SelfHealer, CIManager
    │  agent/           │    AI layer on top. Harness works without this.
    │                    │    Learns patterns across test runs.
    └───────────────────┘
```

**Key properties:**
- Each layer depends only on the layer directly below it.
- The agent layer is optional — the harness works standalone without any AI components.
- `domain-skills/` and `interaction-skills/` are generated at runtime by the agent and stored under `browser_harness/` for reuse by future test runs on the same domain.

---

## Component 1: Chrome in Developer Mode

### What
A Chrome browser running with `--remote-debugging-port=9222`. This opens a WebSocket server that exposes the Chrome DevTools Protocol (CDP).

### Profile Isolation — One Profile Per Test Workflow

Every test workflow gets its own Chrome profile (a directory on disk) so that:
- Logins, cookies, and session state are isolated between workflows
- A test failure in one workflow does not affect another
- You can run tests against a "logged-in" state by pointing at a pre-authenticated profile

#### Launch options

**macOS:**
```bash
open -a "Google Chrome" --args --remote-debugging-port=9222 \
  --user-data-dir="$HOME/Library/Application Support/Google/Chrome/Profile 1"
```

**Linux (system Chrome):**
```bash
google-chrome --remote-debugging-port=9222 \
  --user-data-dir="$HOME/.config/chrome-test-profile"
```

**Linux (Chromium):**
```bash
chromium-browser --remote-debugging-port=9222 \
  --user-data-dir="$HOME/.config/chromium-test-profile"
```

**Windows:**
```powershell
chrome.exe --remote-debugging-port=9222 `
  --user-data-dir="$env:LOCALAPPDATA\Google\Chrome\User Data\TestProfile"
```

Each invocation creates or reuses a named profile directory. Change `--user-data-dir` to switch profiles.

#### Profile path convention

Each daemon instance is identified by `BU_NAME` (default: `default`). The daemon socket, PID, and log files are namespaced:
```
/tmp/bu-<NAME>.sock   ← Unix socket
/tmp/bu-<NAME>.pid    ← daemon PID
/tmp/bu-<NAME>.log    ← daemon log
```

The `BU_NAME` does **not** automatically select a Chrome profile — you pick the profile by how you launch Chrome. The daemon discovers Chrome by scanning the standard profile locations and reading `DevToolsActivePort` from whichever one is currently running with `--remote-debugging-port`.

**Practical pattern for isolated workflows:**

```bash
# Workflow 1: Chrome with its own profile, daemon with its own socket
google-chrome --remote-debugging-port=9222 \
  --user-data-dir="$HOME/.config/chrome-workflow-a"
BU_NAME=workflow-a browser-harness

# Workflow 2: Different Chrome profile, different daemon name
google-chrome --remote-debugging-port=9223 \
  --user-data-dir="$HOME/.config/chrome-workflow-b"
BU_NAME=workflow-b browser-harness
```

Each workflow needs its own `--remote-debugging-port` since each Chrome instance must have a unique port. `BU_NAME` isolates the daemon socket/PID, not the browser profile itself.

#### Naming your daemon

Set `BU_NAME` in `.env` or as an environment variable:

```bash
BU_NAME=sap-build browser-harness
# Daemon socket: /tmp/bu-sap-build.sock
# Chrome profile: ~/.config/google-chrome-sap-build
```

This gives you one isolated daemon + one isolated Chrome profile per name. Multiple `BU_NAME` values can run simultaneously on different ports (each Chrome instance needs its own `--remote-debugging-port`).

### How Chrome's CDP WebSocket is Discovered

Chrome writes a `DevToolsActivePort` file in its profile directory containing:
```
<port>\n<path>
```
Example: `9222\n/devtools/browser/abc123-456`

The WebSocket URL is then `ws://127.0.0.1:<port><path>`.

The daemon scans these profile paths in order until it finds `DevToolsActivePort`:
```
~/.config/google-chrome               ← default profile (Linux)
~/.config/chromium                    ← default profile (Chromium)
~/.config/chromium-browser
~/.config/microsoft-edge
~/.var/app/org.chromium.Chromium/config/chromium
~/.var/app/com.google.Chrome/config/google-chrome
~/Library/Application Support/Google/Chrome  ← default profile (macOS)
~/Library/Application Support/Microsoft Edge
~/AppData/Local/Google/Chrome/User Data   ← Windows
~/AppData/Local/Chromium/User Data
~/AppData/Local/Microsoft/Edge/User Data
```

The **first** match wins. For a named `BU_NAME`, you can point directly at a profile by using the `--user-data-dir` flag when launching Chrome.

### Env Var Override

Set `BU_CDP_WS=ws://host:port/path` to skip auto-discovery and connect directly. Useful for:
- **SSH tunnel:** `BU_CDP_WS=ws://127.0.0.1:9222/devtools/browser/...`
- **Remote browser:** Connect to a Chrome running on another machine
- **Browser Use cloud:** The cloud broker provides a WS URL on startup

### CDP Connection Flow (step by step)

```
1. ensure_daemon() called
       │
       ▼
2. daemon_alive()  ── Connect to /tmp/bu-<NAME>.sock
       │              If socket exists and accepts data → daemon is alive
       ▼
3. If not alive: start daemon.py as subprocess
       │
       ▼
4. daemon.py main():
       a. get_ws_url()  ── Read BU_CDP_WS env var,
       │                   OR scan profile paths for DevToolsActivePort,
       │                   OR fail
       ▼
   b. CDPClient(url).start()  ── WebSocket handshake with Chrome
       │                        Blocks until Chrome accepts
       ▼
   c. attach_first_page()  ── Call Target.getTargets,
       │                      filter for real pages (type==page, non-internal URL),
       │                      attach via Target.attachToTarget(flatten=True),
       │                      get sessionId
       ▼
   d. asyncio.start_unix_server()  ── Listen on /tmp/bu-<NAME>.sock
                                     Now helpers.py can connect
       │
       ▼
5. helpers.py._send()  ── Any Python call (goto_url, click, etc.)
       │                  Opens Unix socket → sends JSON line
       │                  → waits for JSON response → returns
       ▼
6. daemon.handle()  ── Read request, route to CDPClient.send_raw():
       │                - Target.* methods → no sessionId (browser-level)
       │                - All others → current self.session (tab-level)
       ▼
7. CDP response returned through Unix socket back to _send()
       │
       ▼
8. Test runs, assertions fire or pass
       │
       ▼
9. On test failure: runner captures screenshot + HTML + events
       │
       ▼
10. SelfHealer.heal() called if agent is enabled:
       a. analyze_failure() → classify error type
       b. If fixable → generate_fix() → apply_fix() → draft PR
       c. If not → flagged for human review
```

### Daemon Lifecycle Commands

```bash
# Start (auto-starts when you call ensure_daemon or run a test)
uv run browser-harness

# Check if running
browser-harness doctor     # exits 0 if healthy

# Stop daemon
browser-harness stop

# View last daemon log line
cat /tmp/bu-<NAME>.log | tail -1

# Full daemon logs
cat /tmp/bu-<NAME>.log

# SSH tunnel scenario (Chrome on remote Mac)
ssh -L 9222:localhost:9222 user@mac -N
# Then locally:
BU_CDP_WS=ws://127.0.0.1:9222 browser-harness
```

---

## Component 2: Bridge (daemon.py)

### File: `browser_harness/daemon.py`

### Purpose
Acts as the translation layer between Chrome's CDP WebSocket and the Unix socket that Python helpers connect to. One async process, starts on demand, manages session lifecycle.

### Architecture

```
Chrome CDP WebSocket                    Unix socket (clients connect here)
┌──────────────────────┐              ┌────────────────────────────────┐
│  CDPClient (cdp_use)  │              │  asyncio.start_unix_server     │
│  · start()            │              │  handler(reader, writer)       │
│  · send_raw()         │              │  reads one JSON line per req    │
│  · event tap          │              │  writes one JSON line per resp │
└──────────┬───────────┘              └──────────────┬───────────────────┘
           │                                        │
           │  CDP commands + events               │ JSON request/response
           │                                        │
           ▼                                        ▼
     ┌─────────────────────────────────────────────────────┐
     │  Daemon.handle()  — the routing hub                 │
     │  · routes CDP calls from Unix socket to CDPClient   │
     │  · taps events (dialogs, load)                       │
     │  · manages self.session (current attached tab)       │
     │  · stale-session recovery                          │
     └─────────────────────────────────────────────────────┘
```

### CDP WebSocket Discovery

Chrome writes a `DevToolsActivePort` file in its profile directory containing:
```
<port>\n<path>
```
Example: `9222\n/devtools/browser/abc123-456`

The WebSocket URL is then `ws://127.0.0.1:<port><path>`.

The daemon scans these profile paths in order until it finds `DevToolsActivePort`:
```
~/.config/google-chrome
~/.config/chromium
~/.config/chromium-browser
~/.config/microsoft-edge
~/.var/app/org.chromium.Chromium/config/chromium
~/.var/app/com.google.Chrome/config/google-chrome
~/Library/Application Support/Google/Chrome
~/AppData/Local/Google/Chrome/User Data
... (and more platform-specific variants)
```

Set `BU_CDP_WS=ws://host:port/path` to skip discovery entirely (useful for SSH tunnels).

### Unix Socket Wire Protocol

**One JSON object per line — request ends with `\n`, response ends with `\n`.**

#### CDP Request
```json
{
  "method": "Page.navigate",
  "params": {"url": "https://example.com"},
  "session_id": "abc123"   // optional — tab session, see below
}
```

#### CDP Response
```json
{
  "result": { ... }        // CDP response data, or
  "error": "error message" // error string
}
```

#### Meta Commands (not CDP)

Meta commands use the `"meta"` key instead of `"method"`:

| meta command | request | response |
|---|---|---|
| `drain_events` | `{"meta": "drain_events"}` | `{"events": [...]}` — returns buffered CDP events and clears buffer |
| `pending_dialog` | `{"meta": "pending_dialog"}` | `{"dialog": null}` or `{"dialog": {"type": "alert", "message": "..."}}` |
| `session` | `{"meta": "session"}` | `{"session_id": "abc123"}` — returns current attached tab session |
| `set_session` | `{"meta": "set_session", "session_id": "abc123"}` | `{"session_id": "abc123"}` — switches attached tab |
| `shutdown` | `{"meta": "shutdown"}` | `{"ok": true}` — stops daemon |

### Session Model

Every CDP tab has a `sessionId` from `Target.attachToTarget`. All CDP commands targeting a specific tab **must** include that `sessionId`.

**Browser-level calls** (`Target.*`, `Network.*`) must **not** include a session — they operate at browser level.

```python
# Routing logic in daemon.handle():
sid = None if method.startswith("Target.") else (req.get("session_id") or self.session)
#   ^ Target.* calls → no session (browser-level)
#   ^ everything else → explicit session from request, or current self.session
```

### Stale Session Recovery

Chrome can invalidate a `sessionId` after navigation. When this happens:

```
CDP error: "Session with given id not found"
     ↓
Daemon re-attaches to first real page → gets new sessionId
     ↓
Retries the failed CDP command with the new sessionId
```

### Event Buffering

The daemon buffers the last 500 CDP events (configurable via `BUF`). Events are consumed in two ways:
1. `drain_events` meta command — returns all buffered events and clears the buffer
2. `Page.javascriptDialogOpening` — stored in `self.dialog`, surfaced via `pending_dialog`

The runner captures these on failure and saves them to `test-results/<test>_console.json`.

### Daemon Lifecycle

| File | Purpose |
|---|---|
| `/tmp/bu-<NAME>.sock` | Unix socket — clients connect here |
| `/tmp/bu-<NAME>.pid` | PID file — written on start |
| `/tmp/bu-<NAME>.log` | Log file — all connections and errors |

To check if running: try connecting to the Unix socket.
To stop: send `{"meta": "shutdown"}` or kill the PID.

### Tab Management

- On start, daemon attaches to the first real (non-chrome://) page it finds
- If no real pages exist, creates `about:blank` instead of attaching to the omnibox
- Each tab is marked with 🟢 in the title so users can see which tab is controlled
- `Target.getTargets` lists all tabs; `Target.attachToTarget` with `flatten=True` gives a `sessionId`
- `Target.activateTarget` brings a tab to the foreground (doesn't change session)

### Required imports
```python
import asyncio, json, os, socket, sys, time, urllib.request
from collections import deque
from pathlib import Path
from cdp_use.client import CDPClient
```

---

## Component 3: Core Helpers (browser_harness/helpers.py)

### File: `browser_harness/helpers.py`

### Purpose
One function = one CDP command. Thin, direct wrappers. No waiting logic, no retries, no state.

### Environment
- Reads `.env` from the project root for `BU_CDP_WS`, `BU_NAME`
- Constants: `SOCK = f"/tmp/bu-{NAME}.sock"`
- Internal URL prefixes: `("chrome://", "chrome-untrusted://", "devtools://", "chrome-extension://", "about:")`

### How to send a CDP command
```python
def _send(req):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect(SOCK)
    s.sendall((json.dumps(req) + "\n").encode())
    data = b""
    while not data.endswith(b"\n"):
        chunk = s.recv(1 << 20)
        if not chunk: break
        data += chunk
    s.close()
    r = json.loads(data)
    if "error" in r: raise RuntimeError(r["error"])
    return r

def cdp(method, session_id=None, **params):
    return _send({"method": method, "params": params, "session_id": session_id}).get("result", {})
```

### Required functions (minimum set)

**Navigation:**
```python
def goto_url(url):
    return cdp("Page.navigate", url=url)

def wait_for_load(timeout=15.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if js("document.readyState") == "complete":
            return True
        time.sleep(0.3)
    return False

def page_info():
    """Returns {url, title, w, h, sx, sy, pw, ph} or {dialog: {...}} if dialog open"""
    # Check pending dialog first
    dialog = _send({"meta": "pending_dialog"}).get("dialog")
    if dialog:
        return {"dialog": dialog}
    r = cdp("Runtime.evaluate",
            expression="JSON.stringify({url:location.href,title:document.title,w:innerWidth,h:innerHeight,sx:scrollX,sy:scrollY,pw:document.documentElement.scrollWidth,ph:document.documentElement.scrollHeight})",
            returnByValue=True)
    return json.loads(r["result"]["value"])
```

**Input:**
```python
def click_at_xy(x, y, button="left", clicks=1):
    cdp("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button=button, clickCount=clicks)
    cdp("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y, button=button, clickCount=clicks)

def type_text(text):
    cdp("Input.insertText", text=text)

def press_key(key, modifiers=0):
    # Map key name to virtual key code, dispatch keyDown + char + keyUp events

def scroll(x, y, dy=-300, dx=0):
    cdp("Input.dispatchMouseEvent", type="mouseWheel", x=x, y=y, deltaX=dx, deltaY=dy)
```

**JavaScript:**
```python
def js(expression, target_id=None):
    """Execute JS in the page. Auto-wrap bare `return` expressions."""
    sid = cdp("Target.attachToTarget", targetId=target_id, flatten=True)["sessionId"] if target_id else None
    if "return " in expression and not expression.strip().startswith("("):
        expression = f"(function(){{{expression}}})()"
    r = cdp("Runtime.evaluate", session_id=sid, expression=expression, returnByValue=True, awaitPromise=True)
    return r.get("result", {}).get("value")
```

**Visual:**
```python
def capture_screenshot(path="/tmp/shot.png", full=False):
    r = cdp("Page.captureScreenshot", format="png", captureBeyondViewport=full)
    open(path, "wb").write(base64.b64decode(r["data"]))
    return path
```

**Tabs:**
```python
def list_tabs(include_chrome=True):
    return [t for t in cdp("Target.getTargets")["targetInfos"]
            if t["type"] == "page"
            and (include_chrome or not t.get("url","").startswith(INTERNAL))]

def switch_tab(target):
    """Accept targetId string or dict from list_tabs()/current_tab()"""
    target_id = target.get("targetId") if isinstance(target, dict) else target
    cdp("Target.activateTarget", targetId=target_id)
    sid = cdp("Target.attachToTarget", targetId=target_id, flatten=True)["sessionId"]
    _send({"meta": "set_session", "session_id": sid})
    return sid

def new_tab(url="about:blank"):
    tid = cdp("Target.createTarget", url="about:blank")["targetId"]
    switch_tab(tid)
    if url != "about:blank":
        goto_url(url)
    return tid
```

**Utility:**
```python
def wait(seconds=1.0):
    time.sleep(seconds)

def drain_events():
    return _send({"meta": "drain_events"})["events"]

def http_get(url, headers=None, timeout=20.0):
    """Pure HTTP without browser. Use for APIs."""
    # Returns decoded string response
```

### Debug mode
Set `BH_DEBUG_CLICKS=1` env var to overlay red circles on screenshots showing where clicks landed. Useful during test development.

---

## Component 4: UI Helpers (harness/helpers.py)

### File: `harness/helpers.py`

### Purpose
DOM-centric helpers built on top of `js()`. Query the live DOM, return structured element data.

### Element info structure
```python
{
    "tag": "DIV",
    "text": "Button label",
    "attrs": {"data-testid": "submit-btn", "class": "primary"},
    "visible": True,
    "rect": {"x": 100, "y": 200, "w": 80, "h": 40},
    "children": ["BUTTON", "SPAN"]
}
```

### Required functions

```python
def find_element(selector):
    """Find element by CSS selector. Returns element dict or None."""
    expr = json.dumps(selector)
    return js(f"""
        (function(){{
            const el = document.querySelector({expr});
            if (!el) return null;
            const rect = el.getBoundingClientRect();
            const visible = rect.width > 0 && rect.height > 0 && getComputedStyle(el).visibility !== 'hidden';
            const attrs = {{}};
            for (const attr of el.attributes) attrs[attr.name] = attr.value;
            const children = [];
            for (const child of el.children) children.push(child.tagName);
            return {{tag: el.tagName, text: el.innerText, attrs, visible,
                     rect: {{x: rect.x, y: rect.y, w: rect.width, h: rect.height}}, children}};
        }})()
    """)

def wait_for_element(selector, timeout=10):
    """Poll find_element until found or timeout. Returns element dict or None."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = find_element(selector)
        if result is not None:
            return result
        time.sleep(0.3)
    return None

def wait_for_element_visible(selector, timeout=10):
    """Wait for element to be both present AND visible. Returns element dict or None."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = find_element(selector)
        if result is not None and result.get("visible"):
            return result
        time.sleep(0.3)
    return None

def is_element_visible(selector):
    """Immediate check. Returns bool."""
    result = find_element(selector)
    return result is not None and result.get("visible", False)

def get_element_text(selector):
    return find_element(selector).get("text") if find_element(selector) else None

def get_element_attribute(selector, attr):
    """Get a single attribute value from the first matching element."""
    expr = json.dumps(selector)
    return js(f"""
        (function(){{
            const el = document.querySelector({expr});
            return el ? el.getAttribute({json.dumps(attr)}) : null;
        }})()
    """)

def get_all_text(selector):
    """Get text of ALL elements matching selector. Returns list."""
    expr = json.dumps(selector)
    return js(f"""
        (function(){{
            const els = document.querySelectorAll({expr});
            return Array.from(els).map(el => el.innerText);
        }})()
    """) or []
```

---

## Component 5: Assertions (harness/assertions.py)

### File: `harness/assertions.py`

### Purpose
Test language — the API your test files call. Each assertion checks a condition, captures a screenshot on failure, raises with context.

### Required assertions

Each assertion polls until the condition is met or the timeout expires, then captures a screenshot and raises `AssertionError` with context.

```python
def assert_visible(selector: str, timeout: float = 10) -> None:
    """Wait for element to be visible; fail with screenshot if not found or not visible."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _count_matching(selector) > 0 and _element_visible(selector):
            return
        time.sleep(0.2)
    raise AssertionError(f"element not visible. Selector: {selector}. Screenshot: {_screenshot_path(selector)}")

def assert_not_visible(selector: str, timeout: float = 5) -> None:
    """Wait for element to be hidden or removed."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _count_matching(selector) == 0 or not _element_visible(selector):
            return
        time.sleep(0.2)
    raise AssertionError(f"element still visible. Selector: {selector}. Screenshot: {_screenshot_path(selector)}")

def assert_text(selector: str, expected: str, timeout: float = 10) -> None:
    """Wait for element text to match expected value."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _count_matching(selector) > 0:
            actual = js(f"document.querySelector({repr(selector)})?.textContent?.trim()")
            if actual == expected:
                return
        time.sleep(0.2)
    raise AssertionError(f"text mismatch. Selector: {selector}. Expected: {expected!r}. Actual: {actual!r}. Screenshot: {_screenshot_path(selector)}")

def assert_url(pattern: str, timeout: float = 5) -> None:
    """Check current URL matches pattern (substring or regex)."""
    deadline = time.time() + timeout
    is_regex = "/" in pattern and len(pattern) > 2
    while time.time() < deadline:
        url = _page_url()
        if is_regex and re.search(pattern, url): return
        if not is_regex and pattern in url: return
        time.sleep(0.2)
    raise AssertionError(f"URL pattern not matched. Pattern: {pattern!r}. URL: {url}. Screenshot: {_screenshot_path(pattern)}")

def assert_attribute(selector: str, attr: str, expected_value: str, timeout: float = 10) -> None:
    """Check element's attribute equals expected value."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _count_matching(selector) > 0:
            actual = js(f"document.querySelector({repr(selector)})?.getAttribute({repr(attr)})")
            if actual == expected_value:
                return
        time.sleep(0.2)
    raise AssertionError(f"attribute mismatch. Selector: {selector}. Attr: {attr}. Expected: {expected_value!r}. Actual: {actual!r}. Screenshot: {_screenshot_path(selector)}")

def assert_element_count(selector: str, count: int, timeout: float = 10) -> None:
    """Check that exactly `count` elements match selector."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _count_matching(selector) == count:
            return
        time.sleep(0.2)
    actual = _count_matching(selector)
    raise AssertionError(f"element count mismatch. Selector: {selector}. Expected: {count}. Actual: {actual}. Screenshot: {_screenshot_path(selector)}")

# Internal helpers
def _screenshot_path(selector: str) -> Path:
    RESULTS_DIR.mkdir(exist_ok=True)
    safe = re.sub(r"[^a-zA-Z0-9]", "_", selector)
    ts = int(time.time() * 1000)
    return RESULTS_DIR / f"failed_{safe}_{ts}.png"

def _page_url() -> str:
    try: return js("location.href") or ""
    except Exception: return ""

def _element_visible(selector: str) -> bool:
    return js(f"!!(document.querySelector({repr(selector)})?.offsetParent !== null)") is True

def _count_matching(selector: str) -> int:
    return int(js(f"document.querySelectorAll({repr(selector)}).length") or 0)
```

---

## Component 6: Test Runner (harness/runner.py)

### File: `harness/runner.py`

### Purpose
Discovers and executes test files. Handles daemon lifecycle (ensure daemon is running before tests).

### Responsibilities

1. **Daemon lifecycle**
   ```python
   def ensure_daemon(name=None):
       """Start daemon if not already running. Returns (socket_path, pid)."""
       # Check if already running by connecting to socket
       # If not, spawn daemon process (asyncio.run in subprocess or start via cli)
       # Wait for socket to appear
   ```

2. **Test discovery**
   - Scan a directory for `test_*.py` files
   - Import and collect functions starting with `test_`

3. **Execution**
   - Run each test function in order
   - Capture stdout/stderr
   - Store screenshot path if assertion fails
   - Exit code 0 if all pass, non-zero if any fail

4. **Reporting**
   - On failure: print which test failed, the assertion message, the screenshot path
   - On success: print test name + pass marker

---

## Component 7: Agent Layer (agent/) — Optional

### Purpose
AI-powered test generation, pattern learning, and self-healing. The harness works without this. Add when you need natural language → test code, automatic test maintenance, or learned selector strategies across test runs.

The agent layer is NOT a separate running service — it's a library that the runner or a CI pipeline calls. It has four components that share a single `AppModel` as the knowledge store.

### Files

**agent/app_model.py** — the knowledge base
**agent/test_author.py** — NL → test code
**agent/self_healer.py** — failure → fix
**agent/ci_manager.py** — GitHub integration

---

### AppModel — What the Agent Learns

AppModel is a per-app JSON file at `specs/<app-name>/app_model.json`. It accumulates knowledge across test runs.

#### Schema

```json
{
  "app_name": "sap-build",
  "app_url": "https://sap.build.com",
  "selectors": {
    "login_email_field": "[data-testid='email']",
    "login_submit_btn": "[data-testid='login-submit']",
    "lobby_card": ".lobby-card"
  },
  "url_patterns": [
    {"pattern": ".*sap\.build.*", "description": "SAP Build domain"},
    {"pattern": ".*login.*", "description": "Login flow entry"}
  ],
  "wait_patterns": [
    {"selector": "[data-testid='spinner']", "reason": "Wait for loading spinner to disappear before asserting content"},
    {"selector": ".toast", "reason": "Wait for toast notification after form submit"}
  ],
  "known_traps": [
    {"selector": ".modal-overlay", "issue": "Overlay blocks clicks — use force: true or dismiss first"}
  ],
  "component_states": {
    "Button": ["default", "hover", "disabled", "loading"],
    "Input": ["empty", "focused", "filled", "error", "disabled"]
  },
  "updated_at": "2026-05-08T12:00:00Z"
}
```

#### How Learning Happens

1. **TestAuthor writes a test** — It calls `app_model.add_selector(key, selector)` for each element it references, so the model learns which selectors exist.
2. **SelfHealer fixes a test** — On `selector_stale`, it calls `app_model.add_selector(key, new_selector)` with the working alternative.
3. **Human annotates** — When a human adds a `wait_pattern` or `known_trap` entry, that knowledge is preserved.
4. **On domain change** — `goto_url()` in helpers.py checks `browser_harness/domain-skills/<hostname>/` and returns any stored skill files as a hint to the caller (`.domain_skills` field in the response).

#### Selector Priority

When SelfHealer searches for a replacement selector, it prefers in this order:
1. `data-testid` attribute (most stable)
2. `aria-label`
3. `role` attribute
4. `id` attribute (fragile — changes with routing)

---

### SelfHealer — Failure → Fix Loop

The SelfHealer is the core of the learning + improvement system. It is invoked after every test failure.

#### Flow: `heal(test_file, error, screenshot, page_html, page_info)`

```
Test assertion fails
        │
        ▼
SelfHealer.analyze_failure()
        │
        ├── "selector_stale"  → fixable
        │     │
        │     ▼
        │  _diagnose_selector_error()  ─── tries to find alternative from page_html
        │     │  Priority: data-testid > aria-label > role > id
        │     │
        │     ▼
        │  generate_fix()  ─── patches the stale selector in test file
        │     │
        │     ▼
        │  apply_fix()  ─── writes patch + creates draft PR
        │     │
        │     ▼
        │  Returns: {status: "fixed", pr_url: "..."}
        │
        ├── "assertion_wrong"  → fixable
        │     │
        │     ▼
        │  _analyze_assertion_error()  ─── extracts expected vs actual from error string
        │     │
        │     ▼
        │  generate_fix()  ─── updates expected value to actual value
        │
        ├── "infrastructure"  → not immediately fixable
        │     │
        │     ▼
        │  retry_test() once  ─── if it passes, done; if it fails, flag human
        │
        ├── "flaky"  → flag human immediately
        ├── "behavior_changed"  → flag human immediately
        │
        ▼
status: "fixed" | "flagged"
pr_url: GitHub PR URL or null
message: human-readable explanation
```

#### Failure Types

| Type | Diagnosis | Auto-fix? | Action |
|---|---|---|---|
| `selector_stale` | Element moved or renamed | Yes | Patch selector, create draft PR |
| `assertion_wrong` | Expected value wrong (app changed) | Yes | Update expected value |
| `infrastructure` | Network/timeout/500 error | Retry once | Flag if retry fails |
| `flaky` | Race condition, intermittent | No | Flag human |
| `behavior_changed` | Unknown error | No | Flag human |

#### Retry Policy

- `infrastructure` errors are retried once before flagging.
- All other fixable errors (`selector_stale`, `assertion_wrong`) are fixed and flagged in the same pass — no retry.
- Max one auto-fix per test run per failure type before flagging for human review.

---

### TestAuthor — NL → Test Code

TestAuthor takes a natural language task description and generates a runnable Python test file.

#### Input examples

```
"Navigate to sap.build.com, click the login button, assert the URL contains 'login'"
"Fill the email field with test@example.com, click submit, wait for the lobby card"
```

#### Parsing rules (keyword-based, not LLM)

| Pattern in input | Generated code |
|---|---|
| `navigate to <url>` / `go to <url>` | `goto_url("<url>")` |
| `click [element]` | `browser_click(element="...", ref=get_selector("..."))` |
| `fill [field] with [value]` | `browser_fill_form(fields=[{...}])` |
| `type [text] in [field]` | `browser_type(element="...", text="...")` |
| `wait for [element]` | `wait_for_element("...")` |
| `assert that [condition]` | `assert <condition>` |
| `screenshot` | `capture_screenshot()` |

Selectors are resolved via AppModel if available; otherwise a default `data-testid`-based selector is constructed.

---

### CIManager — GitHub Integration

CIManager handles:
- **PR creation** — SelfHealer creates a draft PR with the fix for human review
- **File updates** — Patches test files on a feature branch
- **Commit status** — Sets CI check status on a commit
- **PR comments** — Posts test results as PR comments

GitHub token via `GITHUB_TOKEN` or `GH_TOKEN` env var.

---

### Domain Skills & Interaction Skills (runtime-generated)

These directories under `browser_harness/` are created by the agent at runtime:

**`browser_harness/domain-skills/<hostname>/`** — One markdown file per URL pattern the agent has tested. Contains: what wait patterns worked, which selectors are stable, any traps observed. Example:
```
domain-skills/
└── sap-build/
    └── login.flow.md   ← generated after first successful login test
```

**`browser_harness/interaction-skills/<situation>/`** — How to handle specific UI situations. Example:
```
interaction-skills/
└── dialogs.md          ← how to handle alert/confirm/beforeunload dialogs
```

These are **not** required for the harness to function — they are purely for the agent's context on subsequent runs. `goto_url()` returns `.domain_skills` in its response so the caller can pass them to the agent.

---

## Directory Structure

```
browser-harness-testing/
├── browser_harness/              # Core CDP bridge
│   ├── daemon.py                 # WebSocket ↔ Unix socket bridge (async)
│   ├── helpers.py                # CDP command wrappers (goto_url, click, js, etc.)
│   ├── admin.py                  # Daemon lifecycle (ensure, restart, doctor)
│   ├── run.py                    # CLI entry point: browser-harness
│   ├── domain-skills/            # (runtime) per-hostname learned skills
│   │   └── <hostname>/
│   │       └── *.md
│   └── interaction-skills/       # (runtime) how to handle UI situations
│       └── *.md
│
├── harness/                      # UI testing layer
│   ├── __init__.py               # Re-exports: from browser_harness import * + harness helpers + assertions
│   ├── helpers.py                # DOM helpers (find_element, wait_for_element, etc.)
│   ├── assertions.py             # Test assertions with screenshot-on-failure
│   └── runner.py                 # Test executor
│
├── agent/                        # AI layer (optional)
│   ├── __init__.py
│   ├── app_model.py             # Learned app knowledge (selectors, wait patterns, traps)
│   ├── test_author.py          # NL → test code
│   ├── self_healer.py          # Failure → fix loop
│   ├── ci_manager.py           # GitHub integration (PRs, commits, comments)
│
├── specs/                        # App models (one subdir per app)
│   └── <app-name>/
│       └── app_model.json       # ← created by agent, read by harness
│
├── tests/                        # Test files (test_*.py)
│   └── test_example.py
│
├── test-results/                  # Test artifacts (screenshots, HTML, logs)
│   └── *.png, *.html, *.json
│
├── .env                          # BU_CDP_WS, BU_NAME, GITHUB_TOKEN, etc.
│
└── pyproject.toml
```

---

## Env Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `BU_CDP_WS` | auto-discovered | WebSocket URL to Chrome. Skip auto-discovery if set. |
| `BU_NAME` | `default` | Daemon name. Used for socket path `/tmp/bu-<NAME>.sock`. Use unique name per project. |
| `BH_DEBUG_CLICKS` | unset | Set to `1` to overlay click markers on screenshots |
| `GITHUB_TOKEN` | none | For CI manager to post PR comments |
| `GH_TOKEN` | none | Alias for GITHUB_TOKEN |

---

## Running the Harness

### Setup (one-time)

```bash
# Verify everything is connected
browser-harness doctor

# If doctor reports "chrome not enabled": open chrome://inspect/#remote-debugging
# in your browser, tick "Discover network targets", click Allow if prompted
```

### Running Tests

```bash
# Run all tests (daemon auto-starts on first run)
uv run python -m harness.runner tests/

# Run with a named profile (e.g. for a specific app)
BU_NAME=sap-build uv run python -m harness.runner tests/

# Run a single test file
uv run python -m harness.runner tests/test_login.py
```

### Using a Separate Profile Per Workflow

```bash
# Terminal 1: Start Chrome with a dedicated test profile
google-chrome --remote-debugging-port=9222 \
  --user-data-dir="$HOME/.config/chrome-myapp"

# Terminal 2: Run tests against that profile
BU_NAME=myapp uv run python -m harness.runner tests/
```

The harness auto-discovers Chrome via the profile path. `BU_NAME=myapp` maps to `~/.config/google-chrome-myapp` on Linux.

### SSH Tunnel (Chrome on remote machine, harness on local Pi)

```bash
# On Pi: establish tunnel
ssh -L 9222:localhost:9222 user@mac -N

# On Pi: run tests with the tunneled WebSocket URL
BU_CDP_WS=ws://127.0.0.1:9222 uv run python -m harness.runner tests/
```

### Exploratory REPL

```bash
uv run browser-harness <<'PY'
goto_url("https://example.com")
wait_for_load()
print(page_info())
PY
```

---

## Test File Format

```python
from harness import *

def test_example():
    goto_url("https://example.com")
    wait_for_load()
    assert_visible("[data-testid='submit-btn']")
    assert_text("h1", "Expected Title")
    click_at_xy(200, 300)
    assert_url("success")
```

All imports come from `harness/__init__.py` which re-exports everything from `browser_harness` and `harness` submodules.

---

## Design Constraints

1. **Transparent CDP mapping.** Every function is a direct path to one CDP command. If you can't trace what your function does to a specific CDP call, it doesn't belong here.

2. **No automatic waiting.** Call `wait_for_load()` and `wait_for_element()` explicitly. Hidden waits hide bugs.

3. **Screenshot on every failure.** No exception should escape without a screenshot. This is non-negotiable for debugging.

4. **Unix socket for local IPC.** Keeps it simple, keeps it fast. No HTTP server, no extra ports.

5. **One daemon per name.** Set `BU_NAME` to isolate multiple projects. Each gets its own socket and PID file.

6. **Agent is optional.** The harness must work with zero AI components. Add AI only when the use case demands it.

7. **Learning is explicit.** AppModel is only updated by named method calls in TestAuthor and SelfHealer. The harness itself does no learning — it only reads from AppModel.

---

## Building From Scratch Checklist

### Phase 1 — Core CDP Bridge

- [ ] Chrome running with `--remote-debugging-port=9222`
- [ ] `daemon.py` connects to Chrome WebSocket via `CDPClient` from `cdp_use`
- [ ] `daemon.py` reads `DevToolsActivePort` for auto-discovery, or uses `BU_CDP_WS` env var
- [ ] `daemon.py` attaches to first real page on startup; marks tab 🟢
- [ ] `daemon.py` listens on Unix socket `/tmp/bu-<NAME>.sock` with JSON line protocol
- [ ] `daemon.py` routes CDP calls: `Target.*` without session, all others with `self.session`
- [ ] `daemon.py` handles meta commands: `drain_events`, `pending_dialog`, `shutdown`, `set_session`, `session`
- [ ] `daemon.py` recovers from stale session: re-attaches and retries
- [ ] `daemon.py` buffers last 500 events; stores dialog state
- [ ] `daemon.py` writes PID to `/tmp/bu-<NAME>.pid`, logs to `/tmp/bu-<NAME>.log`
- [ ] `helpers.py` exposes minimal CDP wrappers: `goto_url`, `click_at_xy`, `type_text`, `press_key`, `js`, `capture_screenshot`, `wait`, `wait_for_load`, `page_info`, `list_tabs`, `switch_tab`, `new_tab`, `drain_events`
- [ ] `helpers.py` `_send()` reads `.env` for `BU_CDP_WS`, `BU_NAME`
- [ ] `admin.py` implements `ensure_daemon()`: checks socket, starts if needed

### Phase 2 — Harness (UI + Assertions)

- [ ] `harness/helpers.py` exposes: `find_element`, `wait_for_element`, `is_element_visible`, `get_element_text`, `get_element_attribute`, `get_all_text`
- [ ] `harness/helpers.py` element info dict: `{uid, tag, text, attrs, visible, rect, children}`
- [ ] `harness/assertions.py` exposes: `assert_visible`, `assert_not_visible`, `assert_text`, `assert_url`, `assert_attribute`, `assert_element_count`
- [ ] `harness/assertions.py` screenshots on every failure to `test-results/`
- [ ] `harness/__init__.py` re-exports all public names from both `browser_harness` and `harness`

### Phase 3 — Runner

- [ ] `harness/runner.py` calls `ensure_daemon()` before running tests
- [ ] Discovers `test_*.py` files in directory or single file
- [ ] Runs each `test_*` function, captures stdout/stderr
- [ ] On failure: screenshot + page HTML + console events → `test-results/`
- [ ] Exit code 0 if all pass, non-zero if any fail

### Phase 4 — Agent (optional, in dependency order)

- [ ] `specs/<app-name>/app_model.json` schema with: selectors, url_patterns, wait_patterns, known_traps, component_states, updated_at
- [ ] `app_model.py`: `load()`, `save()`, `add_selector()`, `add_wait_pattern()`, `add_trap()`, `get_selector()`, `is_trap()`
- [ ] `self_healer.py`: `analyze_failure()` — classify into 5 failure types
- [ ] `self_healer.py`: `heal()` — full loop: analyze → generate_fix → apply_fix → draft PR
- [ ] `self_healer.py`: retry policy — infrastructure retries once, others fix or flag
- [ ] `test_author.py`: keyword-based NL parsing → Python test code
- [ ] `test_author.py`: selector resolution via AppModel
- [ ] `ci_manager.py`: `create_branch()`, `update_file()`, `create_pr()` for draft fix PRs
- [ ] `domain-skills/<hostname>/` and `interaction-skills/` directories created by agent (not required for Phase 1–3)

That's the whole thing. Nothing more is needed. 😏