#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import argparse

from libs import init_logger, log_debug, log_error, log_info, pr_get_sid
from libs import Context

import ci

def check_args(args):

    if not os.path.exists(os.path.abspath(args.config)):
        log_error(f"Invalid parameter(config) {args.config}")
        return False

    if not os.path.exists(os.path.abspath(args.bluez_dir)):
        log_error(f"Invalid parameter(src_dir) {args.bluez_dir}")
        return False

    if not os.path.exists(os.path.abspath(args.ell_dir)):
        log_error(f"Invalid parameter(ell_dir) {args.ell_dir}")
        return False

    if args.space == 'kernel':
        # requires kernel_dir
        if not args.kernel_dir:
            log_error("Missing required parameter: kernel_dir")
            return False

        if not os.path.exists(os.path.abspath(args.kernel_dir)):
            log_error(f"Invalid parameter(kernel_dir) {args.kernel_dir}")
            return False

    if not os.path.exists(os.path.abspath(args.patch_root)):
        log_error(f"Invalid parameter(patch_root) {args.patch_root}")
        return False

    return True

def parse_args():
    ap = argparse.ArgumentParser(description="Run CI tests")
    ap.add_argument('-c', '--config', default='./config.json',
                    help='Configuration file to use. default=./config.json')
    ap.add_argument('-b', '--branch', default='master',
                    help='Name of branch in base_repo where the PR is pushed. '
                         'Use <BRANCH> format. default: master')
    ap.add_argument('-z', '--bluez-dir', required=True,
                    help='BlueZ source directory.')
    ap.add_argument('-e', '--ell-dir', required=True,
                    help='ELL source directory.')
    ap.add_argument('-k', '--kernel-dir', default=None,
                    help='Kernel source directory')
    ap.add_argument('-p', '--patch-root', required=True,
                    help='Ratch root directory.')
    ap.add_argument('-d', '--dry-run', action='store_true', default=False,
                    help='Run it without uploading the result. default=False')

    # Positional parameter
    ap.add_argument('space', choices=['user', 'kernel'],
                    help="user or kernel space")
    ap.add_argument("repo",
                    help="Name of Github repository. i.e. bluez/bluez")
    ap.add_argument('pr_num', type=int,
                    help='Pull request number')
    return ap.parse_args()

# Email Message Templates

EMAIL_MESSAGE = '''This is automated email and please do not reply to this email!

Dear submitter,

Thank you for submitting the patches to the linux bluetooth mailing list.
This is a CI test results with your patch series:
PW Link:{pw_link}

---Test result---

{content}

---
Regards,
Linux Bluetooth

'''

def github_pr_post_result(ci_data, test):

    pr = ci_data.gh.get_pr(ci_data.config['pr_num'], force=True)

    comment = f"**{test.name}**\n"
    comment += f"Desc: {test.desc}\n"
    comment += f"Duration: {test.elapsed():.2f} seconds\n"
    comment += f"**Result: {test.verdict.name}**\n"

    if test.output:
        comment += f"Output:\n```\n{test.output}\n```"

    return ci_data.gh.pr_post_comment(pr, comment)

def is_maintainers_only(email_config):
    if 'only-maintainers' in email_config and email_config['only-maintainers']:
        return True
    return False

def get_receivers(email_config, submitter):
    log_debug("Get the list of email receivers")

    receivers = []
    if is_maintainers_only(email_config):
        # Send only to the maintainers
        receivers.extend(email_config['maintainers'])
    else:
        # Send to default-to and submitter
        receivers.append(email_config['default-to'])
        receivers.append(submitter)

    return receivers

