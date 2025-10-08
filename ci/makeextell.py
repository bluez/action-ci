import os
import sys
import shutil

sys.path.insert(0, '../libs')
from libs import cmd_run

from ci import Verdict, EndTest, submit_pw_check
from ci import GenericBuild

class MakeExtEll(GenericBuild):
    """BlueZ Make with External ELL class
    This class builds the BlueZ with external ell option. It assumes that the
    ELL is already installed on the system
    """

    def __init__(self, ci_data):
        # To use external ell, use the following config params
        # config: --enable-external-ell --disable-lsan --disable-asan --disable-ubsan

        # Common
        self.name = "bluezmakeextell"
        self.desc = "Build Bluez with External ELL"
        self.ci_data = ci_data

        config_params = ["--enable-external-ell", "--disable-lsan", "--disable-asan", "--disable-ubsan"]
        super().__init__(config_params=config_params, work_dir=ci_data.src_dir)

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
                            "Make External ELL FAIL: " + self.output,
                            None, self.ci_data.config['dry_run'])
            # Test verdict and output is already set by the super().run().
            # Just raise the EndTest enough
            raise EndTest

        # Build success
        submit_pw_check(self.ci_data.pw, self.ci_data.patch_1,
                        self.name, Verdict.PASS,
                        "Make External ELL PASS",
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
