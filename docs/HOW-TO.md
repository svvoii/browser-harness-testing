# How to Run Browser Harness Testing

## Prerequisites

### Chrome with Remote Debugging

**macOS:**
```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --remote-debugging-port=9222 \
  --no-first-run \
  --user-data-dir=/tmp/chrome-debug &
```

**Linux:**
```bash
google-chrome --remote-debugging-port=9222 --no-first-run --user-data-dir=/tmp/chrome-debug &
```

**Verify Chrome is listening:**
```bash
curl http://localhost:9222/json/version
```

---

## Step 1: Install Dependencies with uv

```bash
cd ~/projects/browser-harness-testing

# Create venv and install dependencies
uv sync

# Activate venv
source .venv/bin/activate
```

---

## Step 2: Configure Environment (.env)

Create `~/projects/browser-harness-testing/.env`:

```bash
# === Chrome Connection ===
# Local: ws://localhost:9222/...
# Remote (SSH tunnel): ws://localhost:9222/... (from curl http://localhost:9222/json/version)
BU_CDP_WS=ws://localhost:9222/devtools/browser/YOUR_WEB_SOCKET_ID

# === Paths ===
BROWSER_HARNESS_HELPERS_PATH=/home/molt/projects/browser-harness/helpers.py

# === GitHub (for CI manager) ===
# GITHUB_TOKEN=your_token_here
# GITHUB_REPOSITORY=svvoii/browser-harness-testing
```

The `.env` file is automatically loaded when you use `uv run` or activate the venv.

**To get the WebSocket URL:** On Mac, run `curl http://localhost:9222/json/version` and copy the `webSocketDebuggerUrl` value.

---

## Step 3: Verify Installation

```bash
cd ~/projects/browser-harness-testing
source .venv/bin/activate

python -c "from harness import *; print('harness import OK')"
python -c "from agent import *; print('agent import OK')"
```

---

## Step 4: Run Tests

```bash
cd ~/projects/browser-harness-testing
source .venv/bin/activate

uv run python -m harness.runner tests/
```

---

## Writing a Test

Create a file in `tests/`:

```python
from harness import *

def test_my_flow():
    goto_url("https://example.com")
    wait_for_load()
    assert_visible("body")
    print("Test passed!")
```

Run it:
```bash
uv run python -m harness.runner tests/test_my_flow.py
```

---

## Remote Browser via SSH Tunnel

If Chrome runs on a different machine (e.g., macOS) than the harness (Pi):

**1. On Mac — Start Chrome with debug port** (see Prerequisites above)

**2. On Mac — Enable Remote Login:**
System Settings → Sharing → Remote Login → ON

**3. On Pi — Create SSH tunnel:**
```bash
ssh -L 9222:localhost:9222 your_mac_username@192.168.1.80
```

**4. On Pi — Get WebSocket URL from Mac:**
```bash
curl http://localhost:9222/json/version
```
Copy the `webSocketDebuggerUrl` value and update `BU_CDP_WS` in `.env`

**5. On Pi — Run tests:**
```bash
cd ~/projects/browser-harness-testing
source .venv/bin/activate
uv run python -m harness.runner tests/
```

---

## Testing with SAP Build

1. **Get trial:** [sap.com](https://www.sap.com) → SAP Build → try for free

2. **Start Chrome with debug mode** (see Prerequisites)

3. **Update `.env`:**
   ```bash
   BU_CDP_WS=ws://localhost:9222/devtools/browser/YOUR_WEB_SOCKET_ID
   ```

4. **Run a test:**
   ```bash
   cd ~/projects/browser-harness-testing
   source .venv/bin/activate
   uv run python -m harness.runner tests/
   ```

---

## Architecture

```
browser-harness-testing/
├── harness/                    # Enhanced layer
│   ├── assertions.py          # assert_visible, assert_text, etc.
│   ├── helpers.py             # imports from parent + UI helpers
│   └── runner.py              # test executor
│
├── agent/                      # AI agent (future)
│   ├── app_model.py           # learned app patterns
│   ├── test_author.py         # NL → test file
│   ├── self_healer.py         # failure → fix
│   └── ci_manager.py          # GitHub API
│
├── tests/                      # test files
├── .env                        # environment variables
└── pyproject.toml             # uv project config
```

---

## Troubleshooting

### Chrome connection refused
- Make sure Chrome is running with `--remote-debugging-port=9222 --user-data-dir=/tmp/chrome-debug`
- If using SSH tunnel, verify it's active: `curl http://localhost:9222/json/version`

### "Usage: browser-harness -c ..." error
Use `uv run`:
```bash
uv run browser-harness <<'PY'
print(page_info())
PY
```

### .env not loaded
Make sure you're using `uv run` or have activated the venv with `source .venv/bin/activate`

---

## GitHub Actions CI

The `.github/workflows/test-executor.yml` runs tests on:
- Every PR
- Every push to main
- Nightly at 2am UTC

No additional setup needed — GitHub Actions handles environment automatically.