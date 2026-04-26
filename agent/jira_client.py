class JiraClient:
    """JIRA integration stub. Implementation deferred until JIRA project details are known."""

    def __init__(self, jira_url=None, api_token=None, project_key=None):
        self.jira_url = jira_url
        self.api_token = api_token
        self.project_key = project_key

    def create_ticket(self, summary, description, labels=None, assignee=None):
        """Create a JIRA ticket. Raises NotImplementedError until JIRA details are defined."""
        raise NotImplementedError("JIRA integration deferred until project details are known")

    def update_ticket(self, ticket_id, **fields):
        raise NotImplementedError

    def add_comment(self, ticket_id, comment):
        raise NotImplementedError

    def close_ticket(self, ticket_id, resolution=None):
        raise NotImplementedError

    def link_test_to_ticket(self, test_file, ticket_id):
        """Link a test file to a JIRA ticket."""
        raise NotImplementedError

    def get_ticket_status(self, ticket_id):
        raise NotImplementedError

    def search_tickets(self, query):
        """Search JIRA tickets. Returns list of ticket dicts."""
        raise NotImplementedError