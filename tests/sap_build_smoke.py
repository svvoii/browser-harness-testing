"""SAP Build smoke tests — browser-harness-testing.

Prerequisites:
  - Chrome running with --remote-debugging-port=9222 (or SSH tunnel active)
  - SAP Build credentials in .env (BUILD_LOBBY, USER, PASSWORD)
  - uv sync && uv run python -m pytest tests/sap_build_smoke.py

Run:
  cd ~/projects/browser-harness-testing
  uv run python -m pytest tests/sap_build_smoke.py -v
  # or without pytest:
  uv run python -m harness.runner tests/sap_build_smoke.py
"""

import os
import time

# Load credentials from .env
_env = {}
with open(".env") as f:
    for line in f:
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            _env[k] = v.strip()

BUILD_LOBBY = _env.get("BUILD_LOBBY", "")
USER        = _env.get("USER", "")
PASSWORD    = _env.get("PASSWORD", "")


def _load_env():
    """Ensure daemon sees .env."""
    from pathlib import Path
    env_path = Path(__file__).parent.parent / ".env"
    if not env_path.exists():
        return
    from browser_harness.admin import _load_env as admin_load
    admin_load()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fill_login(username, password):
    """Fill and submit SAP login form."""
    from harness import js
    from browser_harness.helpers import press_key

    js(f"""
    (function() {{
      var u = document.querySelector('#j_username');
      var p = document.querySelector('#j_password');
      if (u) u.value = {repr(username)};
      if (p) p.value = {repr(password)};
    }})()
    """)
    press_key("Enter")


def _is_logged_in():
    """Check if currently on the lobby page."""
    from harness import js
    url = js("location.href")
    return "/lobby" in url and "sign" not in url.lower()


def _need_login():
    """Check if redirected to SAP login page."""
    from harness import js
    return "sap-build" in js("location.href") and (
        "sign" in js("location.href").lower()
        or js("document.querySelector('#j_username')") is not None
    )


# ---------------------------------------------------------------------------
# Fixtures / setup
# ---------------------------------------------------------------------------

def setup_module():
    """Ensure logged into SAP Build lobby before any test runs."""
    from harness import ensure_daemon, goto_url, wait_for_load, js

    _load_env()
    ensure_daemon(wait=15.0)
    goto_url(BUILD_LOBBY)
    time.sleep(2)

    if _need_login():
        _fill_login(USER, PASSWORD)
        time.sleep(6)

    if _need_login():
        raise RuntimeError("Login failed — check credentials in .env")

    print(f"\nLogged in. URL: {js('location.href')}")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_lobby_page_loads():
    """Verify lobby URL and title."""
    from harness import js
    url   = js("location.href")
    title = js("document.title")
    assert "/lobby" in url,        f"Expected /lobby in URL, got: {url}"
    assert "SAP Build" in title,   f"Expected 'SAP Build' in title, got: {title}"


def test_lobby_heading():
    """Verify main heading is present."""
    from harness import js
    heading = js("document.querySelector('h1, h2')?.innerText")
    assert heading, "No heading found on lobby page"


def test_nav_tabs_present():
    """Verify key navigation tabs are visible."""
    from harness import js
    nav_links = js("""
    (function() {
      return Array.from(document.querySelectorAll("a[href]"))
        .filter(a => a.hostname.includes("build.cloud.sap"))
        .map(a => a.innerText.trim())
        .filter(Boolean);
    })()
    """) or []
    nav_lower = [n.lower() for n in nav_links]
    for tab in ["actions", "events", "lobby"]:
        found = any(tab in n for n in nav_lower)
        assert found, f"Nav tab '{tab}' not found in: {nav_links}"


def test_welcome_message_visible():
    """Verify the welcome message or quick-start section is present."""
    from harness import js
    welcome = js("""
    (function() {
      var el = document.querySelector('[class*="welcome"], h1, h2');
      return el ? el.innerText.trim() : null;
    })()
    """)
    assert welcome, "No welcome/heading element found"


def test_all_projects_section():
    """Verify 'All Projects' section exists and has items."""
    from harness import js
    projects = js("""
    (function() {
      return Array.from(document.querySelectorAll('h1,h2,h3,h4')).
        map(h => h.innerText.trim()).filter(Boolean);
    })()
    """) or []
    found = any("all projects" in p.lower() or "projects" in p.lower() for p in projects)
    assert found, f"'All Projects' heading not found in: {projects}"


def test_quick_start_section():
    """Verify Quick Start / Learning Journeys section is present."""
    from harness import js
    qs = js("""
    (function() {
      return Array.from(document.querySelectorAll('h1,h2,h3,h4,a')).
        map(el => el.innerText.trim()).filter(Boolean);
    })()
    """) or []
    found = any("quick" in s.lower() or "learning" in s.lower() for s in qs)
    assert found, f"Quick Start / Learning section not found"


def test_screenshot_on_lobby():
    """Capture a screenshot of the lobby for visual verification."""
    from harness import capture_screenshot
    path = capture_screenshot("/tmp/sap-build-lobby-smoke.png")
    assert path, "Screenshot capture returned empty path"
    print(f"\nScreenshot saved: {path}")


if __name__ == "__main__":
    # Allow running directly without pytest
    setup_module()
    for name, fn in [(n, f) for n, f in vars().items() if n.startswith("test_") and callable(f)]:
        print(f"\nRunning {name}...")
        fn()
        print(f"PASS: {name}")
