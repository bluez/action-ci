#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import argparse

from libs import init_logger, log_debug, log_error, log_info, pr_get_sid
from libs import Context

import ci

# Map CI Verdict to GitHub Check Run conclusion
VERDICT_TO_CONCLUSION = {
    ci.Verdict.PASS: 'success',
    ci.Verdict.FAIL: 'failure',
    ci.Verdict.ERROR: 'failure',
    ci.Verdict.SKIP: 'skipped',
    ci.Verdict.WARNING: 'neutral',
    ci.Verdict.PENDING: 'neutral',
}

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
    ap.add_argument('-j', '--jobs', action='store', type=str, default="4",
                    help='Number of make jobs (number or "auto"). default=4')

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

{test_log_link}

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

def github_update_check_run(ci_data, check_run, test):
    """Update a GitHub Check Run with the test result."""

    if not check_run:
        return False

    conclusion = VERDICT_TO_CONCLUSION.get(test.verdict, 'neutral')
    title = f"{test.name} - {test.verdict.name}"
    summary = f"**{test.desc}**\n\nDuration: {test.elapsed():.2f} seconds"

    text = None
    if test.output:
        text = f"```\n{test.output}\n```"

    return ci_data.gh.update_check_run(check_run, conclusion, title, summary,
                                       text)

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
    pr = ci_data.gh.get_pr(ci_data.config['pr_num'], force=True)

    body = EMAIL_MESSAGE.format(pw_link=ci_data.series['web_url'],
                                content=content,
                                test_log_link=f"{pr.html_url}")

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

    # Detect which unit tests to run based on changed files
    unit_test_list = detect_user_checks(ci_data)

    # Make Check - only if there are unit tests to run
    # unit_test_list: None = run all, [] = skip, [...] = run subset
    if unit_test_list is None:
        # Run all tests
        test_list.append(ci.MakeCheck(ci_data))
        test_list.append(ci.MakeDistcheck(ci_data))
        test_list.append(ci.CheckValgrind(ci_data))
    elif unit_test_list:
        # Run specific tests
        test_list.append(ci.MakeCheck(ci_data, test_list=unit_test_list))
        test_list.append(ci.MakeDistcheck(ci_data))
        test_list.append(ci.CheckValgrind(ci_data,
                                          test_list=unit_test_list))
    else:
        log_info("Skipping MakeCheck/MakeDistcheck/CheckValgrind "
                 "(no unit-tested code changed)")

    # Check Smatch
    test_list.append(ci.CheckSmatch(ci_data, "user", tool_dir="/smatch"))

    # Make with External ELL
    test_list.append(ci.MakeExtEll(ci_data))

    # Incremental Build
    test_list.append(ci.IncrementalBuild(ci_data, "user"))

    # Run ScanBuild
    test_list.append(ci.ScanBuild(ci_data))

    return test_list

def _get_changed_files(ci_data):
    """Get the list of changed files from the patchwork series.

    Returns:
        List of file paths, or None on error
    """
    from sync_patchwork import series_get_file_list
    try:
        changed_files = series_get_file_list(ci_data, ci_data.series)
    except Exception as e:
        log_error(f"Failed to get file list from series: {e}")
        return None

    if not changed_files:
        log_info("No changed files detected")
        return None

    log_info(f"Changed files ({len(changed_files)}): {changed_files}")
    return changed_files


def _match_files_to_areas(changed_files, file_mapping):
    """Match changed files against a file-mapping config.

    Returns:
        (matched_areas, unmatched_files) tuple where matched_areas is a dict
        of {area_name: area_config} for areas that had at least one file match,
        and unmatched_files is a list of files that matched no pattern.
    """
    matched_areas = {}
    unmatched_files = []

    for changed_file in changed_files:
        found = False
        for area_name, area_config in file_mapping.items():
            if area_name.startswith('_'):
                continue
            for pattern in area_config['files']:
                if pattern.endswith('/'):
                    match = changed_file.startswith(pattern)
                else:
                    match = (changed_file == pattern)
                if match:
                    matched_areas[area_name] = area_config
                    found = True
                    break
            if found:
                break
        if not found:
            unmatched_files.append(changed_file)

    return matched_areas, unmatched_files


def _apply_area_labels(ci_data, matched_areas):
    """Apply area:* labels to the PR for visibility."""
    if matched_areas and not ci_data.config['dry_run']:
        labels = [f"area:{area}" for area in sorted(matched_areas)]
        pr = ci_data.gh.get_pr(ci_data.config['pr_num'])
        ci_data.gh.pr_add_labels(pr, labels)
        log_info(f"Applied PR labels: {labels}")


def detect_testers(ci_data, ci_config):
    """Detect which testers to run based on changed files in the PR.

    Uses the file-mapping from config.json to determine which testers are
    relevant for the files changed by this patch series. Also applies
    'area:*' labels to the PR for visibility.

    Args:
        ci_data: The CI context object
        ci_config: The kernel CI config dict from config.json

    Returns:
        Set of tester names to run, or None if all testers should run
    """
    all_testers = set(ci_config['TestRunner']['tester-list'])
    file_mapping = ci_config['TestRunner'].get('file-mapping')

    if not file_mapping:
        log_info("No file-mapping configured, running all testers")
        return None

    changed_files = _get_changed_files(ci_data)
    if not changed_files:
        return None

    matched_areas, unmatched_files = _match_files_to_areas(
        changed_files, file_mapping)

    # If any changed file didn't match any pattern, run all testers (safe
    # fallback)
    if unmatched_files:
        for f in unmatched_files:
            log_info(f"File '{f}' not in any mapping, running all testers")
        _apply_area_labels(ci_data, matched_areas)
        return None

    # Resolve testers from matched areas
    matched_testers = set()
    all_matched = False
    for area_name, area_config in matched_areas.items():
        area_testers = area_config['testers']
        if area_testers == '__all__':
            all_matched = True
            matched_testers = all_testers.copy()
        elif area_testers == '__none__':
            pass
        else:
            matched_testers.update(area_testers)

    _apply_area_labels(ci_data, matched_areas)

    if all_matched:
        log_info("Running ALL testers")
        return None
    else:
        log_info(f"Running testers: {sorted(matched_testers)}")
        skipped = all_testers - matched_testers
        if skipped:
            log_info(f"Skipping testers: {sorted(skipped)}")
        return matched_testers


