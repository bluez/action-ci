import sys

sys.path.insert(0, '../libs')
from libs import cmd_run

from ci import Base

class GenericBuild(Base):
    """Generic Build class
    This class is used to configure and make the application such as Bluez and
    ELL. It only executes and updates verdict without reporting the result to
    the Patchwork. The report to Patchwork should be done by the child class.
    """

    def __init__(self, config_cmd=None, config_params=None,
                 make_cmd=None, make_params=None,
                 use_fakeroot=False, install=False, install_params=None,
                 work_dir=None, jobs=None):

        super().__init__()

        # This class specific
        self.work_dir = work_dir
        self.use_fakeroot = use_fakeroot

        if config_cmd:
            self.config_cmd = config_cmd
        else:
            self.config_cmd = "./bootstrap-configure"
        self.config_params = config_params

        if make_cmd:
            self.make_cmd = make_cmd
        else:
            self.make_cmd = "make"
        self.make_params = make_params

        self.install = install
        self.install_params = install_params

        self.stderr = None

        self.jobs = jobs if jobs else "4"

        self.log_dbg("Initialization completed")

    def run(self):

        self.log_dbg("GenericBuild: Run")
        self.start_timer()

        # Configure
        cmd = [self.config_cmd]
        if self.config_params:
            cmd = cmd + self.config_params
        (ret, stdout, stderr) = cmd_run(cmd, cwd=self.work_dir)
        if ret:
            self.log_err(f"GenericBuild: Configure failed: {ret}")
            self.add_failure_end_test(stderr)

        # Make
        # AR: Maybe read from /proc for job count
        cmd = [self.make_cmd, "-j" + str(self.jobs)]
        if self.use_fakeroot:
            cmd = ["fakeroot"] + cmd
        if self.make_params:
            cmd = cmd + self.make_params
        (ret, stdout, stderr) = cmd_run(cmd, cwd=self.work_dir)
        if ret:
            self.log_err(f"GenericBuild: Make failed: {ret}")
            self.add_failure_end_test(stderr)
        # Save the stderr for future processing even if the cmd_run success
        self.stderr = stderr

        # Make Install
        if self.install:
            cmd = [self.make_cmd, "install"]
            if self.install_params:
                cmd = cmd + [self.install_params]
            (ret, stdout, stderr) = cmd_run(cmd, cwd=self.work_dir)
            if ret:
                self.log_err(f"GenericBuild: Install failed: {ret}")
                self.add_failure_end_test(stderr)
        # Save the stderr for future processing even if the cmd_run success
        self.stderr = stderr

        self.success()

    def post_run(self):
        self.log_dbg("GenericBuild: Post Run...")
