import os
import sys

sys.path.insert(0, '../libs')
from libs import cmd_run

from ci import Base, Verdict, EndTest, submit_pw_check


class VerifyFixes(Base):
    """Verify Fixes tag class
    Verifies that Fixes: tags in commits reference valid commits with correct
    format and subject.
    """

    def __init__(self, ci_data):

        self.name = "VerifyFixes"
        self.desc = "Verify Fixes tag format and validity"
        self.ci_data = ci_data

        # Script location - relative to the action repo
        self.script = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), 'scripts', 'verify_fixes.sh')

        super().__init__()

        self.log_dbg("Initialization completed")

    def run(self):
        self.log_dbg("Run")
        self.start_timer()

        git_range = "origin/master..HEAD"

        cmd = [self.script, git_range]
        (ret, stdout, stderr) = cmd_run(cmd, cwd=self.ci_data.src_dir)

        if ret == 0:
            submit_pw_check(self.ci_data.pw, self.ci_data.patch_1,
                            self.name, Verdict.PASS,
                            "VerifyFixes PASS",
                            None, self.ci_data.config['dry_run'])
            self.success()
            return

        # Fixes tag verification failed
        outstr = stdout + "\n" + stderr if stderr else stdout
        submit_pw_check(self.ci_data.pw, self.ci_data.patch_1,
                        self.name, Verdict.WARNING,
                        outstr,
                        None, self.ci_data.config['dry_run'])
        self.add_failure(outstr)
        raise EndTest

    def post_run(self):
        self.log_dbg("Post Run...")
