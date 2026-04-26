# browser-harness-testing — Design Spec

## Overview

An AI-driven E2E testing system that replaces traditional frameworks (Playwright, Cypress) with an intelligent agent that authors, executes, monitors, and self-heals tests continuously in a CI pipeline.

**Built on:** browser-harness + Python AI agent  
**Target:** SAP Build / SAP UI5 complex applications  
**Goal:** Eliminate test maintenance burden — tests self-heal, the agent monitors, humans approve.

---

## Architecture

```
browser-harness-testing/
├── agent/                      # AI agent service (continuous runner)
│   ├── __init__.py
│   ├── app_model.py           # Learned app knowledge (selectors, patterns, waits)
│   ├── test_author.py         # Natural language → test files
│   ├── self_healer.py         # Failure analysis → fix generation
│   ├── ci_manager.py          # GitHub API: PRs, comments, status checks
│   └── jira_client.py         # JIRA ticket creation (extensible, deferred)
│
├── harness/                   # Enhanced browser-harness
│   ├── __init__.py
│   ├── assertions.py          # assert_visible, assert_text, assert_url, etc.
│   ├── runner.py              # Test execution with artifact capture
│   └── helpers.py            # Extended browser-harness helpers
│
├── tests/                     # Generated test suites (one file per flow)
│   └── .gitkeep
│
├── specs/                     # App specs, page models, agent knowledge
│   └── .gitkeep
│
├── .github/
│   └── workflows/
│       └── test-executor.yml  # CI: runs tests, captures artifacts
│
├── pyproject.toml
└── README.md
```

---

## Core Loop

```
Human: "test the workorder creation flow"
        ↓
Agent (on-demand / onboarding):
  → Explores app via browser-harness
  → Builds app model (learned selectors, patterns, waits)
  → Writes test file → commits to repo

Agent (continuous monitoring):
  → Polls GitHub API for test results (scheduled + webhook-triggered)
  → On failure: analyzes (screenshot + error + page context)
    → If fixable: edits test → opens draft PR with explanation
    → If complex: posts PR comment with diagnosis, flags human
  → Posts pass/fail summary to PR comments
  → Creates JIRA tickets if configured (deferred implementation)
```

---

## Test Authoring

### Input Methods

1. **Natural language** (primary) — Agent receives a task description, writes a test file
2. **Observation** — Agent explores app, records patterns into app model, uses model to write accurate tests
3. **Migration** (future) — Import existing Playwright/Cypress tests

### App Model

- **Global per app** — One model per application under test
- **Stored as:** `specs/<app-name>/app_model.json` — structured, readable, editable by agent
- **Contains:**
  - Selector strategies that work (aria-*, data-testid, role+text combos)
  - Wait patterns and why they're needed
  - URL patterns and expected page structure
  - Component types and typical states
  - Known traps and selectors that don't work

### Output Format

Plain Python files — one file per feature flow:

```python
# tests/checkout_flow.py
from harness import *

def test_checkout_flow():
    goto_url("https://app.example.com/checkout")
    wait_for_load()
    assert_visible("[data-testid='checkout-form']")
    click_at_xy(200, 300)  # Add first item
    assert_text(".item-name", "Widget A")
    # ... more steps
```

### Assertion Library (harness/assertions.py)

```python
def assert_visible(selector, timeout=10)
def assert_text(selector, expected, timeout=10)
def assert_url(pattern, timeout=5)
def assert_not_visible(selector, timeout=5)
def assert_attribute(selector, attr, value)
def assert_element_count(selector, count)
```

All assertions capture a screenshot on failure with context (selector, page URL, error message).

---

## Test Execution

### Runner (harness/runner.py)

Simple `run_tests()` function:
- Sets up browser (connects to existing Chrome via browser-harness)
- Runs test files (one per invocation, or glob pattern)
- Captures artifacts on failure: screenshot, console logs, page HTML
- Reports pass/fail in a simple structured format
- Compatible with GitHub Actions artifact upload

### CI Integration (.github/workflows/test-executor.yml)

- Triggered: on PR, on push to main, on schedule (nightly)
- Runs: `python -m harness.runner tests/`
- Captures: `test-results/` directory as GitHub Actions artifact
- Posts: results summary to PR comment via GitHub API

---

## Agent Service

### Purpose
Runs continuously, monitors CI results, authors and fixes tests autonomously.

