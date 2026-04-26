"""Tests for assertions.py — verify imports and function signatures."""
import pytest


def test_imports():
    """Assert the module imports without errors."""
    from harness import assertions
    assert assertions is not None


def test_assert_visible_signature():
    """Assert assert_visible has correct signature."""
    from harness.assertions import assert_visible
    import inspect
    sig = inspect.signature(assert_visible)
    assert "selector" in sig.parameters
    assert "timeout" in sig.parameters


def test_assert_not_visible_signature():
    """Assert assert_not_visible has correct signature."""
    from harness.assertions import assert_not_visible
    import inspect
    sig = inspect.signature(assert_not_visible)
    assert "selector" in sig.parameters
    assert "timeout" in sig.parameters


def test_assert_text_signature():
    """Assert assert_text has correct signature."""
    from harness.assertions import assert_text
    import inspect
    sig = inspect.signature(assert_text)
    assert "selector" in sig.parameters
    assert "expected" in sig.parameters
    assert "timeout" in sig.parameters


def test_assert_url_signature():
    """Assert assert_url has correct signature."""
    from harness.assertions import assert_url
    import inspect
    sig = inspect.signature(assert_url)
    assert "pattern" in sig.parameters
    assert "timeout" in sig.parameters


def test_assert_attribute_signature():
    """Assert assert_attribute has correct signature."""
    from harness.assertions import assert_attribute
    import inspect
    sig = inspect.signature(assert_attribute)
    assert "selector" in sig.parameters
    assert "attr" in sig.parameters
    assert "expected_value" in sig.parameters
    assert "timeout" in sig.parameters


def test_assert_element_count_signature():
    """Assert assert_element_count has correct signature."""
    from harness.assertions import assert_element_count
    import inspect
    sig = inspect.signature(assert_element_count)
    assert "selector" in sig.parameters
    assert "count" in sig.parameters
    assert "timeout" in sig.parameters


def test_results_dir_created():
    """Assert test-results directory exists."""
    from pathlib import Path
    assert Path("test-results").is_dir()


def test_screenshot_path_generator():
    """Assert _screenshot_path generates correct paths."""
    from harness.assertions import _screenshot_path
    import re
    path = _screenshot_path("div.test-class")
    assert path.parent.name == "test-results"
    assert re.match(r"^failed_div_test_class_\d+\.png$", path.name)