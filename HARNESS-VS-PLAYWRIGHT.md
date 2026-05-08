# Browser Harness Architecture: CDP vs Playwright

**Focus:** UI Testing & End-to-End (E2E) Testing | **Date:** May 2026

---

## The Fundamental Truth

**Playwright and CDP are not competitors — Playwright is a consumer of CDP.** Every action Playwright takes inside Chrome ultimately becomes a CDP command. The difference is who writes that CDP command and how much intelligence sits between you and the wire.

```
You → Playwright API → CDP JSON-RPC → Chrome
You → Your code → CDP JSON-RPC → Chrome  (direct)
```

Playwright is a high-level wrapper. The browser-harness is a low-level wrapper. Both sit on CDP. The question is what you get and what you give up by using each.

---

## Side-by-Side Comparison

| Aspect | Your CDP Harness | Playwright |
|--------|-----------------|------------|
| **Browser ownership** | You control the Chrome instance | Playwright manages its own bundled Chromium |
| **Connection initiation** | Chrome must be started with `--remote-debugging-port` | Playwright can launch Chrome for you or connect to existing |
| **Language** | Python | Node.js / Python / Java / .NET |
| **Process model** | Single process, Unix socket bridge | Manages Chromium child processes, isolates contexts |
| **Element interaction** | Raw CDP: `Input.dispatchMouseEvent` or `Runtime.evaluate` | Smart auto-wait, locator strategies, frame handling |
| **Navigation** | `Page.navigate` → poll `document.readyState` | Built-in `page.goto()` with load state detection |
| **Waiting** | Manual sleep / poll | Auto-wait on every action (checks visibility, stability) |
| **Selector strategy** | You write it (CSS, XPath, JS) | Built-in locator strategy (role, text, label) |
| **Multi-context** | Manual via `Target.createBrowserContext` | `browser.newContext()` — isolated, concurrent |
| **Authentication/state** | Manual cookies/storage | `context.add_cookies()` / `storageState()` |
| **Cross-browser** | Chromium only | Chromium + Firefox + WebKit |
| **Maturity** | Your code (~250 lines of Python) | 8+ billion tests worth of battle testing |
| **Speed (raw CDP)** | ~15-20% faster than Playwright on identical tasks | Slightly more overhead per command |
| **Debugging** | CDP events visible, direct | Playwright hides raw CDP unless you enable trace |
| **CI/CD** | You build it | Built-in reporters, GitHub Actions integration |
| **Vendor lock-in** | None — code you own | None — but you're using Playwright's API |
| **Maintenance burden** | You own everything | Playwright maintains the abstraction for you |

---

## What Playwright Actually Does That You Don't Have To Think About

Playwright adds a lot of intelligence automatically:

1. **Auto-wait** — Before every action, Playwright checks if the element is visible, stable, actionable. It retries until conditions are met or timeout. Your harness requires you to call `wait_for_element()` explicitly.

2. **Locator strategies** — Playwright has `page.getByRole()`, `page.getByText()`, `page.getByLabel()` which are more resilient than CSS selectors. Your harness uses CSS directly.

3. **Frame and iframe handling** — Playwright automatically switches to the right frame context when you target an element inside one. Your harness uses `iframe_target()` and manual `switch_tab()`.

4. **Load state detection** — `page.goto(url, wait_until='networkidle')` knows how to wait for network inactivity. Your `wait_for_load()` just checks `document.readyState`.

5. **Soft assertions** — `expect()` with auto-retry. Your assertions fail immediately with a screenshot — which is actually better for debugging, but more brittle in CI.

6. **Built-in tracing** — Playwright can record every action with screenshot/video. You capture on failure only.

7. **Context isolation** — Each `browser.newContext()` is a completely isolated browser session with its own cookies/storage. Your harness shares the user's Chrome session (which is both a feature and a risk).

---

## The Honest Trade-off

