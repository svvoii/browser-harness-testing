# How to Run Browser Harness Testing

This guide explains **how the browser connection works end-to-end**, then gives you **step-by-step setup** for both the two-machine workflow (Pi = testing agent, Mac = browser host) and the single-machine Mac workflow.

---

## Part 1: How the Browser Actually Works

### The Stack (3 layers)

```
┌─────────────────────────────────────────────────────────────┐
│  YOUR TEST / AGENT CODE                                     │
│  harness/runner.py  or  helpers.py (browser-harness)       │
│         │                                                   │
│         │ talks to                                          │
│         ▼                                                   │
│  /tmp/bu-{NAME}.sock  (Unix domain socket, local machine)  │
│         │                                                   │
│         │ managed by                                       │
│         ▼                                                   │
│  daemon.py  (long-lived Python background process)          │
│         │                                                   │
│         │ connects via WebSocket                           │
│         ▼                                                   │
│  Chrome DevTools Protocol (CDP)  ←── Chrome with --remote-debugging-port=9222 │
└─────────────────────────────────────────────────────────────┘
```

**Layer 1 — Your code** (`helpers.py`, `harness/runner.py`):
Calls functions like `goto_url()`, `click_at_xy()`, `page_info()`. These are thin wrappers that send JSON messages over a Unix socket.

**Layer 2 — The Unix socket** (`/tmp/bu-{NAME}.sock`):
A local IPC mechanism. Your code and the daemon live on the same machine, so they communicate via this socket — no network needed.

**Layer 3 — The daemon** (`daemon.py`):
A persistent background process. It holds the actual WebSocket connection to Chrome. There is one daemon per `BU_NAME` (default: `default`). The daemon is started automatically by `ensure_daemon()` when your first call needs it.

**Layer 4 — Chrome**:
Chrome exposes a **CDP WebSocket endpoint** at `ws://localhost:9222/...`. The daemon connects to this. Chrome itself must be launched with `--remote-debugging-port=9222` so it listens for incoming CDP connections.

### Key insight: Why a daemon?

Because Chrome's CDP WebSocket is a persistent, stateful connection that speaks a specific binary protocol. Wrapping it in a daemon lets multiple callers share one Chrome session and lets the daemon recover from Chrome restarts transparently.

### How `BU_CDP_WS` works

Chrome's CDP WebSocket URL normally lives at `http://localhost:9222/json/version`. When you `curl` that endpoint, you get:

```json
{
  "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/browser/..."
}
```

If Chrome is **local** to the harness machine, `daemon.py` auto-discovers this by reading `DevToolsActivePort` (a file Chrome writes to `--user-data-dir=/tmp/chrome-debug/`) and constructing the WebSocket URL itself. No configuration needed.

If Chrome is **remote** (different machine), you must tell `daemon.py` the WebSocket URL explicitly via `BU_CDP_WS`. The daemon connects to it regardless of whether it starts with `ws://127.0.0.1` or `ws://<remote-IP>`. **The connection always originates from the machine running daemon.py** — so if the daemon is on Pi and `BU_CDP_WS=ws://localhost:9222/...`, you need the Pi to have an SSH tunnel forwarding that port from the Mac to the Pi.

### Chrome Remote Debugging Port Mechanics

When Chrome starts with `--remote-debugging-port=9222`:
- Chrome listens on **port 9222** for HTTP requests (the `/json/version` endpoint and friends)
- Chrome writes a `DevToolsActivePort` file into `--user-data-dir` containing the port number and the WebSocket path
- Any process on the **same machine** can read that file and connect to Chrome's WebSocket
- **No other machine can directly reach that port** unless forwarded (hence the SSH tunnel for Pi→Mac)

---

## Part 2: Two-Machine Setup (Pi = Test Runner, Mac = Browser)

### Overview

```
┌─────────────────────────┐          ┌─────────────────────────┐
│  RASPBERRY PI           │          │  MAC (HOST)             │
│                         │          │                         │
│  browser-harness-testing│          │  Chrome with:           │
│  ├── harness/           │  SSH     │  --remote-debugging-port│
│  ├── tests/             │  TUNNEL  │  =9222                  │
│  daemon.py(auto-spawned)│◄────────►│  listening on port 9222 │
│                         │          │                         │
│  /tmp/bu-default.sock   │          │  curl http://localhost: │
│  (Unix socket, Pi-local)│          │  9222/json/version      │
└─────────────────────────┘          └─────────────────────────┘
         ▲                                     │
         │                                     │
         │          BU_CDP_WS=                 │
         └─────────────────────────────────────┘
         (WS URL of Mac's Chrome, forwarded
          through SSH tunnel to Pi's localhost:9222)
```

**What runs where:**
- **Pi**: Everything. The test code, the `daemon.py` process, the Unix socket. Chrome itself does NOT run on Pi.
- **Mac**: Chrome browser only, with remote debugging enabled.

