import os
import sys
import shutil

sys.path.insert(0, '../libs')
from libs import cmd_run

from ci import Verdict, EndTest, submit_pw_check
from ci import GenericBuild

class CheckValgrind(GenericBuild):
    """BlueZ Make Check with Valgrind
    This class runs 'make check' with Valgrind. Unlike MakeCheck, it needs to
    build the source, so it expects the source is clean.
    Optionally accepts a list of specific test binaries to run via TESTS=.
    """

    def __init__(self, ci_data, test_list=None):
        # For valgrind check, use the following config params to disable the
        # lsan and asan
        # config: --disable-lsan --disable-asan

        # Common
        self.name = "CheckValgrind"
        self.desc = "Run Bluez Make Check with Valgrind"
        self.ci_data = ci_data

        config_params = ["--disable-lsan", "--disable-asan"]
        make_params = ["check"]
        if test_list:
            tests_str = " ".join(test_list)
            make_params.append(f"TESTS={tests_str}")
        super().__init__(config_params=config_params, make_params=make_params,
                         work_dir=ci_data.src_dir,
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
                            "Check Valgrind FAIL: " + self.output,
                            None, self.ci_data.config["dry_run"])
            # Test verdict and output is already set by the super().run().
            # Just raise the EndTest enough
            raise EndTest

        # Build success
        submit_pw_check(self.ci_data.pw, self.ci_data.patch_1,
                        self.name, Verdict.PASS,
                        "Check Valgrind PASS",
                        None, self.ci_data.config["dry_run"])
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
