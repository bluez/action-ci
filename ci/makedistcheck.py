import os
import sys
import shutil

sys.path.insert(0, '../libs')
from libs import cmd_run

from ci import GenericBuild, Verdict, EndTest, submit_pw_check

class MakeDistcheck(GenericBuild):
    """BlueZ Make Distcheck class
    This class runs 'make distcheck'. It expects the source is clean
    """

    def __init__(self, ci_data):
        # For dist check, use the following config params
        # config: --disable-lsan --disable-asan --disable-ubsan
        # For make, use fakeroot

        # Common
        self.name = "MakeDistcheck"
        self.desc = "Run Bluez Make Distcheck"
        self.ci_data = ci_data

        config_params = ["--disable-lsan", "--disable-asan", "--disable-ubsan"]
        make_params = ["distcheck"]
        super().__init__(config_params=config_params, make_params=make_params,
                         use_fakeroot=True, work_dir=ci_data.src_dir,
                         jobs=ci_data.config.get('jobs'))

        self.log_dbg("Initialization completed")

    def run(self):
        self.log_dbg("Run")

        try:
            super().run()
        except EndTest as e:
            self.log_err("Test ended with an error")
        finally:
            self.log_info(f"Test Verdict: {self.verdict.name}")

        # Report the result to Patchwork
        if self.verdict == Verdict.FAIL:
            submit_pw_check(self.ci_data.pw, self.ci_data.patch_1,
                            self.name, Verdict.FAIL,
                            "Make Distcheck FAIL: " + self.output,
                            None, self.ci_data.config['dry_run'])
            # Test verdict and output is already set by the super().run().
            # Just raise the EndTest enough
            raise EndTest

        # Build success
        submit_pw_check(self.ci_data.pw, self.ci_data.patch_1,
                        self.name, Verdict.PASS,
                        "Make Distcheck PASS",
                        None, self.ci_data.config['dry_run'])
        # Actually no need to call success() here. But add it here just for
        # reference
        self.success()

    def post_run(self):
        self.log_dbg("Post Run...")

        if self.verdict == Verdict.PENDING:
            self.log_info("No verdict. skip post-run")
            return

        # Clean the source
        cmd = ["make", "maintainer-clean"]
        (ret, stdout, stderr) = cmd_run(cmd, cwd=self.ci_data.src_dir)
        if ret:
            self.log_err("Fail to clean the source")

        # AR: hum... should it continue the test?
