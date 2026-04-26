"""TestAuthor: natural language task -> test file writer.

Uses keyword-based parsing to generate Python test code from natural language descriptions.
"""

import os
import re
import subprocess
from pathlib import Path
from typing import Optional, List

from harness import (
    goto_url,
    wait_for_element,
    wait_for_element_visible,
    is_element_visible,
    get_element_text,
    find_element,
    capture_screenshot,
)


class TestAuthor:
    """Convert natural language task descriptions into Python test files."""

    DEFAULT_TESTS_DIR = "tests"

    def __init__(self, app_model=None, ci_manager=None):
        """Initialize TestAuthor.

        Args:
            app_model: Application model for selectors (duck-typed via hasattr)
            ci_manager: Optional CI manager for git operations
        """
        self.app_model = app_model
        self.ci_manager = ci_manager

    def write_test(self, task_description: str, output_path: str = None) -> str:
        """Write test file from NL task description.

        Args:
            task_description: Natural language description of the test
            output_path: Optional path for output file. If None, generates default path.

        Returns:
            Path to the created test file.
        """
        content = self.generate_test_content(task_description)

        if output_path is None:
            output_path = self._default_output_path(task_description)

        # Ensure directory exists
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)

        return output_path

    def generate_test_content(self, task_description: str) -> str:
        """Generate Python test code from task description.

        Uses keyword-based approach to parse task_description:
        - "click" -> browser_click
        - "fill" -> browser_fill_form
        - "navigate" / "go to" -> goto_url
        - "assert" / "verify" / "check" -> assertions
        - "wait for" -> wait_for_element
        - "screenshot" -> capture_screenshot
        - "type" -> browser_type

        Args:
            task_description: Natural language task description

        Returns:
            Python test code as string
        """
        test_name = self._generate_test_name(task_description)
        actions = self._parse_task_description(task_description)

        lines = [
            '"""Auto-generated test from task description.',
            f'"""\n',
            f'from harness import *\n\n',
        ]

        if actions:
            lines.append(f"def test_{test_name}():")
            lines.append('    """Test generated from task description."""')
            lines.append("")
            for action in actions:
                lines.append(f"    {action}")
            lines.append("")
        else:
            # Fallback: just a navigation test
            lines.append(f"def test_{test_name}():")
            lines.append('    """Test generated from task description."""')
            lines.append("    pass")

        return "\n".join(lines)

    def _generate_test_name(self, task_description: str) -> str:
        """Generate a valid Python test function name from task description."""
        # Remove punctuation, replace spaces with underscores
        name = re.sub(r'[^\w\s-]', '', task_description.lower())
        name = re.sub(r'[\s-]+', '_', name)
        # Take first 50 characters
        name = name[:50].strip('_')
        if not name or name[0].isdigit():
            name = "test_" + name
        if not name.startswith("test_"):
            name = "test_" + name
        return name

    def _parse_task_description(self, task_description: str) -> List[str]:
        """Parse task description into list of action statements.

        Returns:
            List of Python code lines to execute in the test.
        """
        actions = []
        text = task_description.lower()

        # Pattern: navigate to [url]
        nav_matches = re.findall(r'navigate to (.+?)(?:\.\s|$)', text + " ")
        for match in nav_matches:
            url = match.strip().strip('"\'')
            if url and not url.endswith('.'):
                actions.append(f'goto_url("{url}")')

        # Pattern: go to [url]
        go_matches = re.findall(r'go to (.+?)(?:\.\s|$)', text + " ")
        for match in go_matches:
            url = match.strip().strip('"\'')
            if url and not url.endswith('.'):
                actions.append(f'goto_url("{url}")')

        # Pattern: click on [element] / click [element]
        click_matches = re.findall(r'click (?:on )?"?([^"\n\.]+)"?', text)
        for match in click_matches:
            selector = self._get_selector(match.strip())
            if selector:
                actions.append(f'browser_click(element="{selector}", ref=get_selector("{selector}"))')

        # Pattern: fill [field] with [value]
        fill_matches = re.findall(r'fill "?([^"\n]+)"? with "?([^"\n]+)"?', text)
        for field, value in fill_matches:
            field_selector = self._get_selector(field.strip())
            if field_selector:
                actions.append(f'browser_fill_form(fields=[{{"name": "{field.strip()}", "ref": get_selector("{field_selector}"), "type": "textbox", "value": "{value.strip()}"}}])')

        # Pattern: type [text] in [field]
        type_matches = re.findall(r'type "?([^"\n]+)"? in "?([^"\n]+)"?', text)
        for text_to_type, field in type_matches:
            field_selector = self._get_selector(field.strip())
            if field_selector:
                actions.append(f'browser_type(element="{field_selector}", ref=get_selector("{field_selector}"), text="{text_to_type.strip()}")')

        # Pattern: wait for [element]
        wait_matches = re.findall(r'wait for "?([^"\n\.]+)"?', text)
        for match in wait_matches:
            selector = self._get_selector(match.strip())
            if selector:
                actions.append(f'wait_for_element("{selector}")')

        # Pattern: assert [condition]
        assert_matches = re.findall(r'assert (?:that )?(.+)', text)
        for match in assert_matches:
            condition = match.strip().strip('"\'.')
            actions.append(f'assert {condition}')

        # Pattern: verify [condition]
        verify_matches = re.findall(r'verify (?:that )?(.+)', text)
        for match in verify_matches:
            condition = match.strip().strip('"\'.')
            actions.append(f'assert {condition}')

        # Pattern: check [condition]
        check_matches = re.findall(r'check (?:that )?(.+)', text)
        for match in check_matches:
            condition = match.strip().strip('"\'.')
            actions.append(f'assert {condition}')

        # Pattern: take screenshot
        if 'screenshot' in text:
            actions.append('capture_screenshot()')

        return actions

    def _get_selector(self, element_name: str) -> Optional[str]:
        """Get selector for element from app_model if available.

        Args:
            element_name: Name/label of the element

        Returns:
            CSS selector string or None if not found
        """
        if self.app_model is not None and hasattr(self.app_model, 'get_selector'):
            return self.app_model.get_selector(element_name)
        # Fallback: try to construct a selector
        return f'[data-testid="{element_name.replace(" ", "-")}"]'

    def _default_output_path(self, task_description: str) -> str:
        """Generate default output path for test file."""
        test_name = self._generate_test_name(task_description)
        tests_dir = self.DEFAULT_TESTS_DIR

        # Ensure we're using absolute path if relative
        if not os.path.isabs(tests_dir):
            tests_dir = os.path.join(os.getcwd(), tests_dir)

        return os.path.join(tests_dir, f"{test_name}.py")

    def commit_test(self, file_path: str, message: str = None) -> None:
        """Commit test file via git subprocess.

        Args:
            file_path: Path to the test file to commit
            message: Optional commit message. If None, generates a default.
        """
        if message is None:
            test_name = Path(file_path).stem
            message = f"test: add {test_name}"

        # Use subprocess.run for git add + git commit
        try:
            # Stage the file
            subprocess.run(
                ["git", "add", file_path],
                check=True,
                capture_output=True,
                text=True,
            )

            # Commit with message
            subprocess.run(
                ["git", "commit", "-m", message],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Git commit failed: {e.stderr}") from e

    def list_tests(self) -> List[str]:
        """List all test files in tests/ directory.

        Returns:
            List of test file paths (relative to tests/ directory)
        """
        tests_dir = self.DEFAULT_TESTS_DIR

        # Handle relative path
        if not os.path.isabs(tests_dir):
            tests_dir = os.path.join(os.getcwd(), tests_dir)

        if not os.path.isdir(tests_dir):
            return []

        test_files = []
        for file in os.listdir(tests_dir):
            if file.startswith("test_") and file.endswith(".py"):
                test_files.append(file)

        return sorted(test_files)

    def update_test(self, test_path: str, changes: str) -> None:
        """Update existing test file with changes.

        Args:
            test_path: Path to the test file to update
            changes: String containing the new content or diff to apply
        """
        if not os.path.isfile(test_path):
            raise FileNotFoundError(f"Test file not found: {test_path}")

        with open(test_path, "w", encoding="utf-8") as f:
            f.write(changes)


def get_selector(selector: str) -> str:
    """Standalone function to get a selector string.

    This is provided for generated test code that needs to reference selectors.
    """
    return selector