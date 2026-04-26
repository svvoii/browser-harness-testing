# How to Run Browser Harness Testing

## Prerequisites

1. **Chrome running with remote debugging**
   - **macOS:** Requires `--user-data-dir` flag (Chrome refuses debug mode without a separate profile directory):

     ```bash
     "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
       --remote-debugging-port=9222 \
       --no-first-run \
       --user-data-dir=/tmp/chrome-debug &
     ```

     This creates a temporary debug profile at `/tmp/chrome-debug`. Your normal Chrome profile is untouched.
   - **Linux:** `google-chrome --remote-debugging-port=9222 --no-first-run --user-data-dir=/tmp/chrome-debug &`
   - **Windows:** `"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --no-first-run --user-data-dir=%TEMP%\chrome-debug"`

2. **browser-harness installed locally** (parent project)
   - Assumed at: `/home/molt/projects/browser-harness`
   - If different, adjust `BROWSER_HARNESS_HELPERS_PATH` below

---

## Step 1: Install Dependencies

```bash
cd ~/projects/browser-harness-testing

# Install this package in editable mode (skip deps, we'll install manually)
pip install -e . --no-deps

# Install test dependencies
pip install PyGithub pytest
```

---

## Step 2: Set Environment Variables

```bash
# Tell harness where to find the parent browser-harness helpers
export BROWSER_HARNESS_HELPERS_PATH=/home/molt/projects/browser-harness/helpers.py

# Add browser-harness to Python path so we can import from it
export PYTHONPATH=/home/molt/projects/browser-harness:$PYTHONPATH
```

Add these to your shell profile (~/.zshrc or ~/.bashrc) to make permanent.

---

## Step 3: Verify Installation

```bash
python -c "from harness import *; print('harness import OK')"
python -c "from agent import *; print('agent import OK')"
```

---

## Step 4: Run Tests

### Run all tests
```bash
BROWSER_HARNESS_HELPERS_PATH=/home/molt/projects/browser-harness/helpers.py \
python -m harness.runner tests/
```

### Run a specific test file
```bash
BROWSER_HARNESS_HELPERS_PATH=/home/molt/projects/browser-harness/helpers.py \
python -m harness.runner tests/test_example.py
```

### Run with pytest (if tests are pytest-style)
```bash
BROWSER_HARNESS_HELPERS_HELPERS_PATH=/home/molt/projects/browser-harness/helpers.py pytest tests/
```

---

## Writing a Test

Create a file in `tests/` directory:

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
python -m harness.runner tests/test_my_flow.py
```

---

## Testing with SAP Build (Trial Account)

1. **Get a SAP Build trial** at [sap.com](https://www.sap.com) → SAP Build → try for free

2. **Start Chrome** with remote debugging (requires `--user-data-dir`):
   ```bash
   "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
     --remote-debugging-port=9222 \
     --no-first-run \
     --user-data-dir=/tmp/chrome-debug &
   ```

3. **Navigate to your SAP Build app** in the Chrome window that opens

4. **Test basic navigation** with browser-harness first:
   ```bash
   cd /home/molt/projects/browser-harness
   browser-harness <<'PY'
   goto_url("https://your-sap-build-url")
   wait_for_load()
   print(page_info())
   PY
   ```

5. **Test with browser-harness-testing assertions**:
   ```bash
   cd /home/molt/projects/browser-harness-testing
   BROWSER_HARNESS_HELPERS_PATH=/home/molt/projects/browser-harness/helpers.py \
   python <<'PY'
   from harness import *

   goto_url("https://your-sap-build-url")
   wait_for_load()
   assert_visible("body")  # adjust selector for your app
   print(page_info())
   PY
   ```

---

## Architecture Overview

```
browser-harness-testing/
├── harness/                    # Enhanced layer (your code)
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
└── tests/                      # your test files

Parent dependency:
└── browser-harness/            # provides base CDP helpers
    └── helpers.py             # goto_url, click_at_xy, etc.
```

---

## Troubleshooting

### "Module not found" errors
- Ensure `PYTHONPATH` includes the browser-harness directory
- Ensure `BROWSER_HARNESS_HELPERS_PATH` points to the correct helpers.py

### Chrome connection refused
- Make sure Chrome is running with `--remote-debugging-port=9222`
- Visit `chrome://inspect` to verify Chrome is listening

### Import errors with harness
```bash
# Verify path is set correctly
echo $BROWSER_HARNESS_HELPERS_PATH
# Should print: /home/molt/projects/browser-harness/helpers.py

# Test direct import
python -c "import sys; sys.path.insert(0, '/home/molt/projects/browser-harness'); import helpers; print('OK')"
```

### Tests not running
```bash
# Check test files exist
ls tests/

# Verify runner works
BROWSER_HARNESS_HELPERS_PATH=/home/molt/projects/browser-harness/helpers.py \
python -m harness.runner tests/ -v
```

---

## GitHub Actions CI

The `.github/workflows/test-executor.yml` runs tests on:
- Every PR
- Every push to main
- Nightly at 2am UTC

No additional setup needed — GitHub Actions handles environment automatically.