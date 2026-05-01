"""Assertion helpers for UI testing — captures screenshot on failure."""

import re
import time
from pathlib import Path

from browser_harness.helpers import capture_screenshot, js, wait_for_load

RESULTS_DIR = Path("test-results")


def _screenshot_path(selector: str) -> Path:
    """Generate screenshot path for a failed assertion."""
    RESULTS_DIR.mkdir(exist_ok=True)
    safe = re.sub(r"[^a-zA-Z0-9]", "_", selector)
    ts   = int(time.time() * 1000)
    return RESULTS_DIR / f"failed_{safe}_{ts}.png"


def _page_url() -> str:
    """Get current page URL."""
    try:
        return js("location.href") or ""
    except Exception:
        return ""


def _element_visible(selector: str) -> bool:
    """Check if element is visible via JS."""
    return js(
        f"!!(document.querySelector({repr(selector)})?.offsetParent !== null)"
    ) is True


def _count_matching(selector: str) -> int:
    """Count elements matching selector."""
    return int(js(f"document.querySelectorAll({repr(selector)}).length") or 0)


def assert_visible(selector: str, timeout: float = 10) -> None:
    """Wait for element to be visible; fail with screenshot if not found or not visible."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        count = _count_matching(selector)
        if count > 0 and _element_visible(selector):
            return
        time.sleep(0.2)

    page_url = _page_url()
    try:
        path = capture_screenshot(str(_screenshot_path(selector)))
    except Exception as e:
        path = f"<screenshot unavailable: {e}>"

    raise AssertionError(
        f"Assertion failed: element not visible. Selector: {selector}. Page: {page_url}. Screenshot: {path}"
    )


def assert_not_visible(selector: str, timeout: float = 5) -> None:
    """Wait for element to be hidden or removed."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        count = _count_matching(selector)
        if count == 0 or not _element_visible(selector):
            return
        time.sleep(0.2)

    page_url = _page_url()
    try:
        path = capture_screenshot(str(_screenshot_path(selector)))
    except Exception as e:
        path = f"<screenshot unavailable: {e}>"

    raise AssertionError(
        f"Assertion failed: element still visible. Selector: {selector}. Page: {page_url}. Screenshot: {path}"
    )


def assert_text(selector: str, expected: str, timeout: float = 10) -> None:
    """Wait for element text to match expected value."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        count = _count_matching(selector)
        if count > 0:
            actual = js(f"document.querySelector({repr(selector)})?.textContent?.trim()")
            if actual == expected:
                return
        time.sleep(0.2)

    page_url = _page_url()
    try:
        path = capture_screenshot(str(_screenshot_path(selector)))
    except Exception as e:
        path = f"<screenshot unavailable: {e}>"

    actual = (
        js(f"document.querySelector({repr(selector)})?.textContent?.trim()")
        if _count_matching(selector) > 0
        else "<element not found>"
    )
    raise AssertionError(
        f"Assertion failed: text mismatch. Selector: {selector}. "
        f"Expected: {expected!r}. Actual: {actual!r}. Page: {page_url}. Screenshot: {path}"
    )


def assert_url(pattern: str, timeout: float = 5) -> None:
    """Check current URL matches pattern (substring or regex)."""
    deadline = time.time() + timeout
    is_regex = "/" in pattern and len(pattern) > 2
    while time.time() < deadline:
        url = _page_url()
        if is_regex:
            if re.search(pattern, url):
                return
        else:
            if pattern in url:
                return
        time.sleep(0.2)

    url = _page_url()
    try:
        path = capture_screenshot(str(_screenshot_path(pattern)))
    except Exception as e:
        path = f"<screenshot unavailable: {e}>"

    raise AssertionError(
        f"Assertion failed: URL pattern not matched. Pattern: {pattern!r}. URL: {url}. Screenshot: {path}"
    )


def assert_attribute(selector: str, attr: str, expected_value: str, timeout: float = 10) -> None:
    """Check element's attribute equals expected value."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        count = _count_matching(selector)
        if count > 0:
            actual = js(
                f"document.querySelector({repr(selector)})?.getAttribute({repr(attr)})"
            )
            if actual == expected_value:
                return
        time.sleep(0.2)

    page_url = _page_url()
    try:
        path = capture_screenshot(str(_screenshot_path(selector)))
    except Exception as e:
        path = f"<screenshot unavailable: {e}>"

    actual = (
        js(f"document.querySelector({repr(selector)})?.getAttribute({repr(attr)})")
        if _count_matching(selector) > 0
        else "<element not found>"
    )
    raise AssertionError(
        f"Assertion failed: attribute mismatch. Selector: {selector}. "
        f"Attribute: {attr}. Expected: {expected_value!r}. Actual: {actual!r}. "
        f"Page: {page_url}. Screenshot: {path}"
    )


def assert_element_count(selector: str, count: int, timeout: float = 10) -> None:
    """Check that exactly `count` elements match selector."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        actual = _count_matching(selector)
        if actual == count:
            return
        time.sleep(0.2)

    page_url = _page_url()
    try:
        path = capture_screenshot(str(_screenshot_path(selector)))
    except Exception as e:
        path = f"<screenshot unavailable: {e}>"

    actual = _count_matching(selector)
    raise AssertionError(
        f"Assertion failed: element count mismatch. Selector: {selector}. "
        f"Expected: {count}. Actual: {actual}. Page: {page_url}. Screenshot: {path}"
    )
