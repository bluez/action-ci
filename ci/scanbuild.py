from gettext import install
import os
import sys

sys.path.insert(0, '../libs')
from libs import RepoTool, cmd_run

from ci import Base, Verdict, EndTest, submit_pw_check

class ScanBuild(Base):
    """Run scan-build class
    This class runs the scan-build and reports any issue found by the scan-build
    """

    def __init__(self, ci_data):

        # Common
        self.name = "ScanBuild"
        self.desc = "Run Scan Build"
        self.ci_data = ci_data

        super().__init__()

        self.log_dbg("Initialization completed")

    def scan_build(self, error_filename):
        # Build and save the error log
        # After saving the error log, it will cleans the build

        # Configure the build for base
        cmd = ["./bootstrap-configure", "--disable-asan", "--disable-lsan",
               "--disable-ubsan", "--disable-android"]
        (ret, stdout, stderr) = cmd_run(cmd, cwd=self.ci_data.src_dir)
        if ret:
            self.log_err("Build config failed")
            submit_pw_check(self.ci_data.pw, self.ci_data.patch_1,
                            self.name, Verdict.FAIL,
                            "Build Config FAIL",
                            None, self.ci_data.config['dry_run'])
            self.add_failure_end_test(stderr)

        # Scan Build Make
        cmd = ["scan-build", "make", "-j4"]
        (ret, stdout, stderr) = cmd_run(cmd, cwd=self.ci_data.src_dir)
        if ret:
            self.log_err("Scan Build failed")
            submit_pw_check(self.ci_data.pw, self.ci_data.patch_1,
                            self.name, Verdict.FAIL,
                            "Scan Build FAIL",
                            None, self.ci_data.config['dry_run'])
            self.add_failure_end_test(stderr)

        # Save the stderr for later use
        err_file = os.path.join(self.ci_data.src_dir, error_filename)
        with open(err_file, 'w+') as f:
            f.write(stderr)
        self.log_dbg(f"Saved output for base build: {err_file}")

        # Clean the source
        cmd = ["make", "maintainer-clean"]
        (ret, stdout, stderr) = cmd_run(cmd, cwd=self.ci_data.src_dir)
        if ret:
            self.log_err("Build clean failed")
            submit_pw_check(self.ci_data.pw, self.ci_data.patch_1,
                            self.name, Verdict.FAIL,
                            "Scan Build FAIL",
                            None, self.ci_data.config['dry_run'])
            self.add_failure_end_test(stderr)

        return err_file

    def run(self):

        self.log_dbg("Run")
        self.start_timer()

        # Create the temp branch (HEAD) to come back later
        if self.ci_data.src_repo.git_checkout("patched", create_branch=True):
            self.log_err("Failed to create branch")
            submit_pw_check(self.ci_data.pw, self.ci_data.patch_1,
                            self.name, Verdict.FAIL,
                            "Setup failed",
                            None, self.ci_data.config['dry_run'])
            self.add_failure_end_test("Setup failed")

        # Run scan build with base, and save the error log
        base_err_file = self.scan_build("scan_build_base.err")

        # Now checked out the patched branch
        if self.ci_data.src_repo.git_checkout("patched"):
            self.log_err(f"Failed to checkout to patched branch")
            submit_pw_check(self.ci_data.pw, self.ci_data.patch_1,
                            self.name, Verdict.FAIL,
                            "Setup failed",
                            None, self.ci_data.config['dry_run'])
            self.add_failure_end_test("Setup failed")

        # Run scan build with patched, and save the error log
        patched_err_file = self.scan_build("scan_build_patched.err")

        # Compare two error files
        results = self.compare_outputs(base_err_file, patched_err_file)
        if results:
            # Add warning...
            self.log_dbg("Found differnece in two build scans: " + results)
            submit_pw_check(self.ci_data.pw, self.ci_data.patch_1,
                            self.name, Verdict.WARNING,
                            "ScanBuild: " + results,
                            None, self.ci_data.config['dry_run'])
            self.warning(results)
            # warning() doens't raise the exception.
            raise EndTest

        submit_pw_check(self.ci_data.pw, self.ci_data.patch_1,
                        self.name, Verdict.PASS,
                        "Scan Build PASS",
                        None, self.ci_data.config['dry_run'])
        self.success()

    def post_run(self):
        self.log_dbg("Post Run...")

    def compare_outputs(self, base_err_file, patched_err_file):
        base_dir = os.path.join(self.ci_data.src_dir, "scan_build_base")
        self.parse_err_file(base_err_file, base_dir)
        patched_dir = os.path.join(self.ci_data.src_dir, "scan_build_patched")
        self.parse_err_file(patched_err_file, patched_dir)

        return self.diff_dirs(base_dir, patched_dir)

    def read_err_lines(self, err_file):
        err_lines = ""

        self.log_dbg(f"Read err_file: {err_file}")

        if os.path.isfile(err_file):
            with open(err_file) as f:
                err_lines = f.read()
            return err_lines

        if os.path.isdir(err_file):
            for f in os.listdir(err_file):
                err_lines += self.read_err_lines(os.path.join(err_file, f))

        return err_lines

    def diff_dirs(self, base_dir, patched_dir):
        """
        Diff two folders and find the new error in the patched dir
        """

        err_lines = ""
        err_file = ""

        cmd = ["diff", "-qr", base_dir, patched_dir]
        (ret, stdout, stderr) = cmd_run(cmd, cwd=self.ci_data.src_dir)
        if ret == 0:
            self.log_dbg("No changes found - base and patched")
            return None

        for line in stdout.splitlines():
            if line.startswith("Only in"):
                if line.find(patched_dir) != -1:
                    self.log_dbg("Found new issue in patched dir")
                    # line looks like this:
                    # "Only in /home/han1/work/dev/scratch/prs/1591/patched: lib"
                    # "Only in /home/han1/work/dev/scratch/prs/1591/patched/monitor: hwdb.c.err"
                    temp = line.replace("Only in ", '').split(": ")
                    err_file = os.path.join(temp[0], temp[1])
                    err_lines += self.read_err_lines(err_file)
                continue

            if line.startswith("Files "):
                # line looks like this:
                # Files /home/han1/work/dev/scratch/prs/1591/base/tools/test-runner.c.err and /home/han1/work/dev/scratch/prs/1591/patched/tools/test-runner.c.err differ
                err_file = line.split(" and ")[1].split(" ")[0]
                err_lines += self.read_err_lines(err_file)

        return err_lines

    def parse_err_file(self, err_file, out_dir):
        """
        Read scan-build error output file and create the file with error
        output
        """
        self.log_dbg(f"Parse error file({err_file}) to {out_dir}")

        file1 = open(err_file, 'r')
        lines = file1.readlines()
        file1.close()

        err_lines = ""

        for line in lines:

            # ignore if the line is empty line
            if line.strip() == "":
                continue

            # Found key string
            if line.find(' generated.') >= 0:
                err_lines += line

                line1 = err_lines.splitlines()[0]

                # Some output starts with "In file included from "
                if line1.find("In file included", 0, 20) >= 0:
                    line1 = line1.replace("In file included from ", '')

                file_path = line1.split(':')[0]

                target_path = os.path.join(out_dir,
                                           os.path.dirname(file_path))
                target_file = os.path.join(target_path,
                                           os.path.basename(file_path) + ".err")

                if not os.path.exists(target_path):
                    os.makedirs(target_path, exist_ok=True)

                # Save to local file
                with open(target_file, 'w+') as f:
                    f.write(err_lines)

                self.log_dbg(f"err file is created: {target_file}")

                # reset and continue
                err_lines = ""
                continue

            err_lines += line
