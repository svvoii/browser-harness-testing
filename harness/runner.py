"""Test executor with browser lifecycle management and artifact capture."""

import glob
import importlib.util
import os
import sys
import traceback
from pathlib import Path

# browser_harness/ is a subpackage of this project — no sys.path hacking needed.
from browser_harness import admin, helpers

capture_screenshot = helpers.capture_screenshot
drain_events      = helpers.drain_events
js                = helpers.js
ensure_daemon     = admin.ensure_daemon

NAME = "browser-harness-testing"
SOCK = f"/tmp/bu-{NAME}.sock"
PID  = f"/tmp/bu-{NAME}.pid"


def setup_browser():
    """Ensure daemon is running and browser is connected. Called before test run."""
    ensure_daemon(wait=60.0, name=None)


def teardown_browser():
    """Cleanup after test run. Don't kill daemon — leave for next run."""
    pass


def run_test_file(file_path, results_dir="test-results/"):
    """
    Run a single test file.
    Imports and executes the file's test functions (functions starting with 'test_').
    Returns: {"status": "pass"|"fail", "error": str|None, "screenshot": str|None}
    """
    Path(results_dir).mkdir(parents=True, exist_ok=True)

    # Import the test module
    spec   = importlib.util.spec_from_file_location("test_module", file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["test_module"] = module

    try:
        spec.loader.exec_module(module)
    except Exception as e:
        return _fail_result(file_path, e, results_dir)

    # Collect test functions
    test_funcs = [
        (name, obj) for name, obj in vars(module).items()
        if name.startswith("test_") and callable(obj)
    ]

    if not test_funcs:
        return {"status": "pass", "error": None, "screenshot": None}

    # Run each test function
    for name, func in test_funcs:
        try:
            func()
        except Exception as e:
            return _fail_result(file_path, e, results_dir, test_name=name)

    return {"status": "pass", "error": None, "screenshot": None}


def _fail_result(file_path, error, results_dir, test_name=None):
    """Capture artifacts on test failure."""
    Path(results_dir).mkdir(parents=True, exist_ok=True)

    base       = Path(file_path).stem
    test_part  = f"_{test_name}" if test_name else ""
    screenshot_path = os.path.join(results_dir, f"{base}{test_part}_failure.png")
    html_path       = os.path.join(results_dir, f"{base}{test_part}_failure.html")

    # Capture screenshot
    screenshot = None
    try:
        capture_screenshot(screenshot_path)
        screenshot = screenshot_path
    except Exception:
        pass

    # Save page HTML
    try:
        html = js("document.documentElement.outerHTML")
        if html:
            Path(html_path).write_text(html)
    except Exception:
        pass

    # Capture console messages
    try:
        events = drain_events()
        if events:
            import json
            log_path = os.path.join(results_dir, f"{base}{test_part}_console.json")
            Path(log_path).write_text(json.dumps(events, default=str))
    except Exception:
        pass

    # Format error
    tb_str  = "".join(traceback.format_exception(type(error), error, error.__traceback__))
    error_msg = f"{test_name}: {error}\n{tb_str}" if test_name else f"{error}\n{tb_str}"

    return {
        "status":   "fail",
        "error":    error_msg,
        "screenshot": screenshot,
    }


def run_tests(test_path="tests/", results_dir="test-results/", verbose=True):
    """
    Run all test files in test_path.

    - test_path:   directory or single file glob pattern
    - results_dir: where to store artifacts (screenshots, HTML, logs)
    - verbose:     print progress

    Returns: (passed_count, failed_count, results_list)
    Each result: {"file": str, "status": "pass"|"fail", "error": str|None, "screenshot": str|None}
    """
    Path(results_dir).mkdir(parents=True, exist_ok=True)

    # Resolve test files
    if os.path.isfile(test_path):
        test_files = [test_path]
    elif os.path.isdir(test_path):
        test_files = glob.glob(os.path.join(test_path, "*.py"))
    else:
        test_files = glob.glob(test_path)

    test_files = [f for f in test_files if not os.path.basename(f).startswith("_")]

    if not test_files:
        if verbose:
            print(f"No test files found in {test_path}")
        return 0, 0, []

    results = []
    passed  = 0
    failed  = 0

    for file_path in sorted(test_files):
        if verbose:
            print(f"Running {file_path}...", end=" ", flush=True)

        result = run_test_file(file_path, results_dir)
        results.append({
            "file":     file_path,
            "status":   result["status"],
            "error":    result["error"],
            "screenshot": result["screenshot"],
        })

        if result["status"] == "pass":
            passed += 1
            if verbose:
                print("PASS")
        else:
            failed += 1
            if verbose:
                print("FAIL")

    # Summary
    if verbose:
        print(f"\n{'='*60}")
        print(f"Results: {passed} passed, {failed} failed, {len(test_files)} total")
        if failed > 0:
            print("\nFailures:")
            for r in results:
                if r["status"] == "fail":
                    print(f"  {r['file']}: {r['error'][:200]}...")
                    if r["screenshot"]:
                        print(f"    Screenshot: {r['screenshot']}")

    return passed, failed, results


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Run browser harness tests")
    parser.add_argument("test_path", nargs="?", default="tests/",
                        help="Test file or directory (default: tests/)")
    parser.add_argument("--results-dir", default="test-results/",
                        help="Directory for test artifacts")
    parser.add_argument("-v", "--verbose", action="store_true", default=True,
                        help="Verbose output")
    parser.add_argument("-q", "--quiet", action="store_true",
                        help="Quiet output (no progress)")
    args = parser.parse_args()

    verbose = args.verbose and not args.quiet

    setup_browser()
    try:
        passed, failed, results = run_tests(
            test_path=args.test_path,
            results_dir=args.results_dir,
            verbose=verbose,
        )
    finally:
        teardown_browser()

    # Exit code for CI
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
