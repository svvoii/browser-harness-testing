# Browser Harness Architecture

**Purpose:** A minimal, robust testing engine built on Chrome DevTools Protocol (CDP). Drives a real Chrome browser in developer mode via WebSocket, exposing a thin Python API for UI/E2E testing.

**Design philosophy:** Zero abstraction. Every function maps directly to one CDP command. The browser is your runtime. You own the stack.

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
    │  Agent (optional) │  ← AppModel, TestAuthor, SelfHealer, CIManager
    │  agent/           │    AI layer on top. Harness works without this.
    └───────────────────┘
```

**Key property:** Each layer depends only on the layer directly below it. The agent layer is optional — the harness works standalone without any AI components.

---

## Component 1: Chrome in Developer Mode

### What
A Chrome browser running with `--remote-debugging-port=9222`. This opens a WebSocket server that exposes the Chrome DevTools Protocol (CDP).

### How to launch

**macOS:**
```bash
open -a "Google Chrome" --args --remote-debugging-port=9222 \
  --user-data-dir=~/Library/Application\ Support/Google/Chrome
```

**Linux (system Chrome):**
```bash
google-chrome --remote-debugging-port=9222 \
  --user-data-dir=~/.config/google-chrome
```

**Linux (Chromium):**
```bash
chromium-browser --remote-debugging-port=9222 \
  --user-data-dir=~/.config/chromium
```

### What it provides
- Chrome writes a `DevToolsActivePort` file in its profile directory
- Format: `port\n/path`
- Example: `9222\n/devtools/browser/abc123-456`
- The WebSocket URL is `ws://127.0.0.1:<port><path>`
- Chrome must be open with this flag for the harness to connect

### Profile paths searched (auto-discovery)
The bridge scans these paths for `DevToolsActivePort`:
```
~/Library/Application Support/Google/Chrome
~/.config/google-chrome
~/.config/chromium
~/.config/chromium-browser
~/.var/app/org.chromium.Chromium/config/chromium
~/.var/app/com.google.Chrome/config/google-chrome
~/.config/microsoft-edge
~/.config/microsoft-edge-beta
~/.config/microsoft-edge-dev
~/.var/app/com.microsoft.Edge/config/microsoft-edge
~/AppData/Local/Google/Chrome/User Data
~/AppData/Local/Chromium/User Data
~/AppData/Local/Microsoft/Edge/User Data
```

### Env var override
Set `BU_CDP_WS=ws://host:port/path` to skip auto-discovery and connect to a specific WebSocket URL directly. Useful for SSH tunnel scenarios.

---

## Component 2: Bridge (daemon.py)

### File: `browser_harness/daemon.py`

### Purpose
Acts as the translation layer between the Chrome WebSocket and the Unix socket that Python helpers connect to. One async process, starts on demand, manages session lifecycle.

### Responsibilities

1. **Connect to Chrome's WebSocket endpoint**
   - Discover or use `BU_CDP_WS` env var
   - Use `CDPClient` from `cdp_use` library
   - `asyncio` handles concurrent message passing

2. **Attach to a browser tab**
   - Call `Target.getTargets` to list all open tabs
   - Filter for real pages (type=="page", URL does not start with `chrome://`, `about:`, etc.)
   - Call `Target.attachToTarget` with `flatten=True` to get a `sessionId`
   - Mark the tab with a green circle emoji (🟢) in the title so the user can see which tab is being controlled

3. **Bridge: Unix socket ↔ WebSocket**
   - Listen on Unix socket `/tmp/bu-<NAME>.sock` (name from `BU_NAME` env, default "default")
   - Each incoming JSON line is a request dict with `method` and optional `params`
   - Forward to CDP client, respond with JSON result
   - Support meta-commands (not CDP): `drain_events`, `pending_dialog`, `shutdown`, `set_session`

4. **Handle session stale**
   - Chrome can invalidate a session ID on navigation
   - On `"Session with given id not found"` error, re-attach to first page automatically
   - Detect and surface dialog events (`Page.javascriptDialogOpening` / `Page.javascriptDialogClosed`)

### Key implementation details

