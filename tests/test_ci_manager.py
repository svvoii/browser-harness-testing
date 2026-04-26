"""Tests for agent/ci_manager.py — mocked since we may not have a real GitHub token."""

import pytest
from unittest.mock import MagicMock, patch


class TestCIManagerInit:
    """Test CIManager initialization."""

    @patch.dict("os.environ", {"GITHUB_TOKEN": "test-token", "GITHUB_REPOSITORY": "owner/repo"})
    def test_init_from_env(self):
        """Test initialization from environment variables."""
        from agent.ci_manager import CIManager

        manager = CIManager()
        assert manager._token == "test-token"
        assert manager._owner == "owner"
        assert manager._repo_name == "repo"

    @patch.dict("os.environ", {"GITHUB_TOKEN": "test-token", "GITHUB_REPOSITORY": "owner/repo"})
    def test_init_with_args_override_env(self):
        """Test that init args override environment variables."""
        from agent.ci_manager import CIManager

        manager = CIManager(github_token="arg-token", owner="arg-owner", repo="arg-repo")
        assert manager._token == "arg-token"
        assert manager._owner == "arg-owner"
        assert manager._repo_name == "arg-repo"

    def test_init_no_token(self):
        """Test initialization without token (anonymous access)."""
        with patch.dict("os.environ", {}, clear=True):
            from agent.ci_manager import CIManager

            manager = CIManager(owner="owner", repo="repo")
            assert manager._token is None


class TestCIManagerGetRepo:
    """Test get_repo method."""

    @patch.dict("os.environ", {"GITHUB_TOKEN": "test-token", "GITHUB_REPOSITORY": "owner/repo"})
    def test_get_repo_caches(self):
        """Test that get_repo caches the repository."""
        from agent.ci_manager import CIManager

        manager = CIManager()
        mock_repo = MagicMock()

        with patch.object(manager._github, "get_repo", return_value=mock_repo) as mock_get_repo:
            result1 = manager.get_repo()
            result2 = manager.get_repo()

            assert result1 is result2
            assert result1 is mock_repo
            mock_get_repo.assert_called_once()


class TestCIManagerPostComment:
    """Test post_pr_comment method."""

    @patch.dict("os.environ", {"GITHUB_TOKEN": "test-token", "GITHUB_REPOSITORY": "owner/repo"})
    def test_post_pr_comment(self):
        """Test posting a PR comment."""
        from agent.ci_manager import CIManager

        manager = CIManager()
        mock_pr = MagicMock()

        with patch.object(manager, "get_repo", return_value=MagicMock(get_pull=lambda n: mock_pr)):
            manager.post_pr_comment(123, "Test comment")
            mock_pr.create_issue_comment.assert_called_once_with("Test comment")


class TestCIManagerGetComments:
    """Test get_pr_comments method."""

    @patch.dict("os.environ", {"GITHUB_TOKEN": "test-token", "GITHUB_REPOSITORY": "owner/repo"})
    def test_get_pr_comments(self):
        """Test getting PR comments."""
        from agent.ci_manager import CIManager

        manager = CIManager()
        mock_comments = [MagicMock(), MagicMock()]
        mock_pr = MagicMock(get_issue_comments=lambda: mock_comments)

        with patch.object(manager, "get_repo", return_value=MagicMock(get_pull=lambda n: mock_pr)):
            result = manager.get_pr_comments(123)
            assert result == mock_comments


class TestCIManagerUpdateStatus:
    """Test update_commit_status method."""

    @patch.dict("os.environ", {"GITHUB_TOKEN": "test-token", "GITHUB_REPOSITORY": "owner/repo"})
    def test_update_commit_status_success(self):
        """Test updating commit status."""
        from agent.ci_manager import CIManager

        manager = CIManager()
        mock_commit = MagicMock()

        with patch.object(manager, "get_repo", return_value=MagicMock(get_commit=lambda s: mock_commit)):
            manager.update_commit_status("abc123", "success", "Build passed")
            mock_commit.create_status.assert_called_once_with(
                state="success",
                description="Build passed",
                target_url=None,
            )

    @patch.dict("os.environ", {"GITHUB_TOKEN": "test-token", "GITHUB_REPOSITORY": "owner/repo"})
    def test_update_commit_status_invalid_state(self):
        """Test that invalid state raises ValueError."""
        from agent.ci_manager import CIManager

        manager = CIManager()
        with pytest.raises(ValueError, match="Invalid state"):
            manager.update_commit_status("abc123", "invalid_state", "description")

    @patch.dict("os.environ", {"GITHUB_TOKEN": "test-token", "GITHUB_REPOSITORY": "owner/repo"})
    def test_update_commit_status_with_target_url(self):
        """Test updating commit status with target URL."""
        from agent.ci_manager import CIManager

        manager = CIManager()
        mock_commit = MagicMock()

        with patch.object(manager, "get_repo", return_value=MagicMock(get_commit=lambda s: mock_commit)):
            manager.update_commit_status("abc123", "pending", "Build running", "https://example.com")
            mock_commit.create_status.assert_called_once_with(
                state="pending",
                description="Build running",
                target_url="https://example.com",
            )


