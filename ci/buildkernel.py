import os
import sys
import shutil

sys.path.insert(0, '../libs')
from libs import cmd_run

from ci import Verdict, EndTest, submit_pw_check
from ci import GenericKernelBuild

class BuildKernel(GenericKernelBuild):
    """Build Kernel class
    This class is used to build the kernel for Bluetooth
    There are two different build type:
    Simple Build (simple_build=True) - Compile the bluetooth sources only in
    net/bluetooth and drivers/bluetooth.
    Full Build (simple_build=False) - Full build based on the config that
    enables all Bluetooth features.
    """

    def __init__(self, ci_data, kernel_config=None, simple_build=True,
                 make_params=None, src_dir=None, dry_run=None):

        # Common
        self.name = "BuildKernel"
        self.desc = "Build Kernel for Bluetooth"
        self.ci_data = ci_data
        self.simple_build = simple_build

        # Override the src dir
        self.src_dir = ci_data.src_dir
        if src_dir:
            self.log_dbg(f"Override src_dir {src_dir}")
            self.src_dir = src_dir

        # Extra build params
        self.make_params = make_params

        # Override the dry_run flag.
        self.dry_run = self.ci_data.config['dry_run']
        if dry_run:
            self.log_dbg(f"Override the dry_run flag: {dry_run}")
            self.dry_run = dry_run

        # Save the error output
        self.stderr = None

        super().__init__(kernel_config=kernel_config, simple_build=simple_build,
                         make_params=make_params, work_dir=self.src_dir,
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

        # Reposrt the result to Patchwork
        if self.verdict == Verdict.FAIL:
            submit_pw_check(self.ci_data.pw, self.ci_data.patch_1,
                            self.name, Verdict.FAIL,
                            "BuildKernel: FAIL: " + self.output,
                            None, self.dry_run)
            # Test verdict and output is already set by the super().run().
            # Just raising EndTest exception is enough here
            raise EndTest

        # Build success
        submit_pw_check(self.ci_data.pw, self.ci_data.patch_1,
                        self.name, Verdict.PASS,
                        "BuildKernel PASS",
                        None, self.dry_run)
        # Actually no need to call success() here. But add it here just for
        # reference
        self.success()

    def post_run(self):
        self.log_dbg("Post Run...")

        self.log_dbg("Clean the source")
        super().post_run()