```python
# Session handling — explicit session wins for non-Target calls
sid = None if method.startswith("Target.") else (req.get("session_id") or self.session)

# Stale session recovery
if "Session with given id not found" in str(e) and sid == self.session:
    await self.attach_first_page()
    return await self.cdp.send_raw(method, params, session_id=self.session)
```

### Session IDs
- Each attached tab has a `sessionId`
- All CDP commands for a specific tab must include that `sessionId`
- Browser-level calls (`Target.*`) must NOT include a session — they operate at browser level

### Daemon lifecycle
- PID written to `/tmp/bu-<NAME>.pid`
- Log written to `/tmp/bu-<NAME>.log`
- Check if running: try to connect to the Unix socket
- Start: `asyncio.run(main())` — connects to Chrome, then listens on Unix socket
- Stop: send `{"meta": "shutdown"}` or signal the stop Event

### Required imports
```python
import asyncio, json, os, socket, time
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

```python
def assert_visible(selector, timeout=10):
    """Fail if element not visible after timeout."""
    start = time.time()
    while time.time() - start < timeout:
        if is_element_visible(selector):
            return
        time.sleep(0.3)
    _fail_screenshot(f"Element {selector} not visible after {timeout}s")

def assert_not_visible(selector, timeout=5):
    """Fail if element is still visible after timeout."""
    start = time.time()
    while time.time() - start < timeout:
        result = find_element(selector)
        if result is None or not result.get("visible"):
            return
        time.sleep(0.3)
    _fail_screenshot(f"Element {selector} still visible after {timeout}s")

def assert_text(selector, expected, timeout=10):
    """Fail if element text does not match expected string."""
    start = time.time()
    while time.time() - start < timeout:
        el = find_element(selector)
        if el and el.get("text", "").strip() == expected.strip():
            return
        time.sleep(0.3)
    _fail_screenshot(f"Text of {selector} != '{expected}'")

def assert_url(pattern, timeout=5):
    """Fail if page URL does not match (substring or regex)."""
    start = time.time()
    while time.time() - start < timeout:
        url = js("location.href")
        if pattern in url:
            return
        time.sleep(0.3)
    _fail_screenshot(f"URL {js('location.href')} does not contain '{pattern}'")

def assert_attribute(selector, attr, value, timeout=10):
    """Fail if element attribute does not equal value."""
    start = time.time()
    while time.time() - start < timeout:
        actual = get_element_attribute(selector, attr)
        if actual == value:
            return
        time.sleep(0.3)
    _fail_screenshot(f"Attribute {attr} of {selector} = '{actual}', expected '{value}'")

def assert_element_count(selector, count, timeout=10):
    """Fail if number of matching elements != count."""
    start = time.time()
    while time.time() - start < timeout:
        found = get_all_text(selector)  # or a dedicated count helper
        if len(found) == count:
            return
        time.sleep(0.3)
    _fail_screenshot(f"Element count for {selector} = {len(found)}, expected {count}")

def _fail_screenshot(message):
    """Internal: capture screenshot and raise."""
    import traceback
    ts = int(time.time())
    path = f"/tmp/fail_{ts}.png"
    capture_screenshot(path)
    raise AssertionError(f"{message}\nScreenshot: {path}\n{traceback.format_exc()}")
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
AI-powered test generation and self-healing. The harness works without this. Add when you need natural language → test code or automatic test maintenance.

### Files

**agent/app_model.py**
- JSON-based knowledge store
- Keys: selector strategies per page/element, wait patterns, URL patterns, known failure modes
- Load/save to `specs/<app-name>/app_model.json`
- Method: `find_selector(element_id)` → returns preferred selector + fallbacks

**agent/test_author.py**
- Input: natural language description of a test flow
- Output: a Python test function string
- Uses an LLM: prompt = app_model context + natural language → test code
- Writes to `tests/` directory

**agent/self_healer.py**
- On test failure: analyze what broke (selector stale, assertion wrong, app changed, flaky)
- Decide fix: update selector, update assertion, flag human, retry
- If selector: use AppModel to find alternative, patch test file, open draft PR

