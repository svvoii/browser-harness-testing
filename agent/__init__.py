"""AI Agent service for browser-harness-testing."""

__all__ = [
    "AppModel",
    "CIManager",
    "TestAuthor",
    "SelfHealer",
    "JiraClient",
]

# Import with fallbacks for modules that may not exist yet
try:
    from agent.app_model import AppModel
except ImportError:
    AppModel = None

try:
    from agent.ci_manager import CIManager
except ImportError:
    CIManager = None

try:
    from agent.test_author import TestAuthor
except ImportError:
    TestAuthor = None

try:
    from agent.self_healer import SelfHealer
except ImportError:
    SelfHealer = None

try:
    from agent.jira_client import JiraClient
except ImportError:
    JiraClient = None
