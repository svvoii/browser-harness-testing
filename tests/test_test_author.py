"""Tests for agent/test_author.py — mocked app_model and ci_manager."""

import os
import pytest
import subprocess
import tempfile
from unittest.mock import MagicMock, patch
from pathlib import Path


class TestTestAuthorInit:
    """Test TestAuthor initialization."""

    def test_init_with_app_model(self):
        """Test initialization with app_model."""
        from agent.test_author import TestAuthor

        mock_app_model = MagicMock()
        author = TestAuthor(app_model=mock_app_model)
        assert author.app_model is mock_app_model
        assert author.ci_manager is None

    def test_init_with_ci_manager(self):
        """Test initialization with ci_manager."""
        from agent.test_author import TestAuthor

        mock_ci = MagicMock()
        author = TestAuthor(ci_manager=mock_ci)
        assert author.app_model is None
        assert author.ci_manager is mock_ci

    def test_init_with_both(self):
        """Test initialization with both app_model and ci_manager."""
        from agent.test_author import TestAuthor

        mock_app = MagicMock()
        mock_ci = MagicMock()
        author = TestAuthor(app_model=mock_app, ci_manager=mock_ci)
        assert author.app_model is mock_app
        assert author.ci_manager is mock_ci


class TestGenerateTestName:
    """Test _generate_test_name method."""

    def test_generates_valid_test_name(self):
        """Test that generated name is a valid Python identifier."""
        from agent.test_author import TestAuthor

        author = TestAuthor()
        name = author._generate_test_name("Click the submit button")
        assert name.startswith("test_")
        assert name.replace("test_", "").replace("_", "").isalnum()

    def test_truncates_long_names(self):
        """Test that long names are truncated."""
        from agent.test_author import TestAuthor

        author = TestAuthor()
        long_desc = "click the button that says submit and wait for the page to load and verify the result"
        name = author._generate_test_name(long_desc)
        assert len(name) <= 60

    def test_handles_numeric_start(self):
        """Test that names starting with numbers get test_ prefix."""
        from agent.test_author import TestAuthor

        author = TestAuthor()
        name = author._generate_test_name("123 element")
        assert name.startswith("test_")


class TestGenerateTestContent:
    """Test generate_test_content method."""

    def test_generates_valid_python(self):
        """Test that generated content is valid Python."""
        from agent.test_author import TestAuthor

        author = TestAuthor()
        content = author.generate_test_content("navigate to example.com")
        assert "def test_" in content
        assert "from harness import *" in content

    def test_navigate_action(self):
        """Test that navigate keyword generates goto_url."""
        from agent.test_author import TestAuthor

        author = TestAuthor()
        content = author.generate_test_content("navigate to https://example.com")
        assert 'goto_url("https://example.com")' in content

    def test_go_to_action(self):
        """Test that 'go to' generates goto_url."""
        from agent.test_author import TestAuthor

        author = TestAuthor()
        content = author.generate_test_content("go to example.com")
        assert 'goto_url("example.com")' in content

    def test_click_action(self):
        """Test that click keyword generates browser_click."""
        from agent.test_author import TestAuthor

        author = TestAuthor()
        content = author.generate_test_content('click on "submit button"')
        assert "browser_click" in content

    def test_fill_action(self):
        """Test that fill keyword generates browser_fill_form."""
        from agent.test_author import TestAuthor

        author = TestAuthor()
        content = author.generate_test_content('fill "username" with "testuser"')
        assert "browser_fill_form" in content

    def test_wait_action(self):
        """Test that wait keyword generates wait_for_element."""
        from agent.test_author import TestAuthor

        author = TestAuthor()
        content = author.generate_test_content('wait for "loading indicator"')
        assert "wait_for_element" in content

    def test_assert_action(self):
        """Test that assert keyword generates assert statement."""
        from agent.test_author import TestAuthor

        author = TestAuthor()
        content = author.generate_test_content("assert that page title equals test")
        assert "assert" in content

    def test_verify_action(self):
        """Test that verify keyword generates assert statement."""
        from agent.test_author import TestAuthor

        author = TestAuthor()
        content = author.generate_test_content("verify that element is visible")
        assert "assert" in content

    def test_screenshot_action(self):
        """Test that screenshot generates capture_screenshot."""
        from agent.test_author import TestAuthor

        author = TestAuthor()
        content = author.generate_test_content("take a screenshot")
        assert "capture_screenshot()" in content

    def test_fallback_no_actions(self):
        """Test fallback when no keywords match."""
        from agent.test_author import TestAuthor

        author = TestAuthor()
        content = author.generate_test_content("do something generic")
        assert "def test_" in content
        assert "pass" in content