**agent/ci_manager.py**
- GitHub API client
- Post test results as PR comments
- Create draft PRs with fixes for human review
- Set commit status checks

---

## Directory Structure

```
browser-harness-testing/
├── browser_harness/              # Core CDP bridge
│   ├── daemon.py                 # WebSocket ↔ Unix socket bridge (async)
│   ├── helpers.py                # CDP command wrappers (goto_url, click, js, etc.)
│   ├── admin.py                  # Daemon lifecycle (ensure, restart, doctor)
│   └── run.py                    # CLI entry point: browser-harness
│   └── domain-skills/            # (optional) per-domain LLM-generated skills
│   └── interaction-skills/        # (optional) per-interaction LLM-generated skills
│
├── harness/                      # UI testing layer
│   ├── __init__.py               # Re-exports: from browser_harness import * + harness helpers + assertions
│   ├── helpers.py                # DOM helpers (find_element, wait_for_element, etc.)
│   ├── assertions.py             # Test assertions with screenshot-on-failure
│   └── runner.py                 # Test executor
│
├── agent/                        # AI layer (optional)
│   ├── app_model.py              # Learned app knowledge
│   ├── test_author.py            # NL → test code
│   ├── self_healer.py            # Failure → fix
│   └── ci_manager.py             # GitHub integration
│
├── specs/                        # App models (one subdir per app)
│   └── <app-name>/
│       └── app_model.json
│
├── tests/                        # Test files (test_*.py)
│   └── test_example.py
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

### Local (Chrome on same machine)
```bash
# Terminal 1: Start Chrome in dev mode (do once)
google-chrome --remote-debugging-port=9222

# Terminal 2: Run a test
cd ~/projects/browser-harness-testing
uv run python -m harness.runner tests/test_example.py

# Or exploratory REPL
uv run browser-harness <<'PY'
goto_url("https://example.com")
wait_for_load()
print(page_info())
PY
```

### SSH tunnel (Chrome on remote Mac, harness on Pi)
```bash
# On Pi: establish tunnel
ssh -L 9222:localhost:9222 user@mac -N

# Then run tests on Pi as if Chrome were local
cd ~/projects/browser-harness-testing
BU_CDP_WS=ws://127.0.0.1:9222 uv run python -m harness.runner tests/
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

1. **No abstraction over CDP.** Every function maps to one command. If you can't explain what CDP call your function makes, it doesn't belong here.

2. **No automatic waiting.** Call `wait_for_load()` and `wait_for_element()` explicitly. Hidden waits hide bugs.

3. **Screenshot on every failure.** No exception should escape without a screenshot. This is non-negotiable for debugging.

4. **Unix socket for local IPC.** Keeps it simple, keeps it fast. No HTTP server, no extra ports.

5. **One daemon per name.** Set `BU_NAME` to isolate multiple projects. Each gets its own socket and PID file.

6. **Agent is optional.** The harness must work with zero AI components. Add AI only when the use case demands it.

---

## Building From Scratch Checklist

- [ ] Chrome running with `--remote-debugging-port=9222`
- [ ] `daemon.py` connects to Chrome WebSocket and listens on Unix socket
- [ ] `helpers.py` exposes: `goto_url`, `click_at_xy`, `type_text`, `press_key`, `js`, `capture_screenshot`, `wait`, `wait_for_load`, `page_info`, `list_tabs`, `switch_tab`, `new_tab`
- [ ] `harness/helpers.py` exposes: `find_element`, `wait_for_element`, `is_element_visible`, `get_element_text`, `get_element_attribute`, `get_all_text`
- [ ] `harness/assertions.py` exposes: `assert_visible`, `assert_not_visible`, `assert_text`, `assert_url`, `assert_attribute`, `assert_element_count`
- [ ] `harness/__init__.py` re-exports all public names
- [ ] `harness/runner.py` can discover and run test files
- [ ] `.env` / env vars: `BU_CDP_WS`, `BU_NAME`
- [ ] Screenshot on failure works
- [ ] SSH tunnel scenario tested
- [ ] Agent layer (optional): `AppModel`, `TestAuthor`, `SelfHealer`, `CIManager`

That's the whole thing. Nothing more is needed. 😏