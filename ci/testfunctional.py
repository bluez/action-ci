import os
import sys
import re
import textwrap
from xml.etree import ElementTree

sys.path.insert(0, "../libs")
from libs import cmd_run

from ci import Base, Verdict, EndTest, submit_pw_check, BuildBluez


class TestFunctional(Base):
    """Functional test runner class
    This class runs test/test-functional
    """

    def __init__(self, ci_data, bluez_src_dir=None):
        if not bluez_src_dir:
            bluez_src_dir = ci_data.src_dir

        jobs = ci_data.config.get("jobs")
        if not jobs:
            jobs = "auto"
        else:
            jobs = max(1, jobs // 3)

        self.name = f"TestFunctional"
        self.desc = f"Run test-functional"
        self.ci_data = ci_data
        self.bluez_src_dir = bluez_src_dir

        self.result_xml = os.path.abspath(
            os.path.join(bluez_src_dir, "test-functional.xml")
        )
        self.cmd = [
            os.path.join(bluez_src_dir, "test/test-functional"),
            "-vv",
            "--junit-xml",
            self.result_xml,
            "-m",
            "not tester",
            "-ra",
            "--vm-timeout",
            "60",
        ]

        _params = ["--disable-lsan", "--enable-asan", "--enable-ubsan"]
        self.bluez_build = BuildBluez(
            ci_data, config_params=_params, src_dir=self.bluez_src_dir, dry_run=True
        )

        super().__init__()

        self.log_dbg("Initialization completed")

    def run(self):
        kernel_img = os.path.join(self.ci_data.src_dir, "arch/x86/boot/bzImage")
        if os.path.isfile(kernel_img):
            self.cmd += ["--kernel", kernel_img]
        else:
            self.cmd += [
                "--kernel-build",
                "-o",
                "kernel_upstream=https://github.com/bluez/bluetooth-next",
            ]

        verdict, desc, msg = self.__do_run()

        submit_pw_check(
            self.ci_data.pw,
            self.ci_data.patch_1,
            self.name,
            verdict,
            desc,
            None,
            self.ci_data.config["dry_run"],
        )

        if verdict == Verdict.PASS:
            self.success()
        elif verdict == Verdict.ERROR:
            self.error(f"{desc}:\n{msg}")
        else:
            self.end_timer()
            raise EndTest

    def __do_run(self):
        self.log_dbg("Run")

        self.start_timer()

        # Check requirements
        ret, stdout, stderr = cmd_run(
            [
                "python3",
                "-mpip",
                "install",
                "--break-system-packages",
                "--no-index",
                "--dry-run",
                "-r",
                "test/functional/requirements.txt",
            ],
            cwd=self.bluez_src_dir,
        )
        if ret:
            return Verdict.SKIP, "Requirements missing", "Requirements missing"

        # Build BlueZ if needed
        if not os.path.isfile(os.path.join(self.bluez_src_dir, "src", "bluetoothd")):
            self.log_info("Building BlueZ")
            try:
                self.bluez_build.run()
            except EndTest as e:
                return Verdict.ERROR, "Failed to build BlueZ", "Failed to build BlueZ"

        # Run tests
        ret, stdout, stderr = cmd_run(self.cmd, cwd=self.bluez_src_dir)
        if ret != 0 and ret != 1:
            self.log_err("Test failed to run")
            return Verdict.ERROR, "Test failed to run", stderr

        # Process the result
        try:
            tree = ElementTree.parse(self.result_xml)
            testcases = tree.findall(".//testcase")
        except:
            return (
                Verdict.ERROR,
                "Test produced no result",
                "Test produced no result\n{stderr}",
            )

        desc = None
        for testcase in tree.findall(".//testcase"):
            name = testcase.attrib.get("classname", "") + "::" + testcase.attrib["name"]

            fail = []
            for error in testcase.findall(".//error") + testcase.findall(".//failure"):
                msg = textwrap.dedent(error.attrib["message"])
                msg = textwrap.indent(msg, "    ").strip()
                fail.append(f"FAIL {name}: {msg}")

            if fail:
                desc = desc or fail[0].splitlines()[0]
                self.add_failure("\n".join(fail))

        if desc:
            return Verdict.FAIL, desc, None
        else:
            return Verdict.PASS, "TestFunctional PASS", None

    def post_run(self):
        self.log_dbg("Post Run...")
