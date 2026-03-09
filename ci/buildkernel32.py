import os
import sys

sys.path.insert(0, '../libs')
from libs import cmd_run

from ci import Verdict, EndTest, submit_pw_check
from ci import GenericKernelBuild

class BuildKernel32(GenericKernelBuild):
    """Build 32bit Kernel class
    This class is used to build the 32bit kernel for Bluetooth
    There are two different build type:
    Simple Build (simple_build=True) - Compile the bluetooth sources only in
    net/bluetooth and drivers/bluetooth.
    Full Build (simple_build=False) - Full build based on the config that
    enables all Bluetooth features.
    """

    def __init__(self, ci_data, kernel_config=None, simple_build=True,
                 make_params=None, src_dir=None, dry_run=None):

        # Common
        self.name = "BuildKernel32"
        self.desc = "Build 32bit Kernel for Bluetooth"
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

        # Check kernel config option
        new_config = self.create_config32(kernel_config)
        self.log_dbg(f"New config for 32bit is created: {new_config}")

        super().__init__(kernel_config=new_config, simple_build=simple_build,
                         make_params=make_params, work_dir=self.src_dir)

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
                            "BuildKernel32: FAIL: " + self.output,
                            None, self.dry_run)
            # Test verdict and output is already set by the super().run().
            # Just raising EndTest exception is enough here
            raise EndTest

        # Build success
        submit_pw_check(self.ci_data.pw, self.ci_data.patch_1,
                        self.name, Verdict.PASS,
                        "BuildKernel32 PASS",
                        None, self.dry_run)
        # Actually no need to call success() here. But add it here just for
        # reference
        self.success()

    def post_run(self):
        self.log_dbg("Post Run...")

        self.log_dbg("Clean the source")
        super().post_run()


    def create_config32(self, orig_config):
        """Create config file for 32bit build
        This is a custom step and assume that the orig config file is used
        for 64bit. This function createst new config file with CONFIG_64BIT=n
        flag and return it.
        """

        with open(orig_config, "r") as f:
            contents = f.readlines()

        # TODO: Maybe check contents if CONFIG_64BIT flag is already exists and
        # delete it before updating it.

        # Add config at the end of the line
        contents.insert(len(contents), "CONFIG_64BIT=n")

        # Save to new file: orig_config name + '.32'
        basedir = os.path.dirname(os.path.abspath(orig_config))
        new_config = os.path.join(basedir,
                        os.path.basename(os.path.abspath(orig_config)) + ".32")
        with open(new_config, "w+") as f:
            contents = "".join(contents)
            f.write(contents)

        return new_config