**The SSH tunnel** (`ssh -L 9222:localhost:9222 user@mac`):
Maps Mac's port 9222 (where Chrome is listening) to Pi's port 9222. From the Pi's perspective, `localhost:9222` is Mac's Chrome. The daemon on Pi connects to `ws://localhost:9222/...` — exactly as if Chrome were local.

### Step-by-Step

#### Step 1: On Mac — Enable Remote Login

Chrome can only be reached from the Mac itself. The Pi cannot directly see the Mac's localhost. The bridge is SSH.

1. **System Settings → Sharing → Remote Login → ON**
2. Note your Mac's local IP (e.g. `192.168.1.80`) and your Mac username
3. Verify with: `ssh user@192.168.1.80 echo "ok"` from another machine on the same network

#### Step 2: On Mac — Start Chrome with Debug Port

You need a Chrome profile dedicated to testing (not your normal browsing profile):

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --remote-debugging-port=9222 \
  --no-first-run \
  --user-data-dir=/tmp/chrome-debug
```

Or if you have an existing test profile:

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --remote-debugging-port=9222 \
  --no-first-run \
  --user-data-dir=/tmp/chrome-debug-test
```

**What to expect:**
- Chrome starts normally. The `--user-data-dir=/tmp/...` means it uses a separate profile, not your regular one.
- Chrome listens on port 9222 for CDP connections.
- The `DevToolsActivePort` file is created at `/tmp/chrome-debug/DevToolsActivePort`.

**Verify on Mac:**
```bash
curl http://localhost:9222/json/version
```
You should get JSON including `"webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/browser/..."`.

#### Step 3: On Pi — Create SSH Tunnel

Open a terminal on Pi and run:

```bash
ssh -L 9222:localhost:9222 your_mac_username@192.168.1.80 -N

# ssh -L 9222:localhost:9222 serge@192.168.1.80 -N
```

- `-L 9222:localhost:9222` means "forward Pi's port 9222 to the Mac's localhost:9222"
- `-N` means "don't execute a remote command" (just hold the tunnel open)
- Keep this terminal **open** for as long as you want to run tests

**What this actually does:**
```
Pi port 9222 ──────────────────────────────────► Mac port 9222
(tunnel entry)                    (tunnel exit, Mac localhost)
```
When the daemon on Pi connects to `localhost:9222`, the SSH tunnel forwards that connection to the Mac, which then hits Chrome's CDP listener.

**Multiple terminal sessions?**
Each new SSH tunnel creates a new connection to the Mac's SSH daemon. This is fine for testing — Chrome only has one CDP listener on port 9222, but multiple WebSocket clients can connect to it.

**SSH key authentication:**
Add your Pi's public key to Mac's `~/.ssh/authorized_keys` so you don't need a password every time. Look up "SSH key-based authentication" for your OS — it's standard.

#### Step 4: On Pi — Configure the Environment

Create/edit `~/projects/browser-harness-testing/.env`:

```bash
# === Chrome Connection ===
# The SSH tunnel forwards Mac's Chrome CDP to Pi's localhost:9222.
# BU_CDP_WS is set explicitly to the WebSocket URL from the Mac.
# (Get it with: curl http://localhost:9222/json/version on the Mac)
BU_CDP_WS=ws://localhost:9222/devtools/browser/YOUR_WEB_SOCKET_ID

# === Daemon Name ===
# Use a separate daemon name so it doesn't conflict with any other
# browser-harness session on the Pi.
BU_NAME=browser-harness-testing

# === GitHub (for CI manager) ===
# GITHUB_TOKEN=***
# GITHUB_REPOSITORY=svvoii/browser-harness-testing
```

**Note:** `browser_harness/` is now a subpackage of `browser-harness-testing/` — no `BROWSER_HARNESS_HELPERS_PATH` needed.

#### Step 5: On Pi — Install Dependencies

```bash
cd ~/projects/browser-harness-testing
uv sync
source .venv/bin/activate
```

#### Step 6: On Pi — Verify Connection

With the SSH tunnel active in one terminal:

```bash
cd ~/projects/browser-harness-testing
source .venv/bin/activate

python -c "from harness import *; print('harness import OK')"
python -c "from agent import *; print('agent import OK')"
```

Then a live browser test:

```bash
uv run python -c "
from harness import ensure_daemon, goto_url, page_info, wait_for_load
print('Starting daemon...')
ensure_daemon()
print('Daemon started. Navigating...')
goto_url('https://example.com')
wait_for_load()
print(page_info())
"
```

If this prints `{'url': ..., 'title': 'Example Domain', ...}` — the tunnel and Chrome are working.

#### Step 7: On Pi — Run Tests

```bash
cd ~/projects/browser-harness-testing
source .venv/bin/activate
uv run python -m harness.runner tests/
```

---

## Part 3: Single-Machine Setup (Mac as both Browser + Test Runner)

