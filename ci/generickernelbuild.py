import os
import sys
import shutil

sys.path.insert(0, '../libs')
from libs import cmd_run

from ci import Base

class GenericKernelBuild(Base):
    """Generic Kernel Build class
    This class is used to build the kernel
    There are two different build type:
    Simple Build (simple_build=True) - Compile the bluetooth sources only in
    net/bluetooth and drivers/bluetooth.
    Full Build (simple_build=False) - Full build based on the config that
    enables all Bluetooth features.
    """

    def __init__(self, kernel_config=None, simple_build=True,
                 make_params=None, work_dir=None):

        super().__init__()

        self.work_dir = work_dir
        self.simple_build = simple_build

        # Set the default build config.
        if kernel_config:
            self.kernel_config = kernel_config
        else:
            self.kernel_config = '/bluetooth_build.config'

        # Extra build params
        self.make_params = make_params

        # Save the error output
        self.stderr = None

        self.log_dbg("Initialization completed")

    def run(self):
        self.log_dbg("GenericKernelBuild: Run")
        self.start_timer()

        # Copy the build config to source dir
        self.log_info(f"GenericKernelBuild: Copying {self.kernel_config}")
        shutil.copy(self.kernel_config, os.path.join(self.work_dir, ".config"))

        # Update .config
        self.log_info("GenericKernelBuild: Run make olddefconfig")
        cmd = ["make", "olddefconfig"]
        if self.make_params:
            cmd += self.make_params
        (ret, stdout, stderr) = cmd_run(cmd, cwd=self.work_dir)
        if ret:
            self.log_err("GenericKernelBuild: Failed to config the kernel")
            self.add_failure_end_test(stderr)

        # make
        self.log_info("Run make")

        base_cmd = ["make", "-j4"]
        if self.make_params:
            base_cmd += self.make_params
        self.log_dbg(f"GenericKernelBuild: Base Command: {base_cmd}")

        if self.simple_build:
            self.log_info("GenericKernelBuild: Simple build - Bluetooth only")
            cmd = base_cmd
            cmd.append('net/bluetooth/')
            cmd.append('drivers/bluetooth/')
            (ret, stdout, stderr) = cmd_run(cmd, cwd=self.work_dir)
            if ret:
                self.log_err("GenericKernelBuild: build fail")
                self.add_failure_end_test(stderr)
            self.stderr = stderr
        else:
            # full build
            self.log_info("Full build")
            cmd = base_cmd
            (ret, stdout, stderr) = cmd_run(cmd, cwd=self.work_dir)
            if ret:
                self.log_err("GenericKernelBuild: build fail")
                self.add_failure_end_test(stderr)
            self.stderr = stderr

        self.success()

    def post_run(self):
        self.log_dbg("GenericKernelBuild: Post Run...")

        # Clean
        cmd = ['make', 'clean']
        (ret, stdout, stderr) = cmd_run(cmd, cwd=self.work_dir)
        if ret:
            self.log_err("Fail to clean the source")

        # AR: should it continue the test?
