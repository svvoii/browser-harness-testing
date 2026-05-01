"""UI testing helpers — element discovery, text extraction, visibility checks.

These are the SAP Build / UI-testing-specific layer on top of the core CDP
helpers from browser_harness.helpers (goto_url, click, js, etc.).
"""

import json
import time
from browser_harness.helpers import js


# --- UI testing helpers ---------------------------------------------------

def find_element(selector):
    """Find element by selector, return element info or None.

    Args:
        selector: CSS selector string

    Returns:
        Element info dict with uid, tag, text, attrs, visible, rect, children, etc.,
        or None if not found.
    """
    expr = json.dumps(selector)
    result = js(
        f"(function(){{"
        f"  const el = document.querySelector({expr});"
        f"  if (!el) return null;"
        f"  const rect = el.getBoundingClientRect();"
        f"  const visible = rect.width > 0 && rect.height > 0 && getComputedStyle(el).visibility !== 'hidden';"
        f"  const attrs = {{}};"
        f"  for (const attr of el.attributes) attrs[attr.name] = attr.value;"
        f"  const children = [];"
        f"  for (const child of el.children) children.push(child.tagName);"
        f"  return {{"
        f"    uid: undefined, tag: el.tagName, text: el.innerText, attrs, visible,"
        f"    rect: {{ x: rect.x, y: rect.y, w: rect.width, h: rect.height }},"
        f"    children"
        f"  }};"
        f"}})()"
    )
    return result


def get_element_text(selector):
    """Get text content of element.

    Args:
        selector: CSS selector string

    Returns:
        Inner text of the first matching element, or None if not found.
    """
    result = find_element(selector)
    return result.get("text") if result else None


def get_element_attribute(selector, attr):
    """Get attribute value of element.

    Args:
        selector: CSS selector string
        attr: Attribute name to retrieve

    Returns:
        Attribute value string, or None if not found/not present.
    """
    expr = json.dumps(selector)
    return js(
        f"(function(){{"
        f"  const el = document.querySelector({expr});"
        f"  return el ? el.getAttribute({json.dumps(attr)}) : null;"
        f"}})()"
    )


def wait_for_element(selector, timeout=10):
    """Wait for element to appear in DOM.

    Args:
        selector: CSS selector string
        timeout: Maximum seconds to wait

    Returns:
        Element info dict if found, or None on timeout.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = find_element(selector)
        if result is not None:
            return result
        time.sleep(0.3)
    return None


def wait_for_element_visible(selector, timeout=10):
    """Wait for element to be visible.

    Args:
        selector: CSS selector string
        timeout: Maximum seconds to wait

    Returns:
        Element info dict if visible, or None on timeout.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = find_element(selector)
        if result is not None and result.get("visible"):
            return result
        time.sleep(0.3)
    return None


def is_element_visible(selector):
    """Check if element is visible without waiting.

    Args:
        selector: CSS selector string

    Returns:
        True if element exists and is visible, False otherwise.
    """
    result = find_element(selector)
    return result is not None and result.get("visible", False)


def get_all_text(selector):
    """Get text of all elements matching selector (returns list).

    Args:
        selector: CSS selector string

    Returns:
        List of inner text strings for all matching elements.
    """
    expr = json.dumps(selector)
    return js(
        f"(function(){{"
        f"  const els = document.querySelectorAll({expr});"
        f"  return Array.from(els).map(el => el.innerText);"
        f"}})()"
    ) or []