def send_email(ci_data, content):
    headers = {}
    email_config = ci_data.config['email']

    body = EMAIL_MESSAGE.format(pw_link=ci_data.series['web_url'],
                                content=content)

    headers['In-Reply-To'] = ci_data.patch_1['msgid']
    headers['References'] = ci_data.patch_1['msgid']

    if not is_maintainers_only(email_config):
        headers['Reply-To'] = email_config['default-to']

    receivers = get_receivers(email_config, ci_data.series['submitter']['email'])
    ci_data.email.set_receivers(receivers)
    ci_data.email.compose("RE: " + ci_data.series['name'], body, headers)

    if ci_data.config['dry_run']:
        log_info("Dry-Run is set. Skip sending email")
        return

    log_info("Sending Email...")
    ci_data.email.send()

def report_ci(ci_data, test_list):
    """Generate the CI result and send email"""
    results = ""
    summary = "Test Summary:\n"

    line = "{name:<30}{result:<10}{elapsed:.2f} seconds\n"
    fail_msg = "Test: {name} - {result}\nDesc: {desc}\nOutput:\n{output}\n"

    for test in test_list:
        if test.verdict == ci.Verdict.PASS:
            # No need to add result of passed tests to simplify the email
            summary += line.format(name=test.name, result='PASS',
                                   elapsed=test.elapsed())
            continue

        # Rest of the verdicts use same output format
        results += "##############################\n"
        results += fail_msg.format(name=test.name, result=test.verdict.name,
                                   desc=test.desc, output=test.output)
        summary += line.format(name=test.name, result=test.verdict.name,
                               elapsed=test.elapsed())

    if results != "":
        results = "Details\n" + results

    # Sending email
    send_email(ci_data, summary + '\n' + results)

def create_test_list_user(ci_data):
    # Setup CI tests
    # AR: Maybe read the test from config?
    #
    # These are the list of tests:
    test_list = []

    ########################################
    # Test List
    ########################################

    # CheckPatch
    test_list.append(ci.CheckPatch(ci_data))

    # GitLint
    test_list.append(ci.GitLint(ci_data))

    # BuildELL
    test_list.append(ci.BuildEll(ci_data))

    # Build BlueZ
    test_list.append(ci.BuildBluez(ci_data))

    # Make Check
    test_list.append(ci.MakeCheck(ci_data))

    # Make distcheck
    test_list.append(ci.MakeDistcheck(ci_data))

    # Make check w/ Valgrind
    test_list.append(ci.CheckValgrind(ci_data))

    # Check Smatch
    test_list.append(ci.CheckSmatch(ci_data, "user", tool_dir="/smatch"))

    # Make with Exteranl ELL
    test_list.append(ci.MakeExtEll(ci_data))

    # Incremental Build
    test_list.append(ci.IncrementalBuild(ci_data, "user"))

    # Run ScanBuild
    test_list.append(ci.ScanBuild(ci_data))

    return test_list

def create_test_list_kernel(ci_data):
    # Setup CI tests for kernel test
    # AR: Maybe read the test from config?
    #
    # These are the list of tests:
    test_list = []
    ci_config = ci_data.config['space_details']['kernel']['ci']

    ########################################
    # Test List
    ########################################

    # CheckPatch
    # If available, need to apply "ignore" flag
    checkaptch_pl = os.path.join(ci_data.src_dir, 'scripts', 'checkpatch.pl')
    test_list.append(ci.CheckPatch(ci_data, checkpatch_pl=checkaptch_pl,
                     ignore=ci_config['CheckPatch']['ignore']))
    # GitLint
    test_list.append(ci.GitLint(ci_data))

    # SubjectPrefix
    test_list.append(ci.SubjectPrefix(ci_data))

    # BuildKernel
    # Get the config from the bluez source tree
    kernel_config = os.path.join(ci_data.config['bluez_dir'], "doc", "ci.config")
    test_list.append(ci.BuildKernel(ci_data, kernel_config=kernel_config))

    # Check All Warning
    test_list.append(ci.CheckAllWarning(ci_data, kernel_config=kernel_config))

    # CheckSparse
    test_list.append(ci.CheckSparse(ci_data, kernel_config=kernel_config))

    # CheckSmatch
    #test_list.append(ci.CheckSmatch(ci_data, "kernel", tool_dir="/smatch",
    #                                kernel_config=kernel_config))

    # BuildKernel32
    test_list.append(ci.BuildKernel32(ci_data, kernel_config=kernel_config))

    # TestRunnerSetup
    tester_config = os.path.join(ci_data.config['bluez_dir'],
                                 "doc", "tester.config")
    test_list.append(ci.TestRunnerSetup(ci_data, tester_config=tester_config,
                     bluez_src_dir=ci_data.config['bluez_dir']))

    # TestRunner-*
    testrunner_list = ci_config['TestRunner']['tester-list']
    for runner in testrunner_list:
        log_debug(f"Add {runner} instance to test_list")
        test_list.append(ci.TestRunner(ci_data, runner,
                         bluez_src_dir=ci_data.config['bluez_dir']))

    # # Incremental Build
    test_list.append(ci.IncrementalBuild(ci_data, "kernel",
                                         kernel_config=kernel_config))

    return test_list

