"""Tests for agent/self_healer.py — mocked app_model and ci_manager."""

import pytest
from unittest.mock import MagicMock


class TestSelfHealerInit:
    """Test SelfHealer initialization."""

    def test_init_with_mocks(self):
        """Test initialization with mock objects."""
        from agent.self_healer import SelfHealer

        mock_app = MagicMock()
        mock_ci = MagicMock()

        healer = SelfHealer(mock_app, mock_ci)
        assert healer.app_model is mock_app
        assert healer.ci_manager is mock_ci


class TestAnalyzeFailure:
    """Test analyze_failure method."""

    def setup_method(self):
        """Set up test fixtures."""
        from agent.self_healer import SelfHealer

        self.mock_app = MagicMock()
        self.mock_ci = MagicMock()
        self.healer = SelfHealer(self.mock_app, self.mock_ci)

    def test_selector_stale_detection(self):
        """Test that selector errors are detected."""
        error = Exception("no such element: Unable to locate element: #submit-btn")
        result = self.healer.analyze_failure("test_file.py", error)

        assert result["type"] == "selector_stale"
        assert result["fixable"] is True
        assert "selector" in result["diagnosis"].lower()

    def test_selector_stale_with_stale_message(self):
        """Test stale element detection."""
        error = Exception("stale element reference: element not found")
        result = self.healer.analyze_failure("test_file.py", error)

        assert result["type"] == "selector_stale"
        assert result["fixable"] is True

    def test_assertion_wrong_detection(self):
        """Test that assertion errors are detected."""
        error = Exception("assertion failed: expected 'Submit' but got 'Cancel'")
        result = self.healer.analyze_failure("test_file.py", error)

        assert result["type"] == "assertion_wrong"
        assert result["fixable"] is True
        assert "expected" in result["diagnosis"].lower()

    def test_infrastructure_error_detection(self):
        """Test infrastructure errors are detected."""
        error = Exception("connection refused: ECONNREFUSED")
        result = self.healer.analyze_failure("test_file.py", error)

        assert result["type"] == "infrastructure"
        assert result["fixable"] is False

    def test_flaky_detection(self):
        """Test flaky pattern detection."""
        error = Exception("intermittent failure: race condition detected")
        result = self.healer.analyze_failure("test_file.py", error)

        assert result["type"] == "flaky"
        assert result["fixable"] is False

    def test_behavior_changed_default(self):
        """Test that unknown errors default to behavior_changed."""
        error = Exception("some unexpected error occurred")
        result = self.healer.analyze_failure("test_file.py", error)

        assert result["type"] == "behavior_changed"
        assert result["fixable"] is False


class TestFindAlternativeSelector:
    """Test _find_alternative_selector method."""

    def setup_method(self):
        """Set up test fixtures."""
        from agent.self_healer import SelfHealer

        self.mock_app = MagicMock()
        self.mock_ci = MagicMock()
        self.healer = SelfHealer(self.mock_app, self.mock_ci)

    def test_finds_data_testid(self):
        """Test that data-testid is found first."""
        html = '<button data-testid="submit-btn">Submit</button>'
        result = self.healer._find_alternative_selector(html)

        assert result == '[data-testid="submit-btn"]'

    def test_finds_aria_label(self):
        """Test that aria-label is found when no data-testid."""
        html = '<input aria-label="email-input" />'
        result = self.healer._find_alternative_selector(html)

        assert result == '[aria-label="email-input"]'

    def test_finds_role(self):
        """Test that role is found when no data-testid or aria-label."""
        html = '<div role="button">Click me</div>'
        result = self.healer._find_alternative_selector(html)

        assert result == '[role="button"]'

    def test_finds_id(self):
        """Test that id is found last in priority."""
        html = '<input id="username-field" />'
        result = self.healer._find_alternative_selector(html)

        assert result == "#username-field"

    def test_no_selector_found(self):
        """Test that None is returned when no suitable selector."""
        html = '<div class="random-class">No identifier</div>'
        result = self.healer._find_alternative_selector(html)

        assert result is None

    def test_priority_order(self):
        """Test that data-testid takes priority over aria-label."""
        html = '<button data-testid="primary" aria-label="secondary">Click</button>'
        result = self.healer._find_alternative_selector(html)

        assert result == '[data-testid="primary"]'