| You win with CDP harness | You win with Playwright |
|------------------------|------------------------|
| Direct access to every CDP command | Auto-wait and smart locators |
| No dependency on Playwright's release cycle | Cross-browser (Chromium + Firefox + WebKit) |
| Control over exactly what runs | Battle-tested on 8B+ test runs |
| No child process management | `page.on()` / network interception built-in |
| Zero latency (local socket) | Full API in 5 languages |
| Can drive the user's already-open Chrome | Handles Chromium, Firefox, WebKit |
| Simpler to understand and audit | Mature CI/CD integration |
| Screenshot-on-failure is native | Built-in video, trace, HAR |
| Can see ALL raw CDP events easily | Standardized, documented API |

---

## CDP Approach: The Complete Architecture

The CDP approach is simpler than it seems — five layers, each with one job:

```
┌─────────────────────────────────────────────────────────┐
│  CHROME (running in dev mode)                           │
│  chrome --remote-debugging-port=9222                    │
│  WebSocket server at ws://127.0.0.1:9222                │
│  Or: Chrome Canary with Allow Remote Debugging checked │
└─────────────────────────────────────────────────────────┘
                           │ WebSocket
                           ▼
┌─────────────────────────────────────────────────────────┐
│  BRIDGE LAYER                                           │
│  Translates: JSON-RPC over WebSocket ↔ Unix socket      │
│  Your daemon.py: CDPClient (from cdp_use) → asyncio     │
│  Unix socket at /tmp/bu-<name>.sock                     │
│                                                         │
│  Responsibilities:                                       │
│  - Connect to Chrome's WebSocket endpoint               │
│  - Maintain session ID to the attached tab              │
│  - Route commands and route events                      │
│  - Handle reconnection on session stale                │
│  - Handle dialogs (alert/confirm/prompt)               │
│  - Mark the controlled tab with 🟢 in title             │
└─────────────────────────────────────────────────────────┘
                           │ Unix socket (local process)
                           ▼
┌─────────────────────────────────────────────────────────┐
│  HELPERS LAYER (browser_harness/helpers.py)             │
│  Thin, direct wrappers around CDP commands              │
│                                                         │
│  Navigation:   goto_url(), wait_for_load(), page_info() │
│  Input:        click_at_xy(), type_text(), press_key()  │
│  Visual:       capture_screenshot()                     │
│  JS:           js("expression")                         │
│  Tabs:         list_tabs(), switch_tab(), new_tab()     │
│  Network:      http_get() (bypasses browser)           │
│  Utility:      wait(), drain_events()                   │
│                                                         │
│  Principle: Zero abstraction. CDP command → function.   │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│  UI LAYER (harness/helpers.py)                          │
│  Element-centric helpers built on top of helpers        │
│                                                         │
│  Discovery:   find_element(), get_all_text()            │
│  Visibility:  is_element_visible(), wait_for_element()   │
│               wait_for_element_visible()               │
│  Text/attr:   get_element_text(), get_element_attribute()│
│  Wait:        Polling loops with timeout                │
│  All powered by js() queries against the DOM            │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│  ASSERTION LAYER (harness/assertions.py)                │
│  Tests that fail with screenshot + context             │
│                                                         │
│  assert_visible(selector, timeout)                      │
│  assert_not_visible(selector, timeout)                  │
│  assert_text(selector, expected, timeout)               │
│  assert_url(pattern, timeout)                           │
│  assert_attribute(selector, attr, value, timeout)        │
│  assert_element_count(selector, count, timeout)         │
│                                                         │
│  On failure: capture screenshot, dump page state        │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│  AGENT LAYER (agent/)                                   │
│  Intelligent test generation and maintenance            │
│                                                         │
│  AppModel      — learned app knowledge (selectors,     │
│                  wait patterns, URL structure)          │
│  TestAuthor    — natural language → test code          │
│  SelfHealer    — failure analysis → fix generator       │
│  CIManager     — GitHub PR comments, draft PRs,          │
│                  status checks                          │
│                                                         │
│  This is where the "AI" lives. Everything below is      │
│  pure infrastructure.                                   │
└─────────────────────────────────────────────────────────┘
```

---

## The Five Core Components

### 1. Chrome + Dev Mode