class TestWriteTest:
    """Test write_test method."""

    def test_creates_file(self):
        """Test that write_test creates a file."""
        from agent.test_author import TestAuthor

        author = TestAuthor()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "test_example.py")
            result = author.write_test("navigate to example.com", output_path)
            assert os.path.exists(result)
            assert result == output_path

    def test_returns_path(self):
        """Test that write_test returns the file path."""
        from agent.test_author import TestAuthor

        author = TestAuthor()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "test_example.py")
            result = author.write_test("navigate to example.com", output_path)
            assert isinstance(result, str)
            assert result.endswith(".py")

    def test_creates_directory(self):
        """Test that write_test creates parent directories."""
        from agent.test_author import TestAuthor

        author = TestAuthor()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "subdir", "test_example.py")
            result = author.write_test("navigate to example.com", output_path)
            assert os.path.exists(os.path.dirname(result))

    def test_default_path(self):
        """Test that default path is used when output_path is None."""
        from agent.test_author import TestAuthor

        author = TestAuthor()
        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                result = author.write_test("navigate to example.com")
                assert os.path.exists(result)
                assert result.endswith(".py")
            finally:
                os.chdir(original_cwd)


class TestCommitTest:
    """Test commit_test method."""

    def test_commits_file(self):
        """Test that commit_test stages and commits a file."""
        from agent.test_author import TestAuthor

        author = TestAuthor()
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a test file
            test_file = os.path.join(tmpdir, "test_example.py")
            with open(test_file, "w") as f:
                f.write("# test file")

            with patch.object(subprocess, "run") as mock_run:
                author.commit_test(test_file, "test: add test_example")
                assert mock_run.call_count == 2
                # First call: git add
                assert mock_run.call_args_list[0][0][0] == ["git", "add", test_file]
                # Second call: git commit
                assert mock_run.call_args_list[1][0][0] == ["git", "commit", "-m", "test: add test_example"]

    def test_default_message(self):
        """Test that default commit message is generated."""
        from agent.test_author import TestAuthor

        author = TestAuthor()
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = os.path.join(tmpdir, "test_example.py")
            with open(test_file, "w") as f:
                f.write("# test file")

            with patch.object(subprocess, "run") as mock_run:
                author.commit_test(test_file)
                # Should have default message
                call_args = mock_run.call_args_list[1][0][0]
                assert "-m" in call_args
                msg_index = call_args.index("-m") + 1
                assert "test_example" in call_args[msg_index]


class TestListTests:
    """Test list_tests method."""

    def test_returns_list(self):
        """Test that list_tests returns a list."""
        from agent.test_author import TestAuthor

        author = TestAuthor()
        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            os.chdir(tmpdir)
            os.makedirs("tests", exist_ok=True)
            try:
                result = author.list_tests()
                assert isinstance(result, list)
            finally:
                os.chdir(original_cwd)

    def test_filters_test_files(self):
        """Test that only test_*.py files are returned."""
        from agent.test_author import TestAuthor

        author = TestAuthor()
        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            os.chdir(tmpdir)
            os.makedirs("tests", exist_ok=True)
            # Create test files
            Path("tests/test_foo.py").touch()
            Path("tests/test_bar.py").touch()
            Path("tests/not_a_test.py").touch()
            try:
                result = author.list_tests()
                assert len(result) == 2
                assert "test_foo.py" in result
                assert "test_bar.py" in result
                assert "not_a_test.py" not in result
            finally:
                os.chdir(original_cwd)


class TestUpdateTest:
    """Test update_test method."""

    def test_updates_file(self):
        """Test that update_test writes new content to file."""
        from agent.test_author import TestAuthor

        author = TestAuthor()
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = os.path.join(tmpdir, "test_example.py")
            original_content = "def test_old():\n    pass"
            new_content = "def test_new():\n    assert True"

            with open(test_file, "w") as f:
                f.write(original_content)

            author.update_test(test_file, new_content)

            with open(test_file, "r") as f:
                assert f.read() == new_content

    def test_raises_on_missing_file(self):
        """Test that update_test raises FileNotFoundError for missing file."""
        from agent.test_author import TestAuthor

        author = TestAuthor()
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(FileNotFoundError):
                author.update_test(os.path.join(tmpdir, "nonexistent.py"), "content")


class TestGetSelector:
    """Test _get_selector method."""

    def test_uses_app_model_get_selector(self):
        """Test that _get_selector uses app_model.get_selector when available."""
        from agent.test_author import TestAuthor

        mock_app = MagicMock()
        mock_app.get_selector.return_value = "#submit-btn"

        author = TestAuthor(app_model=mock_app)
        result = author._get_selector("submit button")

        mock_app.get_selector.assert_called_once_with("submit button")
        assert result == "#submit-btn"

    def test_fallback_without_app_model(self):
        """Test fallback selector when app_model is None."""
        from agent.test_author import TestAuthor

        author = TestAuthor(app_model=None)
        result = author._get_selector("submit button")
        assert result == '[data-testid="submit-button"]'

    def test_fallback_without_get_selector(self):
        """Test fallback when app_model has no get_selector method."""
        from agent.test_author import TestAuthor

        mock_app = MagicMock(spec=[])  # No get_selector method
        author = TestAuthor(app_model=mock_app)
        result = author._get_selector("submit button")
        assert result == '[data-testid="submit-button"]'