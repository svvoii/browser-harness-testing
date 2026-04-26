"""Self-healing agent for test failure analysis and fix generation.

Analyzes test failures, determines the failure type, and generates fixes
for selector_stale and assertion_wrong failures. Flags human for
behavior_changed, flaky, and infrastructure issues.

app_model interface (duck-typed):
    - get_element_info(selector: str) -> dict|None
    - get_page_url() -> str

ci_manager interface (duck-typed):
    - create_pr(title: str, body: str, head: str, base: str, draft: bool) -> int
    - update_file(path: str, content: str, message: str, branch: str) -> None
    - create_branch(branch_name: str, from_sha: str|None) -> None
    - get_file_content(path: str, ref: str|None) -> str
"""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


# Sentinel object to detect when a value was not provided
NOT_PROVIDED = object()


class SelfHealer:
    """Analyzes test failures and generates fixes for auto-fixable issues."""

    def __init__(self, app_model, ci_manager):
        """Initialize SelfHealer.

        Args:
            app_model: Object providing get_element_info(selector) and get_page_url()
            ci_manager: Object providing create_pr(), update_file(), create_branch(),
                       get_file_content()
        """
        self.app_model = app_model
        self.ci_manager = ci_manager

    def analyze_failure(
        self,
        test_file: str,
        error: Exception,
        screenshot: Optional[bytes] = None,
        page_html: Optional[str] = None,
    ) -> dict:
        """Analyze a test failure to determine its type and suggested fix.

        Args:
            test_file: Path to the test file
            error: The exception that was raised
            screenshot: Optional screenshot of the failure state
            page_html: Optional HTML of the page at failure time

        Returns:
            dict with keys:
                - type: "selector_stale" | "assertion_wrong" | "behavior_changed" | "flaky" | "infrastructure"
                - diagnosis: Human-readable explanation
                - fixable: Whether this type can be auto-fixed
                - suggested_fix: Description of the fix, or None
        """
        error_msg = str(error)
        error_type = type(error).__name__

        # Check for selector-related errors
        if self._is_selector_error(error_msg):
            diagnosis = self._diagnose_selector_error(error_msg, page_html)
            return {
                "type": "selector_stale",
                "diagnosis": diagnosis,
                "fixable": True,
                "suggested_fix": diagnosis,
            }

        # Check for assertion errors
        if self._is_assertion_error(error_msg):
            return self._analyze_assertion_error(error_msg)

        # Check for infrastructure errors (network, timeout, etc.)
        if self._is_infrastructure_error(error_msg):
            return {
                "type": "infrastructure",
                "diagnosis": f"Infrastructure error: {error_msg}",
                "fixable": False,
                "suggested_fix": None,
            }

        # Check for likely flaky patterns
        if self._is_flaky_pattern(error_msg):
            return {
                "type": "flaky",
                "diagnosis": f"Possibly flaky test: {error_msg}",
                "fixable": False,
                "suggested_fix": None,
            }

        # Default: behavior changed - needs human review
        return {
            "type": "behavior_changed",
            "diagnosis": f"Unexpected error ({error_type}): {error_msg}",
            "fixable": False,
            "suggested_fix": None,
        }

    def _is_selector_error(self, error_msg: str) -> bool:
        """Check if error is related to selector issues."""
        selector_patterns = [
            r"no such element",
            r"element not found",
            r"selector.*not.*found",
            r"find_element.*failed",
            r"stale element",
            r"element.*detached",
        ]
        msg_lower = error_msg.lower()
        return any(re.search(p, msg_lower) for p in selector_patterns)

    def _is_assertion_error(self, error_msg: str) -> bool:
        """Check if error is an assertion failure."""
        assertion_patterns = [
            r"assert.*failed",
            r"assertion.*error",
            r"expected.*actual",
            r"expected.*but.*found",
            r"assertEqual",
            r"assertTrue",
            r"pytest.*assert",
        ]
        msg_lower = error_msg.lower()
        return any(re.search(p, msg_lower) for p in assertion_patterns)

    def _is_infrastructure_error(self, error_msg: str) -> bool:
        """Check if error is an infrastructure issue."""
        infra_patterns = [
            r"connection.*refused",
            r"timeout",
            r"network.*error",
            r"ECONNREFUSED",
            r"ETIMEDOUT",
            r"server.*error",
            r"500",
            r"502",
            r"503",
            r"504",
        ]
        msg_lower = error_msg.lower()
        return any(re.search(p, msg_lower) for p in infra_patterns)

    def _is_flaky_pattern(self, error_msg: str) -> bool:
        """Check for patterns that suggest flakiness."""
        flaky_patterns = [
            r"intermittent",
            r"flaky",
            r"race condition",
            r"sometimes.*fail",
            r"occasionally",
        ]
        msg_lower = error_msg.lower()
        return any(re.search(p, msg_lower) for p in flaky_patterns)

    def _diagnose_selector_error(self, error_msg: str, page_html: Optional[str]) -> str:
        """Diagnose selector error and find alternative selector."""
        if page_html:
            # Try to find alternative selectors
            alternative = self._find_alternative_selector(page_html)
            if alternative:
                return f"Selector stale. Found alternative: {alternative}"

        return f"Selector error: {error_msg}"

    def _find_alternative_selector(self, page_html: str) -> Optional[str]:
        """Find an alternative selector for elements on the page.

        Priority: data-testid > aria-label > role > id
        """
        # Simple regex-based extraction for attributes
        # This is a heuristic approach

        # Try data-testid first
        pattern = r'<[^>]*data-testid=["\']([^"\']+)["\']'
        matches = re.findall(pattern, page_html)
        if matches:
            selector = f'[data-testid="{matches[0]}"]'
            logger.info(f"Found data-testid alternative: {selector}")
            return selector

        # Try aria-label
        pattern = r'<[^>]*aria-label=["\']([^"\']+)["\']'
        matches = re.findall(pattern, page_html)
        if matches:
            selector = f'[aria-label="{matches[0]}"]'
            logger.info(f"Found aria-label alternative: {selector}")
            return selector

        # Try role
        pattern = r'<[^>]*role=["\']([^"\']+)["\'][^>]*'
        matches = re.findall(pattern, page_html)
        if matches:
            selector = f'[role="{matches[0]}"]'
            logger.info(f"Found role alternative: {selector}")
            return selector

        # Try id
        pattern = r'<[^>]*id=["\']([^"\']+)["\']'
        matches = re.findall(pattern, page_html)
        if matches:
            selector = f'#{matches[0]}'
            logger.info(f"Found id alternative: {selector}")
            return selector

        return None

    def _analyze_assertion_error(self, error_msg: str) -> dict:
        """Analyze assertion error to compare expected vs actual."""
        expected_match = re.search(r"expected[:\s]+(.+?)(?:\s+but|\s+actual|\s+got|\s+found)", error_msg, re.IGNORECASE)
        actual_match = re.search(r"(?:actual|got|found)[:\s]+(.+?)(?:\s*$)", error_msg, re.IGNORECASE)

        expected = expected_match.group(1) if expected_match else "unknown"
        actual = actual_match.group(1) if actual_match else "unknown"

        diagnosis = f"Assertion mismatch - expected '{expected}' but got '{actual}'"

        return {
            "type": "assertion_wrong",
            "diagnosis": diagnosis,
            "fixable": True,
            "suggested_fix": diagnosis,
        }

    def generate_fix(
        self,
        test_file: str,
        analysis: dict,
        page_info: Optional[dict] = None,
    ) -> str:
        """Generate updated test code based on the analysis.

        Args:
            test_file: Path to the test file (currently unused, could be used for context)
            analysis: Analysis result from analyze_failure()
            page_info: Optional dict with page information including HTML

        Returns:
            New file content as a string
        """
        # Read the current test file content
        try:
            if hasattr(self.ci_manager, "get_file_content"):
                current_content = self.ci_manager.get_file_content(test_file)
            else:
                with open(test_file, "r") as f:
                    current_content = f.read()
        except Exception as e:
            logger.error(f"Failed to read test file: {e}")
            current_content = ""

        failure_type = analysis["type"]
        diagnosis = analysis.get("diagnosis", "")

        if failure_type == "selector_stale":
            return self._fix_selector_stale(current_content, diagnosis, page_info)
        elif failure_type == "assertion_wrong":
            return self._fix_assertion_wrong(current_content, diagnosis, analysis)
        else:
            # Non-fixable, return unchanged
            return current_content

    def _fix_selector_stale(
        self,
        current_content: str,
        diagnosis: str,
        page_info: Optional[dict],
    ) -> str:
        """Fix selector staleness by updating to new selector."""
        # Extract new selector from diagnosis if available
        selector_match = re.search(r"Found alternative:\s*([^\.]+)", diagnosis)
        new_selector = selector_match.group(1) if selector_match else None

        if not new_selector:
            return current_content

        # Try to find and replace the stale selector in the content
        # Look for common patterns like page.get_by(), locator(), etc.

        # Pattern to match common locator calls
        locator_patterns = [
            r'(page\.get_by_[a-z_]+\(["\'][^"\']+["\'])',
            r'(page\.locator\(["\'][^"\']+["\'])',
            r'(["\'][^"\']+["\'](?:\.first|\.nth\(\d+\)))',
        ]

        for pattern in locator_patterns:
            if re.search(pattern, current_content):
                # Replace the first occurrence with new selector
                new_content = re.sub(pattern, f'{new_selector}', current_content, count=1)
                if new_content != current_content:
                    return new_content

        # If no pattern matched, append a comment about the fix
        fix_comment = f"\n# FIXME (self-healer): Selector updated - {diagnosis}\n"
        return current_content + fix_comment

    def _fix_assertion_wrong(
        self,
        current_content: str,
        diagnosis: str,
        analysis: dict,
    ) -> str:
        """Fix assertion by updating expected value."""
        # Extract expected/actual from diagnosis
        exp_match = re.search(r"expected\s+['\"]([^'\"]+)['\"]", diagnosis)
        actual_match = re.search(r"got\s+['\"]([^'\"]+)['\"]", diagnosis)

        if exp_match and actual_match:
            expected = exp_match.group(1)
            actual = actual_match.group(1)

            # Try to fix common assertion patterns
            # Replace expected value with actual value
            patterns = [
                (rf'assert.*==\s*["\']({re.escape(expected)})["\']', f'assert actual == "{actual}"'),
                (rf'assert.*equal\(.*,\s*["\']({re.escape(expected)})["\']', f'assertEqual(actual, "{actual}")'),
            ]

            for pattern, replacement in patterns:
                new_content = re.sub(pattern, replacement, current_content)
                if new_content != current_content:
                    return new_content

        # If couldn't fix, add comment
        fix_comment = f"\n# FIXME (self-healer): Assertion may need review - {diagnosis}\n"
        return current_content + fix_comment

    def apply_fix(self, test_file: str, new_content: str, diagnosis: str) -> dict:
        """Write fix to file and create draft PR with explanation.

        Args:
            test_file: Path to the test file
            new_content: The fixed file content
            diagnosis: Explanation of what was fixed

        Returns:
            dict with status, pr_url, message
        """
        try:
            # Create a new branch for the fix
            branch_name = f"self-healer/fix-{hash(diagnosis) % 10000:04d}"

            try:
                self.ci_manager.create_branch(branch_name)
            except Exception as e:
                logger.warning(f"Could not create branch: {e}")
                branch_name = None

            # Update the file
            if hasattr(self.ci_manager, "update_file"):
                self.ci_manager.update_file(
                    test_file,
                    new_content,
                    f"Self-healer: {diagnosis}",
                    branch=branch_name,
                )
            else:
                with open(test_file, "w") as f:
                    f.write(new_content)

            # Create PR if we have a branch
            pr_number = None
            if branch_name and hasattr(self.ci_manager, "create_pr"):
                try:
                    title = f"Self-healer: Fix test failure"
                    body = f"""## Self-Healer Fix

**Diagnosis:** {diagnosis}

This PR was automatically created by the self-healer to address a test failure.

Please review the changes and merge if appropriate.

---
*This is an automated fix - please verify before merging.*
"""
                    pr_number = self.ci_manager.create_pr(
                        title=title,
                        body=body,
                        head=branch_name,
                        base="main",
                        draft=True,
                    )
                except Exception as e:
                    logger.warning(f"Could not create PR: {e}")

            return {
                "status": "fixed",
                "pr_url": f"https://github.com/pull/{pr_number}" if pr_number else None,
                "message": f"Fix applied: {diagnosis}",
            }

        except Exception as e:
            logger.error(f"Failed to apply fix: {e}")
            return {
                "status": "flagged",
                "pr_url": None,
                "message": f"Failed to apply fix: {str(e)}",
            }

    def retry_test(self, test_file: str) -> dict:
        """Retry a test once before flagging for human review.

        Args:
            test_file: Path to the test file to retry

        Returns:
            dict with status, message
        """
        # This is a placeholder - actual retry would involve running pytest
        # For now, we'll just return a status indicating retry was attempted
        logger.info(f"Retrying test: {test_file}")

        return {
            "status": "retry_attempted",
            "message": f"Test retry attempted for {test_file}",
        }

    def heal(
        self,
        test_file: str,
        error: Exception,
        screenshot: Optional[bytes] = None,
        page_html: Optional[str] = None,
        page_info: Optional[dict] = None,
    ) -> dict:
        """Main entry point for self-healing.

        Args:
            test_file: Path to the test file
            error: The exception that was raised
            screenshot: Optional screenshot of the failure state
            page_html: Optional HTML of the page at failure time
            page_info: Optional dict with page information (html, url, etc.)

        Returns:
            dict with keys:
                - status: "fixed" | "flagged"
                - pr_url: URL of created PR, or None
                - message: Human-readable status message
        """
        # Extract page_html from page_info if not provided directly
        if page_html is None and page_info and isinstance(page_info, dict):
            page_html = page_info.get("html")

        # Analyze the failure
        analysis = self.analyze_failure(test_file, error, screenshot, page_html)

        logger.info(f"Failure analysis: {analysis}")

        # Handle infrastructure errors - retry once first
        if analysis["type"] == "infrastructure":
            retry_result = self.retry_test(test_file)
            if retry_result["status"] == "fixed":
                return {
                    "status": "fixed",
                    "pr_url": None,
                    "message": "Infrastructure issue resolved on retry",
                }
            else:
                return {
                    "status": "flagged",
                    "pr_url": None,
                    "message": f"Infrastructure failure after retry: {analysis['diagnosis']}",
                }

        # Non-fixable types are flagged for human review
        if not analysis["fixable"]:
            return {
                "status": "flagged",
                "pr_url": None,
                "message": f"Non-fixable failure type '{analysis['type']}': {analysis['diagnosis']}",
            }

        # Generate and apply the fix
        try:
            new_content = self.generate_fix(test_file, analysis, page_info)
            result = self.apply_fix(test_file, new_content, analysis["diagnosis"])
            return result
        except Exception as e:
            logger.error(f"Healing failed: {e}")
            return {
                "status": "flagged",
                "pr_url": None,
                "message": f"Healing failed: {str(e)}",
            }