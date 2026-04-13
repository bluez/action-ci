import os
import sys

sys.path.insert(0, '../libs')
from libs import cmd_run

from ci import Base, Verdict, EndTest, submit_pw_check

class CheckPatch(Base):
    """Check Patch class
    This class runs the checkpatch.pl with the patches in the series.
    """

    def __init__(self, ci_data, checkpatch_pl=None, ignore=None):

        self.name = "CheckPatch"
        self.desc = "Run checkpatch.pl script"
        self.ignore = ignore
        self.ci_data = ci_data

        # Set the checkpatch.pl script
        if checkpatch_pl:
            self.checkpatch_pl = checkpatch_pl
        else:
            self.checkpatch_pl = '/usr/bin/checkpatch.pl'

        super().__init__()

        self.log_dbg("Initialization completed")

    def run(self):

        self.log_dbg("Run")
        self.start_timer()

        # Get patches from patchwork series
        for patch in self.ci_data.series['patches']:
            self.log_dbg(f"Patch ID: {patch['id']}")

            (ret, stdout, stderr) = self._checkpatch(patch)
            if ret == 0:
                # CheckPatch PASS
                self.log_dbg("Test result PASSED")
                submit_pw_check(self.ci_data.pw, patch,
                                self.name, Verdict.PASS,
                                "CheckPatch PASS",
                                None, self.ci_data.config['dry_run'])
                continue

            # checkpatch script sends STDERR to STDOUT. so combint stdout and
            # stderr together before processing the output
            outstr = stdout + "\n" + stderr
            msg = f"{patch['name']}\n{outstr}"
            if outstr.find("ERROR:") != -1:
                self.log_dbg("Test result FAIL")
                submit_pw_check(self.ci_data.pw, patch,
                                self.name, Verdict.FAIL,
                                outstr,
                                None, self.ci_data.config['dry_run'])
                self.add_failure(msg)
                continue

            if outstr.find("WARNING:") != -1:
                self.log_dbg("Test result WARNING")
                submit_pw_check(self.ci_data.pw, patch,
                                self.name, Verdict.WARNING,
                                outstr,
                                None, self.ci_data.config['dry_run'])
                self.add_failure(msg)
                continue

        # Overall result
        if self.verdict == Verdict.FAIL:
            self.log_info(f"Test Verdict: {self.verdict.name}")
            raise EndTest

        self.success()
        self.log_info(f"Test Verdict: {self.verdict.name}")

    def _checkpatch(self, patch):
        cmd = [self.checkpatch_pl]
        if self.ignore:
            cmd.append('--ignore')
            cmd.append(self.ignore)

        patch_file = self.ci_data.pw.save_patch_mbox(patch['id'],
                            os.path.join(self.ci_data.patch_root,
                                         f"{patch['id']}.patch"))
        self.log_dbg(f"Patch file: {patch_file}")
        cmd.append(patch_file)
        return cmd_run(cmd, cwd=self.ci_data.src_dir)

    def post_run(self):
        self.log_dbg("Post Run...")
