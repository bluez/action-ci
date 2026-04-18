import os
import sys
import re
import shutil

from ci import Verdict, EndTest, submit_pw_check
from ci import CheckAllWarning

class CheckKernelLLVM(CheckAllWarning):
    """Build kernel with LLVM + context analysis
    """

    def __init__(self, ci_data, kernel_config=None, src_dir=None, dry_run=None):
        # Enable context analysis unconditionally
        kernel_config = self.make_kernel_config(kernel_config)

        super().__init__(ci_data, kernel_config=kernel_config, src_dir=src_dir,
                         dry_run=dry_run, make_params=["LLVM=1"])

        self.name = "CheckKernelLLVM"
        self.desc = "Build kernel with LLVM + context analysis"

    def run(self):
        if not shutil.which("clang"):
            self.skip("Clang not found")
        super().run()

    def make_kernel_config(self, old_kernel_config):
        kernel_config = "/build_kernel_llvm.config"
        if not old_kernel_config:
            old_kernel_config = '/bluetooth_build.config'

        with open(old_kernel_config, "r") as f:
            config_text = f.read()
        config_text += "\nCONFIG_WARN_CONTEXT_ANALYSIS=y"
        config_text += "\nCONFIG_WERROR=y"
        with open(kernel_config, "w") as f:
            f.write(config_text)

        return kernel_config