### Stack
- Python (same stack as browser-harness)
- browser-harness for app exploration
- GitHub API for CI interaction
- Optional: JIRA API for ticket creation

### Key Modules

**app_model.py**
- Load/save app model from JSON
- Update model with new observations
- Query model for selector strategies when authoring tests

**test_author.py**
- receive natural language task
- consult app model
- write/overwrite test file
- commit to git

**self_healer.py**
- receive failure (screenshot + error + test file)
- analyze root cause (selector stale, assertion wrong, app behavior change)
- generate fix or flag human
- open draft PR with explanation

**ci_manager.py**
- poll GitHub Actions API for run results
- post PR comments with summaries
- create/update PRs with test changes
- manage draft PR lifecycle
- status check updates

### Deployment Modes

1. **Same infra (GitHub Actions)** — Agent runs as a long-running workflow with scheduled dispatch for periodic tasks. Limited to 6-12h runs — fine for periodic tasks, insufficient for true continuous monitoring.

2. **Separate service** — Agent runs as a standalone Python process (container, cloud function, VPS). Calls GitHub API to orchestrate. Both modes use the same API interface — design for this.

**Decision:** The CI manager is designed to work from either context. On GitHub Actions it uses the native context; as a separate service it authenticates via GitHub App or PAT.

---

## CI/CD Design

### GitHub Actions Workflow

```yaml
name: E2E Tests
on:
  push:
    branches: [main]
  pull_request:
  schedule:
    - cron: '0 2 * * *'  # nightly

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install -e .
      - run: python -m harness.runner tests/
      - uses: actions/upload-artifact@v4
        if: failure()
        with:
          name: test-artifacts
          path: test-results/
```

### GitHub Integration Points

- **PR comments:** Agent posts test summaries, failure diagnoses, fix explanations
- **Draft PRs:** Agent opens draft PR when it has a fix, human approves and merges
- **Status checks:** Agent updates commit status (pending → success/failure)
- **Artifacts:** Screenshots, logs, page HTML on failure — stored as Actions artifacts

---

## JIRA Integration (Deferred)

- Design for extensibility: `jira_client.py` has a clean interface
- Deferred until JIRA project and ticket schema are defined
- Agent can create tickets via JIRA API when configured
- Ticket structure: linked to test file, CI run, screenshot, failure diagnosis

---

## Design Principles

1. **Simplicity first** — No extra layers. Plain Python tests, simple runner, GitHub-native reporting.
2. **Agent transparency** — Agent writes human-readable tests, PR descriptions explain what changed and why.
3. **Human in the loop** — All fixes via draft PR, human reviews and merges.
4. **App model as memory** — Agent learns app once, applies that knowledge across all tests.
5. **Failure is informative** — Screenshots captured on every assertion failure, diagnostic context always available.

---

## Self-Healing Logic

| Failure Type | Agent Action |
|---|---|
| Selector stale (element not found) | Analyze page → find new selector → update test |
| Assertion wrong (text changed) | Review expected vs actual → update assertion |
| App behavior changed (flow broken) | Flag human with diagnosis, suggest test update |
| Flaky test (intermittent) | Flag for human review, mark as flaky |
| Infrastructure failure (browser crash) | Retry once, then flag human |

---

## Out of Scope (v1)

- Playwright/Cypress test migration (import tool)
- JIRA ticket implementation
- Test scheduling beyond CI triggers
- Multi-app support (v1 = one app at a time)
- Parallel test execution (v1 = sequential)

---

## Dependencies

- `browser-harness` — base browser control
- `cdp-use` — CDP client (already in browser-harness)
- `PyGithub` — GitHub API access
- Standard library: `json`, `subprocess`, `pathlib`, `asyncio`

---

## File Inventory

| Path | Purpose |
|---|---|
| `agent/__init__.py` | Package marker |
| `agent/app_model.py` | App knowledge base |
| `agent/test_author.py` | NL → test file |
| `agent/self_healer.py` | Failure → fix |
| `agent/ci_manager.py` | GitHub API interface |
| `agent/jira_client.py` | JIRA API (stub / deferred) |
| `harness/__init__.py` | Package marker |
| `harness/assertions.py` | Assertion helpers |
| `harness/runner.py` | Test executor |
| `harness/helpers.py` | Extended browser helpers |
| `tests/` | Generated test files |
| `specs/` | App models, page specs |
| `.github/workflows/test-executor.yml` | CI pipeline |
| `pyproject.toml` | Project config |
| `README.md` | Usage documentation |