class TestCIManagerCreatePR:
    """Test create_pr method."""

    @patch.dict("os.environ", {"GITHUB_TOKEN": "test-token", "GITHUB_REPOSITORY": "owner/repo"})
    def test_create_pr(self):
        """Test creating a PR."""
        from agent.ci_manager import CIManager

        manager = CIManager()
        mock_pr = MagicMock(number=42)

        with patch.object(manager, "get_repo", return_value=MagicMock(create_pull=lambda **k: mock_pr)):
            result = manager.create_pr("Title", "Body", "feature-branch")
            assert result == 42

    @patch.dict("os.environ", {"GITHUB_TOKEN": "test-token", "GITHUB_REPOSITORY": "owner/repo"})
    def test_create_pr_draft_default(self):
        """Test that PRs are created as draft by default."""
        from agent.ci_manager import CIManager

        manager = CIManager()
        mock_pr = MagicMock()

        mock_repo = MagicMock()
        mock_repo.create_pull.return_value = mock_pr

        with patch.object(manager, "get_repo", return_value=mock_repo):
            manager.create_pr("Title", "Body", "feature-branch")
            # Verify draft=True was passed
            mock_repo.create_pull.assert_called_once()
            call_kwargs = mock_repo.create_pull.call_args[1]
            assert call_kwargs["draft"] is True


class TestCIManagerUpdatePR:
    """Test update_pr method."""

    @patch.dict("os.environ", {"GITHUB_TOKEN": "test-token", "GITHUB_REPOSITORY": "owner/repo"})
    def test_update_pr_title(self):
        """Test updating PR title."""
        from agent.ci_manager import CIManager

        manager = CIManager()
        mock_pr = MagicMock()

        with patch.object(manager, "get_repo", return_value=MagicMock(get_pull=lambda n: mock_pr)):
            manager.update_pr(123, title="New Title")
            mock_pr.edit.assert_called_with(title="New Title")

    @patch.dict("os.environ", {"GITHUB_TOKEN": "test-token", "GITHUB_REPOSITORY": "owner/repo"})
    def test_update_pr_body(self):
        """Test updating PR body."""
        from agent.ci_manager import CIManager

        manager = CIManager()
        mock_pr = MagicMock()

        with patch.object(manager, "get_repo", return_value=MagicMock(get_pull=lambda n: mock_pr)):
            manager.update_pr(123, body="New Body")
            mock_pr.edit.assert_called_with(body="New Body")


class TestCIManagerWorkflowRuns:
    """Test get_workflow_runs method."""

    @patch.dict("os.environ", {"GITHUB_TOKEN": "test-token", "GITHUB_REPOSITORY": "owner/repo"})
    def test_get_workflow_runs(self):
        """Test getting workflow runs."""
        from agent.ci_manager import CIManager

        manager = CIManager()
        mock_runs = [MagicMock(), MagicMock()]

        with patch.object(manager, "get_repo", return_value=MagicMock(get_workflow_runs=lambda **k: mock_runs)):
            result = manager.get_workflow_runs(workflow_name="test.yml", branch="main")
            assert result == mock_runs


class TestCIManagerRunArtifact:
    """Test get_run_artifact method."""

    @patch.dict("os.environ", {"GITHUB_TOKEN": "test-token", "GITHUB_REPOSITORY": "owner/repo"})
    def test_get_run_artifact_found(self):
        """Test getting an artifact by name."""
        from agent.ci_manager import CIManager

        manager = CIManager()
        mock_artifact = MagicMock(zipball_url="https://example.com/artifact.zip")
        mock_artifact.name = "test-artifact"

        mock_run = MagicMock(get_artifacts=lambda: iter([mock_artifact]))

        with patch.object(manager, "get_repo", return_value=MagicMock(get_workflow_run=lambda i: mock_run)):
            result = manager.get_run_artifact(123, "test-artifact")
            assert result == "https://example.com/artifact.zip"

    @patch.dict("os.environ", {"GITHUB_TOKEN": "test-token", "GITHUB_REPOSITORY": "owner/repo"})
    def test_get_run_artifact_not_found(self):
        """Test getting an artifact that doesn't exist."""
        from agent.ci_manager import CIManager

        manager = CIManager()
        mock_run = MagicMock(get_artifacts=lambda: [])

        with patch.object(manager, "get_repo", return_value=MagicMock(get_workflow_run=lambda i: mock_run)):
            result = manager.get_run_artifact(123, "nonexistent")
            assert result is None


