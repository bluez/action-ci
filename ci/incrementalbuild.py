import os
import shutil
import sys

sys.path.insert(0, '../libs')
from libs import cmd_run

from ci import Base, Verdict, EndTest, submit_pw_check

class IncrementalBuild(Base):
    """Incremental Build class
    This class builds the target after applying each patch in the series
    one-by-one, running an incremental make after each patch.
    """

    def __init__(self, ci_data, space, kernel_config=None):

        self.name = "IncrementalBuild"
        self.desc = "Incremental build with the patches in the series"

        self.kernel_config = kernel_config
        self.space = space
        self.ci_data = ci_data

        if self.space not in ("kernel", "user"):
            raise ValueError(f"Invalid space: {self.space}")

        # For kernel builds, default to the standard config if not provided
        if self.space == "kernel" and not self.kernel_config:
            self.kernel_config = '/bluetooth_build.config'

        super().__init__()

        self.log_dbg("Initialization completed")

    def _initial_setup(self):
        """Run the initial build configuration once before the patch loop."""

        if self.space == "user":
            # Run bootstrap-configure once
            cmd = ["./bootstrap-configure"]
            (ret, stdout, stderr) = cmd_run(cmd, cwd=self.ci_data.src_dir)
            if ret:
                self.log_err("Failed to run bootstrap-configure")
                self.add_failure_end_test(stderr)
        elif self.space == "kernel":
            # Copy kernel config and run olddefconfig once
            self.log_info(f"Copying kernel config: {self.kernel_config}")
            shutil.copy(self.kernel_config,
                        os.path.join(self.ci_data.src_dir, ".config"))
            cmd = ["make", "olddefconfig"]
            (ret, stdout, stderr) = cmd_run(cmd, cwd=self.ci_data.src_dir)
            if ret:
                self.log_err("Failed to run make olddefconfig")
                self.add_failure_end_test(stderr)

    def _incremental_make(self):
        """Run make without reconfiguring - truly incremental."""

        cmd = ["make", "-j4"]
        if self.space == "kernel":
            # Kernel simple build: only Bluetooth sources
            cmd.append('net/bluetooth/')
            cmd.append('drivers/bluetooth/')

        (ret, stdout, stderr) = cmd_run(cmd, cwd=self.ci_data.src_dir)
        if ret:
            self.log_err("Incremental make failed")
            self.add_failure(stderr)
            return False
        return True

    def run(self):
        self.log_dbg("Run")

        self.start_timer()

        # Reset source tree to origin/master so patches can be applied
        # one-by-one for incremental building. Using origin/master directly
        # avoids issues with merge commits (refs/pull/N/merge) where HEAD~N
        # walks back through master history instead of the PR commits.
        self.log_info("Resetting source to origin/master (base commit)")
        if self.ci_data.src_repo.git_reset('origin/master', hard=True):
            self.log_err("Failed to reset to base commit")
            self.add_failure_end_test("Failed to reset to base commit")

        # Run initial configure/config setup once before the patch loop
        self._initial_setup()

        # Get patches from patchwork series
        for patch in self.ci_data.series['patches']:
            self.log_dbg(f"Patch ID: {patch['id']}")

            # Save patch mbox to file
            patch_file = self.ci_data.pw.save_patch_mbox(patch['id'],
                            os.path.join(self.ci_data.patch_root,
                                         f"{patch['id']}.patch"))
            self.log_dbg(f"Save patch: {patch_file}")

            # Apply patch
            if self.ci_data.src_repo.git_am(patch_file):
                self.log_err("Failed to apply patch")
                self.log_info("Aborting failed git-am and retrying")
                self.ci_data.src_repo.git_am(abort=True)
                self.ci_data.src_repo.git_clean()
                if self.ci_data.src_repo.git_am(patch_file):
                    self.log_err("Failed to apply patch. Giving up")
                    msg = self.ci_data.src_repo.stderr
                    self.ci_data.src_repo.git_am(abort=True)
                    self.add_failure_end_test(msg)

            # Incremental build - just run make, no reconfigure/clean
            if not self._incremental_make():
                msg = f"{patch['name']}\n{self.output}"
                submit_pw_check(self.ci_data.pw, patch,
                                self.name, Verdict.FAIL,
                                msg,
                                None, self.ci_data.config['dry_run'])
                self.add_failure_end_test(msg)

            # Build Passed
            submit_pw_check(self.ci_data.pw, patch,
                            self.name, Verdict.PASS,
                            "Incremental Build PASS",
                            None, self.ci_data.config['dry_run'])
            self.success()

    def post_run(self):
        self.log_dbg("Post Run...")

        if self.verdict == Verdict.PENDING:
            self.log_info("No verdict. skip post-run")
            return

        if self.space == 'user':
            cmd = ["make", "maintainer-clean"]
        else: # kernel
            cmd = ['make', 'clean']

        (ret, stdout, stderr) = cmd_run(cmd, cwd=self.ci_data.src_dir)
        if ret:
            self.log_err("Fail to clean the source")

        # AR: hum... should it continue the test?
