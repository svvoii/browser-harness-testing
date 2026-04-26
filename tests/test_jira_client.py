"""Tests for JiraClient stub."""

import pytest
from agent.jira_client import JiraClient


def test_jira_client_init():
    """Test JiraClient initializes with correct attributes."""
    client = JiraClient(
        jira_url="https://example.atlassian.net",
        api_token="secret-token",
        project_key="PROJ"
    )
    assert client.jira_url == "https://example.atlassian.net"
    assert client.api_token == "secret-token"
    assert client.project_key == "PROJ"


def test_jira_client_init_with_defaults():
    """Test JiraClient initializes with None defaults."""
    client = JiraClient()
    assert client.jira_url is None
    assert client.api_token is None
    assert client.project_key is None


@pytest.mark.parametrize("method_name,args", [
    ("create_ticket", ("summary", "description")),
    ("update_ticket", ("PROJ-123",)),
    ("add_comment", ("PROJ-123", "comment text")),
    ("close_ticket", ("PROJ-123",)),
    ("link_test_to_ticket", ("tests/test_example.py", "PROJ-123")),
    ("get_ticket_status", ("PROJ-123",)),
    ("search_tickets", ("project = PROJ",)),
])
def test_methods_raise_not_implemented_with_args(method_name, args):
    """Test that all JiraClient methods raise NotImplementedError with various arguments."""
    client = JiraClient()
    method = getattr(client, method_name)
    with pytest.raises(NotImplementedError):
        method(*args)