class TestCIManagerGetChangedFiles:
    """Test get_changed_files method."""

    @patch.dict("os.environ", {"GITHUB_TOKEN": "test-token", "GITHUB_REPOSITORY": "owner/repo"})
    def test_get_changed_files(self):
        """Test getting changed files in a PR."""
        from agent.ci_manager import CIManager

        manager = CIManager()
        mock_file1 = MagicMock(filename="src/app.py")
        mock_file2 = MagicMock(filename="tests/test_app.py")
        mock_pr = MagicMock(get_files=lambda: [mock_file1, mock_file2])

        with patch.object(manager, "get_repo", return_value=MagicMock(get_pull=lambda n: mock_pr)):
            result = manager.get_changed_files(123)
            assert result == ["src/app.py", "tests/test_app.py"]


class TestCIManagerGetFileContent:
    """Test get_file_content method."""

    @patch.dict("os.environ", {"GITHUB_TOKEN": "test-token", "GITHUB_REPOSITORY": "owner/repo"})
    def test_get_file_content(self):
        """Test getting file content."""
        from agent.ci_manager import CIManager

        manager = CIManager()
        mock_contents = MagicMock(decoded_content=b"file content")

        with patch.object(manager, "get_repo", return_value=MagicMock(get_contents=lambda p, ref=None: mock_contents)):
            result = manager.get_file_content("README.md")
            assert result == "file content"


class TestCIManagerUpdateFile:
    """Test update_file method."""

    @patch.dict("os.environ", {"GITHUB_TOKEN": "test-token", "GITHUB_REPOSITORY": "owner/repo"})
    def test_update_existing_file(self):
        """Test updating an existing file."""
        from agent.ci_manager import CIManager

        manager = CIManager()
        mock_existing = MagicMock(sha="abc123")
        mock_repo = MagicMock(get_contents=lambda p, ref=None: mock_existing)

        with patch.object(manager, "get_repo", return_value=mock_repo):
            manager.update_file("README.md", "new content", "Update readme")
            mock_repo.update_file.assert_called_once()

    @patch.dict("os.environ", {"GITHUB_TOKEN": "test-token", "GITHUB_REPOSITORY": "owner/repo"})
    def test_create_new_file(self):
        """Test creating a new file (404 error on get_contents)."""
        from agent.ci_manager import CIManager
        from github.GithubException import GithubException

        manager = CIManager()
        mock_repo = MagicMock()

        error_404 = GithubException(404, "Not found")
        mock_repo.get_contents.side_effect = error_404

        with patch.object(manager, "get_repo", return_value=mock_repo):
            manager.update_file("new_file.txt", "content", "Add new file")
            mock_repo.create_file.assert_called_once()


class TestCIManagerCreateBranch:
    """Test create_branch method."""

    @patch.dict("os.environ", {"GITHUB_TOKEN": "test-token", "GITHUB_REPOSITORY": "owner/repo"})
    def test_create_branch_from_sha(self):
        """Test creating a branch from a specific SHA."""
        from agent.ci_manager import CIManager

        manager = CIManager()
        mock_repo = MagicMock()

        with patch.object(manager, "get_repo", return_value=mock_repo):
            manager.create_branch("feature-branch", "abc123")
            mock_repo.create_git_ref.assert_called_once_with(ref="refs/heads/feature-branch", sha="abc123")

    @patch.dict("os.environ", {"GITHUB_TOKEN": "test-token", "GITHUB_REPOSITORY": "owner/repo"})
    def test_create_branch_default_sha(self):
        """Test creating a branch uses default branch SHA when not specified."""
        from agent.ci_manager import CIManager

        manager = CIManager()
        mock_default_branch = MagicMock()
        mock_default_branch.commit.sha = "default-sha"

        mock_repo = MagicMock(
            default_branch="main",
            get_branch=lambda b: mock_default_branch,
        )

        with patch.object(manager, "get_repo", return_value=mock_repo):
            manager.create_branch("new-branch")
            mock_repo.create_git_ref.assert_called_once_with(ref="refs/heads/new-branch", sha="default-sha")