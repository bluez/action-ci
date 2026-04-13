import os
import sys

sys.path.insert(0, '../libs')
from libs import cmd_run

from ci import Base, Verdict, EndTest, submit_pw_check

class GitLint(Base):
    """Git Lint class
    This class runs gitlint with the patches in the series
    """

    def __init__(self, ci_data, gitlint_config=None):

        self.name = "GitLint"
        self.desc = "Run gitlint"
        self.ci_data = ci_data

        # Set the gitlint config file
        if gitlint_config:
            self.gitlint_config = gitlint_config
        else:
            self.gitlint_config = '/gitlint'

        super().__init__()

        self.log_dbg("Initialization completed")

    def run(self):
        self.log_dbg("Run")

        self.start_timer()

        # Get patches from patchwork series
        for patch in self.ci_data.series['patches']:
            self.log_dbg(f"Patch ID: {patch['id']}")

            (ret, stdout, stderr) = self._gitlint(patch)
            if ret == 0:
                # GitLint PASS
                self.log_dbg("Test result PASSED")
                submit_pw_check(self.ci_data.pw, patch,
                                self.name, Verdict.PASS,
                                "Gitlint PASS",
                                None, self.ci_data.config["dry_run"])
                continue

            submit_pw_check(self.ci_data.pw, patch,
                            self.name, Verdict.FAIL,
                            stderr,
                            None, self.ci_data.config["dry_run"])
            self.log_dbg("Test result FAIL")
            self.add_failure(f"{patch['name']}\n{stderr}")

        if self.verdict == Verdict.FAIL:
            self.log_info(f"Test Verdict: {self.verdict.name}")
            raise EndTest

        self.success()
        self.log_info(f"Test Verdict: {self.verdict.name}")

    def _gitlint(self, patch):
        patch_msg = self.ci_data.pw.save_patch_msg(patch['id'],
                            os.path.join(self.ci_data.patch_root,
                                         f"{patch['id']}.msg"))
        self.log_dbg(f"Patch msg: {patch_msg}")
        cmd = ['gitlint', '-C', self.gitlint_config, '--msg-filename', patch_msg]
        return cmd_run(cmd, cwd=self.ci_data.src_dir)

    def post_run(self):
        self.log_dbg("Post Run...")