def run_ci(ci_data):

    num_fails = 0

    test_list = []
    if ci_data.config['space'] == 'user':
        test_list = create_test_list_user(ci_data)
    else:
        test_list = create_test_list_kernel(ci_data)

    log_info(f"Test list is created: {len(test_list)}")
    log_debug("+--------------------------+")
    log_debug("|          Run CI          |")
    log_debug("+--------------------------+")
    for test in test_list:
        log_info("##############################")
        log_info(f"## CI: {test.name}")
        log_info("##############################")

        try:
            test.run()
        except ci.EndTest as e:
            log_error(f"Test Ended(Failure): {test.name}:{test.verdict.name}")
        except Exception as e:
            log_error(f"Test Ended(Exception): {test.name}: {e.__class__}")
        finally:
            test.post_run()

        if test.verdict != ci.Verdict.PASS:
            num_fails += 1

        if ci_data.config['dry_run']:
            log_info("Skip submitting result to Github: dry_run=True")
            continue

        log_debug("Submit the result to github")
        # AR: Submit the result to GH
        if not github_pr_post_result(ci_data, test):
            log_error("Failed to submit the result to Github")

    log_info(f"Total number of failed test: {num_fails}")
    log_debug("+--------------------------+")
    log_debug("|        ReportCI          |")
    log_debug("+--------------------------+")
    report_ci(ci_data, test_list)

    return num_fails

def main():
    global config, pw, gh, src_repo, email

    init_logger("Bluez_CI", verbose=True)

    args = parse_args()
    if not check_args(args):
        sys.exit(1)

    if args.space == "user":
        main_src = args.bluez_dir
    elif args.space == "kernel":
        main_src = args.kernel_dir
    else:
        log_error(f"Invalid parameter(space) {args.space}")
        sys.exit(1)

    ci_data = Context(config_file=os.path.abspath(args.config),
                      github_repo=args.repo,
                      src_dir=main_src,
                      patch_root=args.patch_root,
                      branch=args.branch, dry_run=args.dry_run,
                      bluez_dir=args.bluez_dir, ell_dir=args.ell_dir,
                      kernel_dir=args.kernel_dir, pr_num=args.pr_num,
                      space=args.space)

    # Setup Source for the test that needs to access the base like incremental
    # build.
    # It needs to fetch the extra patches: # of commit in PR + 1
    pr = ci_data.gh.get_pr(args.pr_num, force=True)
    cmd = ['fetch', f'--depth={pr.commits+1}']
    if ci_data.src_repo.git(cmd):
        log_error("Failed to fetch commits in the patches")
        sys.exit(1)

    # Get the patchwork series data and save in CI data
    sid = pr_get_sid(pr.title)

    # If PR is not created for Patchwork (no key string), ignore this PR and
    # stop running the CI
    if not sid:
        log_error("Not a valid PR. No need to run")
        sys.exit(1)

    ci_data.update_series(ci_data.pw.get_series(sid))

    num_fails = run_ci(ci_data)

    log_debug("----- DONE -----")

    sys.exit(num_fails)

if __name__ == "__main__":
    main()