Chrome runs normally with remote debugging enabled. The user logs in, cookies are there, sessions are active. This is the key difference from Playwright's bundled Chromium — you're testing the real user experience, not a fresh profile.

```bash
# Mac (the browser host)
open -a "Google Chrome" --args --remote-debugging-port=9222 \
  --user-data-dir=~/Library/Application\ Support/Google/Chrome

# Or on Linux/Raspberry Pi
google-chrome --remote-debugging-port=9222 \
  --user-data-dir=~/.config/google-chrome
```

The only requirement: Chrome must be open with that flag. The `daemon.py` auto-discovers the WebSocket URL via `DevToolsActivePort` in the Chrome profile directory.

---

### 2. Bridge (daemon.py — ~260 lines)

Handles three things and nothing else:

1. **Connects to Chrome's WebSocket** using `CDPClient` from `cdp_use`
2. **Attaches to the first real page tab** (marks it with 🟢 in title so user can see which tab the agent controls)
3. **Bridges Unix socket ↔ WebSocket** so your Python helpers can send CDP commands as simple JSON over a local socket

The async design matters: `asyncio` handles the WebSocket connection, event routing, and session management concurrently. The `handle()` method routes requests — CDP commands pass through, meta-commands (`drain_events`, `pending_dialog`, `shutdown`) are intercepted.

The session stale logic is important: when Chrome tabs navigate unexpectedly, the session ID can become invalid. The `handle()` method detects `"Session with given id not found"` and re-attaches to the first page automatically.

**This is the only part that touches the WebSocket protocol directly.**

---

### 3. Core Helpers (browser_harness/helpers.py — ~250 lines)

Direct, thin wrappers around CDP commands. No logic, no waiting, no retries. Just:

```python
goto_url(url)                    →  cdp("Page.navigate", url=url)
click_at_xy(x, y)                →  Input.dispatchMouseEvent (press + release)
js("document.title")             →  Runtime.evaluate → return value
capture_screenshot()              →  Page.captureScreenshot → base64 → PNG
wait_for_load()                  →  poll document.readyState == "complete"
```

Everything here is idempotent and explicit. If you call `goto_url()` twice, you navigate twice. No hidden state. No automatic waiting. No magic.

The `BH_DEBUG_CLICKS` env variable turns on click visualization — overlays a red circle on screenshots showing where clicks landed. Useful during development.

---

### 4. UI Helpers (harness/helpers.py — ~140 lines)

Element-centric wrappers built on `js()`. They query the DOM:

```python
find_element(selector)     →  document.querySelector(selector) → {tag, text, attrs, rect, visible}
wait_for_element(selector) →  poll find_element() until found or timeout
is_element_visible(selector) →  find_element() + check rect + visibility CSS
get_element_text(selector) →  find_element() → text
```

Everything here uses CSS selectors directly against the live DOM. If the DOM has `<div data-testid="wo-form">`, you query it. If the dev changed the `data-testid`, the query breaks — this is where `AppModel` knowledge helps, picking alternative selectors that historically survived refactors.

---

### 5. Assertions (harness/assertions.py)

The testing interface. Each assertion:
1. Calls the corresponding helper
2. Checks the condition
3. On failure: captures a screenshot, prints diagnostic context, raises

```python
def assert_visible(selector, timeout=10):
    start = time.time()
    while time.time() - start < timeout:
        if is_element_visible(selector):
            return
        time.sleep(0.3)
    capture_screenshot(f"/tmp/fail_{int(time.time())}.png")
    raise AssertionError(f"Element {selector} not visible after {timeout}s")
```

The screenshot on failure is the debugging gold — you can see exactly what the page looked like when the assertion failed, alongside the full page state (URL, title, scroll position).

---

## The Complete Stack (Local Mode)

