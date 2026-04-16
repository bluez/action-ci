from datetime import datetime, timezone
from github import Github, GithubException
import re

from libs.utils import log_debug, log_error, log_info

class GithubTool:

    def __init__(self, repo, token=None, checks_token=None):
        self._repo = Github(token).get_repo(repo)
        self._pr = None
        self._prs = None

        # Use a separate Github client for Check Runs API which requires
        # a GitHub App token (the Actions-provided GITHUB_TOKEN), not a PAT.
        if checks_token and checks_token != token:
            self._checks_repo = Github(checks_token).get_repo(repo)
        else:
            self._checks_repo = self._repo

    def get_pr_commits(self, pr_id):
        pr = self.get_pr(pr_id, True)

        return pr.get_commits()

    def get_pr(self, pr_id, force=False):
        if force or self._pr == None:
            self._pr = self._repo.get_pull(pr_id)

        return self._pr

    def get_prs(self, force=False):
        if force or not self._prs:
            self._prs = self._repo.get_pulls()

        return self._prs

    def create_pr(self, title, body, base, head):

        return self._repo.create_pull(title, body, base, head, True)

    def close_pr(self, pr_id):
        pr = self.get_pr(pr_id, force=True)
        pr.edit(state="closed")

        git_ref = self._repo.get_git_ref(f"heads/{pr.head.ref}")
        git_ref.delete()

    def pr_exist_title(self, str):
        if not self._prs:
            self._prs = self.get_prs(force=True)

        for pr in self._prs:
            if re.search(str, pr.title, re.IGNORECASE):
                return True

        return False

    def pr_post_comment(self, pr, comment):

        try:
            pr.create_issue_comment(comment)
        except:
            return False

        return True

    def pr_get_issue_comments(self, pr):
        try:
            comments = pr.get_issue_comments()
        except:
            return None

        return comments

    def pr_close(self, pr):
        pr.edit(state="closed")

    def create_check_run(self, name, head_sha, status='queued',
                         details_url=None):
        """Create a new GitHub Check Run for a specific test.

        Args:
            name: Name of the check (e.g. 'CheckPatch', 'BuildKernel')
            head_sha: The SHA of the commit to associate the check with
            status: Initial status ('queued' or 'in_progress')
            details_url: Optional URL for more details

        Returns:
            CheckRun object on success, None on failure
        """
        try:
            kwargs = {
                'status': status,
                'started_at': datetime.now(timezone.utc),
            }
            if details_url:
                kwargs['details_url'] = details_url
            check_run = self._checks_repo.create_check_run(name, head_sha,
                                                              **kwargs)
            log_debug(f"Created check run '{name}' (id={check_run.id})")
            return check_run
        except GithubException as e:
            log_error(f"Failed to create check run '{name}': {e}")
            return None

    def pr_add_labels(self, pr, labels):
        """Add labels to a PR, creating them if they don't exist.

        Args:
            pr: The PR object
            labels: List of label strings to add

        Returns:
            True on success, False on failure
        """
        try:
            for label_name in labels:
                try:
                    self._repo.get_label(label_name)
                except GithubException:
                    # Label doesn't exist, create it with a blue color
                    self._repo.create_label(label_name, "0075ca")
                    log_debug(f"Created label '{label_name}'")

            pr.add_to_labels(*labels)
            log_debug(f"Added labels to PR: {labels}")
            return True
        except GithubException as e:
            log_error(f"Failed to add labels to PR: {e}")
            return False

    def update_check_run(self, check_run, conclusion, title, summary,
                         text=None):
        """Update a GitHub Check Run with the final result.

        Args:
            check_run: The CheckRun object to update
            conclusion: One of 'success', 'failure', 'neutral', 'cancelled',
                       'skipped', 'timed_out', 'action_required'
            title: Short title for the check output
            summary: Summary of the check result (markdown)
            text: Optional detailed text output (markdown)

        Returns:
            True on success, False on failure
        """
        try:
            output = {
                'title': title,
                'summary': summary,
            }
            if text:
                output['text'] = text

            check_run.edit(
                status='completed',
                conclusion=conclusion,
                completed_at=datetime.now(timezone.utc),
                output=output,
            )
            log_debug(f"Updated check run '{check_run.name}' -> {conclusion}")
            return True
        except GithubException as e:
            log_error(f"Failed to update check run '{check_run.name}': {e}")
            return False