Use this when you want to run tests directly on your Mac without involving the Pi.

**No separate clone needed** — `browser_harness/` is already inside `browser-harness-testing/`.

### Step 1: Start Chrome with Debug Port

Same as above:

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --remote-debugging-port=9222 \
  --no-first-run \
  --user-data-dir=/tmp/chrome-debug
```

### Step 2: Configure

In `~/projects/browser-harness-testing/.env`:

```bash
# === Chrome Connection ===
# No SSH tunnel needed — Chrome is local.
# daemon.py auto-discovers via DevToolsActivePort.
# BU_CDP_WS is intentionally unset.

# === Daemon Name ===
BU_NAME=browser-harness-testing

# === GitHub ===
# GITHUB_TOKEN=***
# GITHUB_REPOSITORY=svvoii/browser-harness-testing
```

### Step 3: Run Tests

```bash
cd ~/projects/browser-harness-testing
uv sync
source .venv/bin/activate
uv run python -m harness.runner tests/
```

---

## Part 4: Testing with SAP Build

1. **Get a trial:** [sap.com](https://www.sap.com) → SAP Build → try for free

2. **Log into SAP Build** in the Chrome profile you've set up for testing

3. **Run a test:**
   ```bash
   cd ~/projects/browser-harness-testing
   source .venv/bin/activate
   uv run python -m harness.runner tests/
   ```

4. **Or use the browser-harness CLI directly** for exploratory testing:
   ```bash
   cd ~/projects/browser-harness-testing
   uv run browser-harness <<'PY'
   goto_url("https://your-tenant.launchpad.sap.com")
   wait_for_load()
   print(page_info())
   PY
   ```

---

## Part 5: Troubleshooting

### "Connection refused" on Pi when tunnel is running

- Verify the tunnel is active: run `curl http://localhost:9222/json/version` **on the Pi** (not the Mac). If it fails, the tunnel is down.
- On Mac, verify Chrome is running with debug port: `curl http://localhost:9222/json/version` on Mac.
- Check SSH tunnel is pointing to the right Mac IP.
- Some corporate networks block SSH between devices — you may need to be on the same WiFi or use a VPN.

### Daemon won't start ("already running")

```bash
# Stop any existing daemon
uv run python -c "from admin import restart_daemon; restart_daemon()"
```

Or manually:
```bash
kill $(cat /tmp/bu-browser-harness-testing.pid)
rm -f /tmp/bu-browser-harness-testing.sock /tmp/bu-browser-harness-testing.pid
```

### Chrome profile picker keeps appearing

The debug Chrome profile (with `--user-data-dir=/tmp/chrome-debug`) is separate from your normal profile. If you want to reuse your existing SAP login, copy your normal profile's User Data to the debug directory, or start Chrome with `--user-data-dir=/tmp/chrome-debug` pointing at your actual profile folder (found in `~/Library/Application Support/Google/Chrome/`).

### `.env` not loaded

Always use `uv run` or activate the venv with `source .venv/bin/activate`. Plain `python` won't source `.env`.

### "Usage: browser-harness -c ..."

The `browser-harness` CLI requires `-c` to pass code inline. Always wrap:
```bash
uv run browser-harness <<'PY'
print(page_info())
PY
```

---

## Architecture Reference

```
browser-harness-testing/          ← single unified project
├── browser_harness/              # CDP WS bridge + helpers (formerly separate repo)
│   ├── admin.py                  # daemon lifecycle (start/stop/restart)
│   ├── daemon.py                  # CDP WS ↔ Unix socket bridge
│   ├── helpers.py                 # CDP client (goto_url, click_at_xy, etc.)
│   ├── run.py                     # CLI entry point (browser-harness command)
│   ├── domain-skills/            # learned agent skills
│   ├── interaction-skills/        # browser interaction skills
│   ├── pyproject.toml             # package build config
│   └── openstreetmap/             # domain knowledge (scraping, etc.)
│
├── harness/                       # our SAP Build UI testing layer
│   ├── __init__.py               # re-exports: core CDP helpers + UI helpers + assertions
│   ├── helpers.py                # UI helpers: find_element, wait_for_element, etc.
│   ├── assertions.py             # assert_visible, assert_text, assert_url, etc.
│   └── runner.py                 # test executor, artifact capture
│
├── agent/                         # AI agent modules (future)
│   ├── app_model.py
│   ├── test_author.py
│   ├── self_healer.py
│   └── ci_manager.py
│
├── tests/                         # test files
├── .env                           # environment variables
├── pyproject.toml                 # uv project config
└── .github/workflows/test-executor.yml
```

---

## GitHub Actions CI

The `.github/workflows/test-executor.yml` runs tests on:
- Every PR
- Every push to main
- Nightly at 2am UTC

No additional setup needed — GitHub Actions handles the environment automatically. For local CI runs, use `uv run python -m harness.runner tests/`.