```
Chrome (dev mode, debug port 9222)
  └── WebSocket at ws://127.0.0.1:9222/devtools/...
        │
        ▼ CDPClient (asyncio, cdp_use)
        │
   daemon.py (Unix socket bridge)
        │ Unix socket /tmp/bu-default.sock (local to Pi)
        ▼
   Python process (your test, your agent)
        │
        ├─ browser_harness/helpers.py  (cdp wrappers)
        │     goto_url, click_at_xy, js, capture_screenshot, ...
        │
        ├─ harness/helpers.py  (DOM helpers)
        │     find_element, wait_for_element, get_element_text, ...
        │
        ├─ harness/assertions.py  (test assertions)
        │     assert_visible, assert_text, assert_url, ...
        │
        └─ agent/  (AI layer)
              AppModel, TestAuthor, SelfHealer, CIManager
```

All local. No SSH. No tunnel. The Unix socket and the Chrome debug port are both on `127.0.0.1`. Your test runs at near-zero latency.

---

## SSH Complication (The Tunnel)

When you run the harness from your Raspberry Pi but Chrome is on your Mac:

```
[Pi] Python process
   └── Unix socket /tmp/bu-default.sock (local to Pi)
        │
        ▼ SSH tunnel
            └── forward Pi:9222 → Mac:9222
                 │
                 ▼
            Chrome on Mac (dev mode, listening on port 9222)
```

**How it works:** The SSH tunnel forwards TCP connections from a port on your Pi to a port on the Mac. The `daemon.py` running on the Pi thinks it's connecting to `127.0.0.1:9222` locally, but that port is actually forwarded to the Mac's Chrome.

**Complications:**
- Chrome's `DevToolsActivePort` file contains the WebSocket path (e.g., `/devtools/browser/abc123`). This path must be forwarded correctly through the tunnel.
- The WebSocket upgrade happens over this forwarded connection — it works, but Chrome must be configured to allow remote connections (the `--remote-debugging-port` flag handles this).
- Your `get_ws_url()` reads `DevToolsActivePort` from the Mac's Chrome profile directory via the SSH connection, extracts port + path, and constructs the WS URL. That WS URL gets connected through the tunnel.
- If the tunnel drops, the WebSocket connection drops and the daemon needs to reconnect.

**What you gain:** The Pi can drive the Mac's Chrome as if it were local. The Mac user keeps their logged-in Chrome session, cookies, extensions — all intact. Your tests run against the real authenticated state.

**What you lose:** Latency. SSH round-trip adds ~1-5ms per command depending on network. Negligible for most tests, meaningful for high-volume execution.

**Setup command:**
```bash
ssh -L 9222:localhost:9222 user@mac -N
```

---

## What Makes This Robust (vs. Fragile)

The main failure modes and how the architecture handles them:

| Failure | Protection |
|---------|-----------|
| Chrome restarts / tab closes | Session stale detection → re-attach to first page |
| Selector breaks on refactor | AppModel stores fallback selector strategies |
| Page loads slowly | `wait_for_load()` + explicit `wait_for_element()` |
| Dialogs (alert/confirm) block | `pending_dialog` meta-command detects them, `dialog_handler` skill exists |
| Network latency over SSH | Async CDP client handles concurrent operations |
| Chrome update changes CDP | `cdp_use` library updates, your code stays the same |
| Test runs but checks nothing | Assertions only — no silent passes |

The architecture is clean because each layer has exactly one responsibility:
- **Bridge** speaks WebSocket
- **Helpers** speak CDP
- **UI layer** speaks DOM
- **Assertions** speak test language
- **Agent** speaks natural language

---

## Why This Approach Exists

The browser-harness was built because:
1. **Playwright's bundled Chromium is a different browser** than the one users run. Bugs you find in Playwright's Chrome might not exist in the user's actual Chrome (extensions, profile state, GPU settings).
2. **You want the user's logged-in session**, not a fresh profile with no cookies, no auth, no saved state.
3. **You want to own the stack** — no dependency on Playwright's release cycle, no opaque abstraction, no vendor lock-in.
4. **You want direct CDP access** — every command, every event, every response, visible and controllable.
5. **You want to build AI on top** — the agent needs to see raw browser state, not just Playwright's sanitized API.

For teams that want that level of control, the harness approach wins. For teams that want cross-browser coverage and don't want to maintain their own infrastructure, Playwright wins.

Both are valid. This project chose the former. 😏