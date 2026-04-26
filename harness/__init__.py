"""browser-harness-testing helpers.

Re-exports all helpers from helpers.py for convenient access:
    from harness import goto_url, click_at_xy, capture_screenshot, ...

Or use the full module:
    from harness.helpers import find_element, wait_for_element, ...
"""

from harness.helpers import (
    # Re-exported from browser-harness
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
    # UI testing helpers
    find_element,
    get_element_text,
    get_element_attribute,
    wait_for_element,
    wait_for_element_visible,
    is_element_visible,
    get_all_text,
)

__all__ = [
    # Re-exported from browser-harness
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
]
