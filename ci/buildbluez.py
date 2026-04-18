from ci import Verdict, EndTest, submit_pw_check
from ci import GenericBuild

class BuildBluez(GenericBuild):
    """Class for building the BlueZ
    This class is to configure and make the bluez. Actual work is done by the
    GenericBuild class. After finishing the actual run() from the GenericBuiuld
    class, it checks the verdict and reports the result.
    """

    def __init__(self, ci_data, src_dir=None, config_params=None,
                 make_params=None, dry_run=None):

        self.name = "BluezMake"
        self.desc = "Build BlueZ"
        self.ci_data = ci_data

        # Override the src_dir
        self.src_dir = ci_data.src_dir
        if src_dir:
            self.log_dbg(f"Override src_dir {src_dir}")
            self.src_dir = src_dir

        self.make_params = make_params

        self.dry_run = self.ci_data.config['dry_run']
        if dry_run:
            self.log_dbg(f"Override the dry_run flag: {dry_run}")
            self.dry_run = dry_run

        super().__init__(config_params=config_params, work_dir=self.src_dir,
                         make_params=self.make_params,
                         jobs=ci_data.config.get('jobs'))

        self.log_dbg("Initialization completed")

    def run(self):

        self.log_dbg("Run")

        try:
            super().run()
        except EndTest as e:
            self.log_err("Test ended with an error")
        finally:
            self.log_info(f"Test Verdict: {self.verdict}")

        self.log_info(f"Test Verdict: {self.verdict.name}")

        # Report the result to Patchwork
        if self.verdict == Verdict.FAIL:
            submit_pw_check(self.ci_data.pw, self.ci_data.patch_1,
                            self.name, Verdict.FAIL,
                            "BluezMake FAIL: " + self.output,
                            None, self.dry_run)
            # Test verdict and output is already set by the super().run().
            # Just raise the EndTest enough
            raise EndTest

        # Build success
        submit_pw_check(self.ci_data.pw, self.ci_data.patch_1,
                        self.name, Verdict.PASS,
                        "Bluez Make PASS",
                        None, self.dry_run)
        # Actually no need to call success() here. But add it here just for
        # reference
        self.success()

    def post_run(self):
        self.log_dbg("Post Run...")
