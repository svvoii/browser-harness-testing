"""browser-harness-testing harness package.

Re-exports helpers from the browser_harness/ core (CDP client) and
our own UI-testing layer so callers can use a single import::

    from harness import ensure_daemon, goto_url, find_element, assert_visible

Core CDP helpers (from browser_harness/):
    ensure_daemon, goto_url, click_at_xy, capture_screenshot, wait_for_load,
    js, page_info, list_tabs, new_tab, switch_tab, ensure_real_tab,
    type_text, press_key, scroll, upload_file, http_get, wait

UI-testing helpers (from harness/):
    find_element, get_element_text, get_element_attribute,
    wait_for_element, wait_for_element_visible, is_element_visible, get_all_text

Assertions (from harness/assertions):
    assert_visible, assert_not_visible, assert_text, assert_url,
    assert_attribute, assert_element_count
"""

from browser_harness.admin import ensure_daemon
from browser_harness.helpers import (
    goto_url,
    click_at_xy,
    capture_screenshot,
    wait_for_load,
    js,
    page_info,
    list_tabs,
    new_tab,
    switch_tab,
    ensure_real_tab,
    type_text,
    press_key,
    scroll,
    upload_file,
    http_get,
    wait,
)
from .helpers import (
    find_element,
    get_element_text,
    get_element_attribute,
    wait_for_element,
    wait_for_element_visible,
    is_element_visible,
    get_all_text,
)
from .assertions import (
    assert_visible,
    assert_not_visible,
    assert_text,
    assert_url,
    assert_attribute,
    assert_element_count,
)

__all__ = [
    # admin / daemon lifecycle
    "ensure_daemon",
    # core CDP helpers
    "goto_url",
    "click_at_xy",
    "capture_screenshot",
    "wait_for_load",
    "js",
    "page_info",
    "list_tabs",
    "new_tab",
    "switch_tab",
    "ensure_real_tab",
    "type_text",
    "press_key",
    "scroll",
    "upload_file",
    "http_get",
    "wait",
    # UI testing helpers
    "find_element",
    "get_element_text",
    "get_element_attribute",
    "wait_for_element",
    "wait_for_element_visible",
    "is_element_visible",
    "get_all_text",
    # assertions
    "assert_visible",
    "assert_not_visible",
    "assert_text",
    "assert_url",
    "assert_attribute",
    "assert_element_count",
]