class TestGenerateFix:
    """Test generate_fix method."""

    def setup_method(self):
        """Set up test fixtures."""
        from agent.self_healer import SelfHealer

        self.mock_app = MagicMock()
        self.mock_ci = MagicMock()
        self.healer = SelfHealer(self.mock_app, self.mock_ci)

    def test_generate_fix_selector_stale(self):
        """Test fix generation for selector staleness."""
        self.mock_ci.get_file_content.return_value = 'page.get_by_role("button")'

        analysis = {
            "type": "selector_stale",
            "diagnosis": "Selector stale. Found alternative: [data-testid='submit']",
            "fixable": True,
        }

        result = self.healer.generate_fix("test.py", analysis)

        assert "[data-testid='submit']" in result

    def test_generate_fix_reads_from_ci_manager(self):
        """Test that generate_fix reads file content via ci_manager."""
        self.mock_ci.get_file_content.return_value = "page.get_by_role('button')"

        self.healer.generate_fix("test.py", {"type": "selector_stale", "diagnosis": "test", "fixable": True})

        self.mock_ci.get_file_content.assert_called_once_with("test.py")

    def test_generate_fix_non_fixable_unchanged(self):
        """Test that non-fixable failures return unchanged content."""
        self.mock_ci.get_file_content.return_value = "original content"

        analysis = {
            "type": "behavior_changed",
            "diagnosis": "something changed",
            "fixable": False,
        }

        result = self.healer.generate_fix("test.py", analysis)

        assert result == "original content"


class TestApplyFix:
    """Test apply_fix method."""

    def setup_method(self):
        """Set up test fixtures."""
        from agent.self_healer import SelfHealer

        self.mock_app = MagicMock()
        self.mock_ci = MagicMock()
        self.healer = SelfHealer(self.mock_app, self.mock_ci)

    def test_apply_fix_creates_branch(self):
        """Test that apply_fix creates a branch."""
        self.mock_ci.update_file.return_value = None
        self.mock_ci.create_branch.return_value = None
        self.mock_ci.create_pr.return_value = 42

        result = self.healer.apply_fix("test.py", "new content", "diagnosis message")

        assert result["status"] == "fixed"
        self.mock_ci.create_branch.assert_called_once()

    def test_apply_fix_updates_file(self):
        """Test that apply_fix updates the file."""
        self.mock_ci.update_file.return_value = None
        self.mock_ci.create_branch.return_value = None
        self.mock_ci.create_pr.return_value = 42

        self.healer.apply_fix("test.py", "new content", "diagnosis message")

        self.mock_ci.update_file.assert_called_once()
        call_args = self.mock_ci.update_file.call_args
        assert call_args[0][0] == "test.py"
        assert call_args[0][1] == "new content"

    def test_apply_fix_creates_pr(self):
        """Test that apply_fix creates a draft PR."""
        self.mock_ci.update_file.return_value = None
        self.mock_ci.create_branch.return_value = None
        self.mock_ci.create_pr.return_value = 42

        result = self.healer.apply_fix("test.py", "new content", "diagnosis message")

        self.mock_ci.create_pr.assert_called_once()
        call_kwargs = self.mock_ci.create_pr.call_args[1]
        assert call_kwargs["draft"] is True
        assert call_kwargs["base"] == "main"

    def test_apply_fix_returns_pr_url(self):
        """Test that apply_fix returns PR URL when PR is created."""
        self.mock_ci.update_file.return_value = None
        self.mock_ci.create_branch.return_value = None
        self.mock_ci.create_pr.return_value = 42

        result = self.healer.apply_fix("test.py", "new content", "diagnosis message")

        assert result["pr_url"] == "https://github.com/pull/42"

    def test_apply_fix_graceful_when_pr_fails(self):
        """Test that apply_fix returns fixed status even if PR creation fails."""
        self.mock_ci.update_file.return_value = None
        self.mock_ci.create_branch.return_value = None
        self.mock_ci.create_pr.side_effect = Exception("PR creation failed")

        result = self.healer.apply_fix("test.py", "new content", "diagnosis message")

        assert result["status"] == "fixed"
        assert result["pr_url"] is None


