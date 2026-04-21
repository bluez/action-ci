import sys

sys.path.insert(0, '../libs')
from libs import cmd_run

from ci import Base, Verdict, submit_pw_check

class MakeCheck(Base):
    """BlueZ Make Check class
    This class runs 'make check' with Bluez, and it assumes that the source
    is already compiled. Optionally accepts a list of specific test binaries
    to run via TESTS= override.
    """

    def __init__(self, ci_data, test_list=None):

        # Common
        self.name = "MakeCheck"
        self.desc = "Run Bluez Make Check"
        self.ci_data = ci_data
        self.test_list = test_list

        super().__init__()

        self.log_dbg("Initialization completed")

    def run(self):

        self.log_dbg("Run")
        self.start_timer()

        cmd = ["make", "check"]
        if self.test_list:
            tests_str = " ".join(self.test_list)
            cmd.append(f"TESTS={tests_str}")
            self.log_info(f"Running subset of tests: {tests_str}")

        (ret, stdout, stderr) = cmd_run(cmd, cwd=self.ci_data.src_dir)
        if ret:
            submit_pw_check(self.ci_data.pw, self.ci_data.patch_1,
                            self.name, Verdict.FAIL,
                            "BlueZ Make Check FAIL: " + self.output,
                            None, self.ci_data.config['dry_run'])
            self.log_dbg("Test result FAIL")
            self.add_failure_end_test(stderr)

        # Build success
        submit_pw_check(self.ci_data.pw, self.ci_data.patch_1,
                        self.name, Verdict.PASS,
                        "Bluez Make Check PASS",
                        None, self.ci_data.config['dry_run'])
        self.success()
        self.log_dbg("Test result PASS")

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
