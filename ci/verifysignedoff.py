import os
import sys

sys.path.insert(0, '../libs')
from libs import cmd_run

from ci import Base, Verdict, EndTest, submit_pw_check


class VerifySignedoff(Base):
    """Verify Signed-off-by class
    Verifies that author and committer have matching Signed-off-by lines.
    """

    def __init__(self, ci_data):

        self.name = "VerifySignedoff"
        self.desc = "Verify Signed-off-by chain"
        self.ci_data = ci_data

        # Script location - relative to the action repo
        self.script = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), 'scripts', 'verify_signedoff.sh')

        super().__init__()

        self.log_dbg("Initialization completed")

    def run(self):
        self.log_dbg("Run")
        self.start_timer()

        # Use HEAD^2 to skip GitHub's merge commit (refs/pull/N/merge)
        # and only check the actual PR commits
        git_range = "origin/master..HEAD^2"

        cmd = [self.script, git_range]
        (ret, stdout, stderr) = cmd_run(cmd, cwd=self.ci_data.src_dir)

        if ret == 0:
            submit_pw_check(self.ci_data.pw, self.ci_data.patch_1,
                            self.name, Verdict.PASS,
                            "VerifySignedoff PASS",
                            None, self.ci_data.config['dry_run'])
            self.success()
            return

        # Signed-off-by verification failed
        outstr = stdout + "\n" + stderr if stderr else stdout
        submit_pw_check(self.ci_data.pw, self.ci_data.patch_1,
                        self.name, Verdict.WARNING,
                        outstr,
                        None, self.ci_data.config['dry_run'])
        self.add_failure(outstr)
        raise EndTest

    def post_run(self):
        self.log_dbg("Post Run...")
