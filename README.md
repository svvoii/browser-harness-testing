# Browser Harness Testing

AI-driven E2E testing system built on top of `browser_harness` — the CDP WS bridge and helpers that drive Chrome via the Chrome DevTools Protocol.

## Overview

An intelligent testing agent that:
- Authors tests from natural language descriptions
- Learns app patterns and stores them in an app model
- Self-heals failing tests by analyzing failures and generating fixes
- Posts results to GitHub PRs and opens draft PRs for human review

## Architecture

```
browser-harness-testing/              ← single unified project
├── browser_harness/                  # CDP WS bridge + helpers (formerly separate repo)
│   ├── admin.py                      # daemon lifecycle
│   ├── daemon.py                      # CDP WS ↔ Unix socket bridge
│   ├── helpers.py                     # CDP client (goto_url, click, js, etc.)
│   ├── run.py                         # CLI entry point
│   ├── domain-skills/                 # learned agent skills
│   └── interaction-skills/            # browser interaction skills
│
├── harness/                          # SAP Build UI testing layer
│   ├── __init__.py                  # re-exports: CDP helpers + UI helpers + assertions
│   ├── assertions.py                 # UI testing assertions
│   ├── helpers.py                    # UI helpers: find_element, wait_for_element, etc.
│   └── runner.py                     # Test executor with artifact capture
│
├── agent/                            # AI agent modules (future)
│   ├── app_model.py
│   ├── test_author.py
│   ├── self_healer.py
│   └── ci_manager.py
│
├── tests/                             # Test files (one per flow)
├── specs/                             # App models, page specs
└── .github/workflows/
    └── test-executor.yml
```

## Installation

```bash
cd ~/projects/browser-harness-testing
uv sync
```

The `browser-harness` CLI is installed automatically as part of the local package.

## Writing Tests

Create test files in `tests/` directory:

```python
from harness import *

def test_workorder_creation():
    goto_url("https://app.example.com/workorder/create")
    wait_for_load()
    assert_visible("[data-testid='wo-form']")
    click_at_xy(200, 300)
    assert_text(".item-name", "Widget A")
```

## Running Tests

```bash
# Run all tests
uv run python -m harness.runner tests/

# Run single test file
uv run python -m harness.runner tests/test_example.py

# Exploratory testing with the browser-harness CLI
uv run browser-harness <<'PY'
goto_url("https://example.com")
wait_for_load()
print(page_info())
PY
```

## Assertions

Available assertion helpers:
- `assert_visible(selector, timeout=10)` — element visible
- `assert_not_visible(selector, timeout=5)` — element hidden
- `assert_text(selector, expected, timeout=10)` — element text matches
- `assert_url(pattern, timeout=5)` — URL matches pattern
- `assert_attribute(selector, attr, value, timeout=10)` — attribute equals value
- `assert_element_count(selector, count, timeout=10)` — element count matches

All assertions capture a screenshot on failure with diagnostic context.

## AI Test Authoring

```python
from agent import TestAuthor, AppModel, CIManager

# Load app model (learned selector strategies, wait patterns)
app_model = AppModel("sap-build")
app_model.load()

# Create test author with CI manager
ci = CIManager()
author = TestAuthor(app_model, ci)

# Write test from natural language
author.write_test("test workorder creation flow with valid data")
```

## App Model

The app model stores learned knowledge about the application:
- Selector strategies (what works for this app)
- Wait patterns and why they're needed
- URL patterns and expected page structure
- Known traps (selectors that don't work)

Stored in `specs/<app-name>/app_model.json`.

## Self-Healing

When a test fails, SelfHealer analyzes the failure:

| Failure Type | Action |
|---|---|
| Selector stale | Find new selector, update test, open draft PR |
| Assertion wrong | Update assertion with correct expected value |
| App behavior changed | Flag human with diagnosis |
| Flaky test | Flag human for review |
| Infrastructure failure | Retry once, then flag human |

## CI/CD

Tests run on GitHub Actions:
- On every PR
- On push to main
- Nightly at 2am UTC

Results are posted as PR comments. Failed tests open draft PRs with suggested fixes for human review.

## Environment Variables

| Variable | Purpose |
|---|---|
| `BU_CDP_WS` | Chrome CDP WebSocket URL (default: auto-discovered) |
| `BU_NAME` | Daemon name (default: default, use `browser-harness-testing` for this project) |
| `GITHUB_TOKEN` | GitHub API access for PR comments and PRs |
| `GH_TOKEN` | Alternative to GITHUB_TOKEN |
| `GITHUB_REPOSITORY` | Owner/repo for CI manager (auto-detected in CI) |

## Project Structure Details

### browser_harness/ (CDP core)

**admin.py** — Daemon lifecycle (ensure_daemon, restart_daemon, run_doctor, run_setup)
**daemon.py** — CDP WebSocket ↔ Unix socket bridge
**helpers.py** — CDP client helpers: goto_url, click_at_xy, js, wait, wait_for_load, page_info, list_tabs, new_tab, switch_tab, capture_screenshot, http_get, etc.
**run.py** — CLI entry point (`browser-harness` command)

### harness/ (UI testing layer)

**__init__.py** — Re-exports everything from both browser_harness and local modules
**assertions.py** — UI testing assertions with screenshot-on-failure
**helpers.py** — UI helpers: find_element, wait_for_element, get_element_text, is_element_visible, etc.
**runner.py** — Test executor with artifact capture

### agent/

**app_model.py** — App knowledge base (JSON read/write, selector lookup)
**ci_manager.py** — GitHub API client (runs, comments, PRs, status checks)
**test_author.py** — Natural language → test file writer
**self_healer.py** — Failure analysis → fix generator

## Extending

To add a new helper function, edit `harness/helpers.py`.
To add a new assertion, edit `harness/assertions.py`.
To extend the agent, add methods to the appropriate agent module.