def detect_user_checks(ci_data):
    """Detect which unit tests to run for userspace patches.

    Examines the changed files against the user space file-mapping to
    build a list of unit test binaries that should run. If only
    daemon/plugin/client code changed, no tests need to run.

    Args:
        ci_data: The CI context object

    Returns:
        List of test binary paths to run (e.g. ["unit/test-bap"]),
        None to run all tests (fallback), or empty list to skip tests.
    """
    ci_config = ci_data.config['space_details']['user'].get('ci')
    if not ci_config:
        log_info("No user CI config, running all checks")
        return None

    file_mapping = ci_config.get('file-mapping')
    if not file_mapping:
        log_info("No user file-mapping configured, running all checks")
        return None

    changed_files = _get_changed_files(ci_data)
    if not changed_files:
        return None

    matched_areas, unmatched_files = _match_files_to_areas(
        changed_files, file_mapping)

    # Unmatched files -> safe fallback, run everything
    if unmatched_files:
        for f in unmatched_files:
            log_info(f"File '{f}' not in any user mapping, "
                     "running all checks")
        _apply_area_labels(ci_data, matched_areas)
        return None

    _apply_area_labels(ci_data, matched_areas)

    # Collect unit tests from matched areas
    run_all = False
    test_set = set()
    for area_name, area_config in matched_areas.items():
        unit_tests = area_config.get('unit_tests', [])
        if unit_tests == '__all__':
            run_all = True
            log_info(f"Area '{area_name}' requires all unit tests")
            break
        elif unit_tests:
            test_set.update(unit_tests)
            log_info(f"Area '{area_name}' -> {unit_tests}")

    if run_all:
        log_info("Running ALL unit tests")
        return None

    if test_set:
        test_list = sorted(test_set)
        log_info(f"Running unit tests: {test_list}")
        return test_list
    else:
        areas = sorted(matched_areas.keys())
        log_info(f"Only daemon/non-tested code changed ({areas}), "
                 "skipping MakeCheck/Valgrind/Distcheck")
        return []


def create_test_list_kernel(ci_data):
    # Setup CI tests for kernel test
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

    # CheckKernelLLVM
    test_list.append(ci.CheckKernelLLVM(ci_data, kernel_config=kernel_config))

    # TestRunnerSetup
    tester_config = os.path.join(ci_data.config['bluez_dir'],
                                 "doc", "tester.config")
    test_list.append(ci.TestRunnerSetup(ci_data, tester_config=tester_config,
                     bluez_src_dir=ci_data.config['bluez_dir']))

    # TestRunner-*
    # Detect which testers to run based on changed files
    active_testers = detect_testers(ci_data, ci_config)
    testrunner_list = ci_config['TestRunner']['tester-list']
    for runner in testrunner_list:
        if active_testers is not None and runner not in active_testers:
            log_debug(f"Skip {runner} (not relevant to changed files)")
            continue
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

    # Get the PR head SHA for creating check runs
    pr = ci_data.gh.get_pr(ci_data.config['pr_num'], force=True)
    head_sha = pr.head.sha

    log_info(f"Test list is created: {len(test_list)}")
    log_info(f"PR head SHA for check runs: {head_sha}")
    log_debug("+--------------------------+")
    log_debug("|          Run CI          |")
    log_debug("+--------------------------+")
    for test in test_list:
        log_info("##############################")
        log_info(f"## CI: {test.name}")
        log_info("##############################")

        # Create a GitHub Check Run in 'in_progress' state
        check_run = None
        if not ci_data.config['dry_run']:
            check_run = ci_data.gh.create_check_run(
                test.name, head_sha, status='in_progress')

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

        # Update the GitHub Check Run with the result
        log_debug("Update check run with result")
        if not github_update_check_run(ci_data, check_run, test):
            log_error("Failed to update check run on Github")

        # Also post comment on PR for backward compatibility
        log_debug("Submit the result to github PR comment")
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

    if args.jobs == "auto":
        args.jobs = str(os.cpu_count())

    ci_data = Context(config_file=os.path.abspath(args.config),
                      github_repo=args.repo,
                      src_dir=main_src,
                      patch_root=args.patch_root,
                      branch=args.branch, dry_run=args.dry_run,
                      bluez_dir=args.bluez_dir, ell_dir=args.ell_dir,
                      kernel_dir=args.kernel_dir, pr_num=args.pr_num,
                      space=args.space, jobs=args.jobs)

    # Setup Source for the test that needs to access the base like incremental
    # build and scan build. Fetch origin/master so we have the base branch
    # ref available (the shallow clone from actions/checkout only has the
    # merge commit).
    pr = ci_data.gh.get_pr(args.pr_num, force=True)
    cmd = ['fetch', 'origin', 'master']
    if ci_data.src_repo.git(cmd):
        log_error("Failed to fetch origin/master")
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