class TestRetryTest:
    """Test retry_test method."""

    def setup_method(self):
        """Set up test fixtures."""
        from agent.self_healer import SelfHealer

        self.mock_app = MagicMock()
        self.mock_ci = MagicMock()
        self.healer = SelfHealer(self.mock_app, self.mock_ci)

    def test_retry_test_returns_retry_attempted(self):
        """Test that retry_test returns retry_attempted status."""
        result = self.healer.retry_test("test.py")

        assert result["status"] == "retry_attempted"
        assert "retry" in result["message"].lower()


class TestHeal:
    """Test heal method - main entry point."""

    def setup_method(self):
        """Set up test fixtures."""
        from agent.self_healer import SelfHealer

        self.mock_app = MagicMock()
        self.mock_ci = MagicMock()
        self.healer = SelfHealer(self.mock_app, self.mock_ci)

    def test_heal_selector_stale_fixable(self):
        """Test heal flow for selector_stale."""
        self.mock_ci.get_file_content.return_value = 'page.get_by_role("button")'
        self.mock_ci.update_file.return_value = None
        self.mock_ci.create_branch.return_value = None
        self.mock_ci.create_pr.return_value = 99

        error = Exception("no such element: #submit-btn")
        result = self.healer.heal("test.py", error)

        assert result["status"] == "fixed"
        assert result["pr_url"] == "https://github.com/pull/99"

    def test_heal_infrastructure_retry_then_flag(self):
        """Test heal flow for infrastructure errors with retry."""
        # First retry succeeds (mock doesn't raise)
        error = Exception("connection refused")
        result = self.healer.heal("test.py", error)

        assert result["status"] == "retry_attempted" or result["status"] == "flagged"

    def test_heal_non_fixable_flagged(self):
        """Test heal flow for non-fixable failures."""
        error = Exception("unexpected behavior detected")
        result = self.healer.heal("test.py", error)

        assert result["status"] == "flagged"
        assert "behavior_changed" in result["message"]

    def test_heal_extracts_html_from_page_info(self):
        """Test that heal extracts html from page_info dict."""
        html = '<button data-testid="my-btn">Click</button>'

        error = Exception("stale element")
        self.healer.heal("test.py", error, page_info={"html": html})

        # Should find alternative selector from html
        # heal() -> analyze_failure() -> _diagnose_selector_error() -> _find_alternative_selector()
        # The analysis should show a fix was found
        self.mock_ci.get_file_content.return_value = "page.locator('#old')"
        self.mock_ci.update_file.return_value = None
        self.mock_ci.create_branch.return_value = None
        self.mock_ci.create_pr.return_value = 1

        result = self.healer.heal("test.py", error, page_info={"html": html})

        # The diagnosis should mention the alternative found
        assert result["status"] == "fixed"


class TestEdgeCases:
    """Test edge cases."""

    def setup_method(self):
        """Set up test fixtures."""
        from agent.self_healer import SelfHealer

        self.mock_app = MagicMock()
        self.mock_ci = MagicMock()
        self.healer = SelfHealer(self.mock_app, self.mock_ci)

    def test_analyze_failure_empty_error_message(self):
        """Test analyze_failure with empty error message."""
        error = Exception("")
        result = self.healer.analyze_failure("test.py", error)

        # Should default to behavior_changed
        assert result["type"] == "behavior_changed"

    def test_generate_fix_file_read_error(self):
        """Test generate_fix when file read fails."""
        self.mock_ci.get_file_content.side_effect = Exception("File not found")

        analysis = {"type": "selector_stale", "diagnosis": "test", "fixable": True}
        result = self.healer.generate_fix("test.py", analysis)

        # Should return empty string and not crash
        assert result == ""

    def test_apply_fix_file_write_error(self):
        """Test apply_fix when file write fails."""
        self.mock_ci.update_file.side_effect = Exception("Write failed")
        self.mock_ci.create_branch.return_value = None

        result = self.healer.apply_fix("test.py", "content", "diagnosis")

        assert result["status"] == "flagged"
        assert "failed" in result["message"].lower()
