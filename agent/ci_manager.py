"""GitHub API client for CI interaction.

Used by test_author and self_healer to post comments, create PRs, update statuses.
"""

import os
import logging
from typing import Optional

from github import Github
from github.GithubException import RateLimitExceededException, GithubException
from github.Auth import Token

logger = logging.getLogger(__name__)


class CIManager:
    """GitHub API client for CI interaction."""

    VALID_STATUS_STATES = ("pending", "success", "failure", "error", "cancelled")

    def __init__(
        self,
        github_token: Optional[str] = None,
        owner: Optional[str] = None,
        repo: Optional[str] = None,
    ):
        """Initialize GitHub client.

        Token from env GITHUB_TOKEN or GH_TOKEN if not provided.
        Owner/repo from env GITHUB_REPOSITORY if not provided.
        """
        self._token = github_token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        self._owner = owner or os.environ.get("GITHUB_REPOSITORY", "").split("/")[0]
        self._repo_name = repo or os.environ.get("GITHUB_REPOSITORY", "").split("/")[-1]

        self._github = Github(auth=Token(self._token)) if self._token else Github()
        self._repo = None

    def get_repo(self):
        """Get repository object."""
        if self._repo is None:
            self._repo = self._github.get_repo(f"{self._owner}/{self._repo_name}")
        return self._repo

    def _handle_rate_limit(self, error: RateLimitExceededException):
        """Log rate limit info and potentially wait."""
        logger.warning(
            "GitHub API rate limit exceeded. Reset at: %s",
            error.reset,
        )

    def post_pr_comment(self, pr_number: int, body: str) -> None:
        """Post a comment on a PR."""
        try:
            repo = self.get_repo()
            pr = repo.get_pull(pr_number)
            pr.create_issue_comment(body)
        except RateLimitExceededException as e:
            self._handle_rate_limit(e)
            raise
        except GithubException as e:
            logger.error("Failed to post PR comment: %s", e)
            raise

    def get_pr_comments(self, pr_number: int) -> list:
        """Get all comments on a PR."""
        try:
            repo = self.get_repo()
            pr = repo.get_pull(pr_number)
            return list(pr.get_issue_comments())
        except RateLimitExceededException as e:
            self._handle_rate_limit(e)
            raise
        except GithubException as e:
            logger.error("Failed to get PR comments: %s", e)
            raise

    def update_commit_status(
        self,
        sha: str,
        state: str,
        description: str,
        target_url: Optional[str] = None,
    ) -> None:
        """Update commit status (pending/success/failure/error/cancelled)."""
        if state not in self.VALID_STATUS_STATES:
            raise ValueError(f"Invalid state: {state}. Must be one of {self.VALID_STATUS_STATES}")

        try:
            repo = self.get_repo()
            repo.get_commit(sha).create_status(
                state=state,
                description=description,
                target_url=target_url,
            )
        except RateLimitExceededException as e:
            self._handle_rate_limit(e)
            raise
        except GithubException as e:
            logger.error("Failed to update commit status: %s", e)
            raise

    def create_pr(
        self,
        title: str,
        body: str,
        head: str,
        base: str = "main",
        draft: bool = True,
    ) -> int:
        """Create a PR (draft by default). Returns PR number."""
        try:
            repo = self.get_repo()
            pr = repo.create_pull(
                title=title,
                body=body,
                head=head,
                base=base,
                draft=draft,
            )
            return pr.number
        except RateLimitExceededException as e:
            self._handle_rate_limit(e)
            raise
        except GithubException as e:
            logger.error("Failed to create PR: %s", e)
            raise

    def update_pr(self, pr_number: int, title: Optional[str] = None, body: Optional[str] = None) -> None:
        """Update PR title/body."""
        try:
            repo = self.get_repo()
            pr = repo.get_pull(pr_number)
            if title is not None:
                pr.edit(title=title)
            if body is not None:
                pr.edit(body=body)
        except RateLimitExceededException as e:
            self._handle_rate_limit(e)
            raise
        except GithubException as e:
            logger.error("Failed to update PR: %s", e)
            raise

    def get_workflow_runs(
        self,
        workflow_name: Optional[str] = None,
        branch: Optional[str] = None,
    ) -> list:
        """Get recent workflow runs. Returns list of runs."""
        try:
            repo = self.get_repo()
            runs = repo.get_workflow_runs(workflow_id=workflow_name, branch=branch)
            return list(runs)
        except RateLimitExceededException as e:
            self._handle_rate_limit(e)
            raise
        except GithubException as e:
            logger.error("Failed to get workflow runs: %s", e)
            raise

    def get_run_artifact(self, run_id: int, artifact_name: str) -> Optional[str]:
        """Get artifact download URL for a run."""
        try:
            repo = self.get_repo()
            run = repo.get_workflow_run(run_id)
            artifacts = run.get_artifacts()
            for artifact in artifacts:
                if artifact.name == artifact_name:
                    return artifact.zipball_url
            return None
        except RateLimitExceededException as e:
            self._handle_rate_limit(e)
            raise
        except GithubException as e:
            logger.error("Failed to get run artifact: %s", e)
            raise

    def get_run_status(self, run_id: int) -> Optional[str]:
        """Get conclusion status of a run."""
        try:
            repo = self.get_repo()
            run = repo.get_workflow_run(run_id)
            return run.conclusion
        except RateLimitExceededException as e:
            self._handle_rate_limit(e)
            raise
        except GithubException as e:
            logger.error("Failed to get run status: %s", e)
            raise

    def get_changed_files(self, pr_number: int) -> list:
        """Get list of files changed in a PR."""
        try:
            repo = self.get_repo()
            pr = repo.get_pull(pr_number)
            return [f.filename for f in pr.get_files()]
        except RateLimitExceededException as e:
            self._handle_rate_limit(e)
            raise
        except GithubException as e:
            logger.error("Failed to get changed files: %s", e)
            raise

    def get_file_content(self, path: str, ref: Optional[str] = None) -> str:
        """Get file content from repo."""
        try:
            repo = self.get_repo()
            contents = repo.get_contents(path, ref=ref)
            if hasattr(contents, "decoded_content"):
                return contents.decoded_content.decode("utf-8")
            return contents
        except RateLimitExceededException as e:
            self._handle_rate_limit(e)
            raise
        except GithubException as e:
            logger.error("Failed to get file content: %s", e)
            raise

    def update_file(
        self,
        path: str,
        content: str,
        message: str,
        branch: Optional[str] = None,
    ) -> None:
        """Update a file in the repo (create or overwrite)."""
        try:
            repo = self.get_repo()
            if branch:
                ref = f"heads/{branch}"
                try:
                    repo.get_git_ref(ref)
                except GithubException:
                    logger.warning("Branch %s does not exist, creating it", branch)

            try:
                existing = repo.get_contents(path, ref=branch)
                repo.update_file(
                    path=path,
                    message=message,
                    content=content,
                    sha=existing.sha,
                    branch=branch,
                )
            except GithubException as e:
                if e.status == 404:
                    repo.create_file(
                        path=path,
                        message=message,
                        content=content,
                        branch=branch,
                    )
                else:
                    raise
        except RateLimitExceededException as e:
            self._handle_rate_limit(e)
            raise
        except GithubException as e:
            logger.error("Failed to update file: %s", e)
            raise

    def create_branch(self, branch_name: str, from_sha: Optional[str] = None) -> None:
        """Create a new branch."""
        try:
            repo = self.get_repo()
            if from_sha is None:
                default_branch = repo.default_branch
                from_sha = repo.get_branch(default_branch).commit.sha

            repo.create_git_ref(ref=f"refs/heads/{branch_name}", sha=from_sha)
        except RateLimitExceededException as e:
            self._handle_rate_limit(e)
            raise
        except GithubException as e:
            logger.error("Failed to create branch: %s", e)
            raise