#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import json
import re
import argparse
import tempfile

from github import Github

from libs import init_logger, log_debug, log_error, log_info, pr_get_sid
from libs import Patchwork, GithubTool, RepoTool, EmailTool, Context

def patch_get_new_file_list(patch):
    """
    Parse patch to get the file that is newly added
    """

    file_list = []

    # If patch has no contents, return empty file
    if patch == None:
        log_error("WARNING: No file found in patch")
        return file_list

    # split patch(in string) to list of string by newline
    lines = patch.split('\n')
    iter_lines = iter(lines)
    for line in iter_lines:
        try:
            if re.search(r'^\-\-\- ', line):
                if line.find('dev/null') >= 0:
                    # Detect new file. Read next line to get the filename
                    line2 = next(iter_lines)
                    file_list.append(line2[line2.find('/')+1:])
        except StopIteration:
            # End of iteration or no next line. Nothing to do. Just pass
            pass

    log_debug(f"New file in the patch: {file_list}")

    return file_list

def patch_get_file_list(patch):
    """
    Parse patch to get the file list
    """

    file_list = []

    # If patch has no contents, return empty file
    if patch == None:
        log_error("WARNING: No file found in patch")
        return file_list

    # split patch(in string) to list of string by newline
    lines = patch.split('\n')
    for line in lines:
        # Use --- (before) instead of +++ (after).
        # If new file is added, --- is /dev/null and can be ignored
        # If file is removed, file in --- still exists in the tree
        # The corner case is if the patch adds new files. Even in this case
        # even if new files are ignored, Makefile should be changed as well
        # so it still can be checked.
        if re.search(r'^\-\-\- ', line):
            # For new file, it should be dev/null. Ignore the file.
            if line.find('dev/null') >= 0:
                log_debug("New file is added. Ignore in the file list")
                continue

            # Trim the '--- /'
            file_list.append(line[line.find('/')+1:])

    log_debug(f"files found in the patch: {file_list}")

    return file_list

def series_get_file_list(ci_data, series, ignore_new_file=False):
    """
    Get the list of files from the patches in the series.
    """

    file_list = []
    new_file_list = []

    for patch in series['patches']:
        full_patch = ci_data.pw.get_patch(patch['id'])
        file_list += patch_get_file_list(full_patch['diff'])
        if ignore_new_file:
            new_file_list += patch_get_new_file_list(full_patch['diff'])

    if ignore_new_file == False or len(new_file_list) == 0:
        return file_list

    log_debug("Check if new file is in the file list")
    new_list = []
    for filename in file_list:
        if filename in new_file_list:
            log_debug(f"file:{filename} is in new_file_list. Don't count.")
            continue
        new_list.append(filename)

    return new_list

def filter_repo_space(ci_data, space_details, series, src_dir):
    """
    Check if the series belong to this repository

    if the series[name] has exclude string
        return False
    if the series[name] has include string
        return True
    get file list from the patch in series
    if the file exist
        return True
    else
        return False
    """

    log_debug(f"Check repo space for this series[{series['id']}]")

    # Check Exclude string
    for str in space_details['exclude']:
        if re.search(str, series['name'], re.IGNORECASE):
            log_debug(f"Found EXCLUDE string: {str}")
            return False

    # Check Include string
    for str in space_details['include']:
        if re.search(str, series['name'], re.IGNORECASE):
            log_debug(f"Found INCLUDE string: {str}")
            return True

    # Get file list from the patches in the series
    file_list = series_get_file_list(ci_data, series, ignore_new_file=True)
    if len(file_list) == 0:
        # Something is not right.
        log_error("ERROR: No files found in the series/patch")
        return False
    log_debug(f"Files in series={file_list}")

    # File exist in source tree?
    for filename in file_list:
        file_path = os.path.join(src_dir, filename)
        if not os.path.exists(file_path):
            log_error(f"File not found: {filename}")
            return False

    # Files exist in the source tree
    print("Files exist in the source tree.")
    return True

EMAIL_MESSAGE = '''This is an automated email and please do not reply to this email.

Dear Submitter,

Thank you for submitting the patches to the linux bluetooth mailing list.
While preparing the CI tests, the patches you submitted couldn't be applied to the current HEAD of the repository.

----- Output -----
{content}

Please resolve the issue and submit the patches again.


---
Regards,
Linux Bluetooth

'''

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

def send_email(ci_data, series, content):

    headers = {}
    email_config = ci_data.config['email']

    body = EMAIL_MESSAGE.format(content=content)

    patch_1 = series['patches'][0]
    headers['In-Reply-To'] = patch_1['msgid']
    headers['References'] = patch_1['msgid']

    if not is_maintainers_only(email_config):
        headers['Reply-To'] = email_config['default-to']

    receivers = get_receivers(email_config,
                              series['submitter']['email'])
    ci_data.email.set_receivers(receivers)

    ci_data.email.compose(f"RE: {series['name']}", body, headers)

    if ci_data.config['dry_run']:
        log_info("Dry-Run: Skip sending email")
        return

    log_info("Sending Email...")
    ci_data.email.send()

def series_check_patches(ci_data, series):

    # Save series/patches to the local directory
    series_dir = os.path.join(ci_data.config['temp_root'], f"{series['id']}")
    if not os.path.exists(series_dir):
        os.makedirs(series_dir)
    log_debug(f"Series PATH: {series_dir}")

    # Reset source branch to base branch
    if ci_data.src_repo.git_checkout(ci_data.config['branch']):
        # No need to continue
        log_error(f"ERROR: Failed: git checkout {ci_data.config['branch']}")
        return False

    # Create branch for series
    if ci_data.src_repo.git_checkout(f"{series['id']}", create_branch=True):
        log_error(f"ERROR: Failed: git checkout -b {series['id']}")
        return False

    # Already checked?
    already_checked = False
    patch_1 = ci_data.pw.get_patch(series['patches'][0]['id'])
    if patch_1['check'] != 'pending':
        already_checked = True
        log_info("This series is already checked")

    verdict = True
    content = ""

    # Process the patches in this series
    log_debug("Process the patches in this series")
    for patch in series['patches']:
        log_debug(f"Patch: {patch['id']}: {patch['name']}")
        patch_mbox = ci_data.pw.get_patch_mbox(patch['id'])
        patch_path = os.path.join(series_dir, f"{patch['id']}.patch")
        with open(patch_path, 'w') as f:
            f.write(patch_mbox)
        log_debug(f"Patch mbox saved to file: {patch_path}")

        # Apply patch
        if ci_data.src_repo.git_am(patch_path):
            # git am failed. Update patchwork/checks and abort
            verdict = False

            # Update the contents for email body
            content = ci_data.src_repo.stderr

            ci_data.src_repo.git_am(abort=True)

            if ci_data.config['dry_run'] or already_checked:
                log_info("Skip submitting the result to PW")
                break

            ci_data.pw.post_check(patch, "pre-ci_am", 3, content)
            break

        # git am success
        if ci_data.config['dry_run'] or already_checked:
            log_info("Skip submitting the result to PW: Success")
        else:
            ci_data.pw.post_check(patch, "pre-ci_am", 1, "Success")

    if not verdict:
        log_info("PRE-CI AM failed. Notify the submitter")
        if ci_data.config['dry_run'] or already_checked:
            log_info("Skip sending email")
            return False

        send_email(ci_data, series, content)

        return False

    if ci_data.config['disable_pr']:
        log_info("Disable PR: Skip creating PR")
        return True

    # Create Pull Request
    if ci_data.src_repo.git_push(f"{series['id']}"):
        log_error("Failed to push the source to Github")
        return False

    title = f"[PW_SID:{series['id']}] {series['name']}"

    # Use the commit of the patch for pr body
    patch_1 = ci_data.pw.get_patch(series['patches'][0]['id'])
    log_info(f"Creating PR: {title}")
    if ci_data.gh.create_pr(title, patch_1['content'], ci_data.config['branch'],
                            f"{series['id']}"):
        return True

    return False

def run_series(ci_data, new_series):

    log_debug("##### Processing Series #####")

    space_details = ci_data.config['space_details'][ci_data.config['space']]

    # Process the series
    for series in new_series:
        log_info(f"\n### Process Series: {series['id']} ###")

        # If the series subject doesn't have the key-str, ignore it.
        # Sometimes, the name have null value. If that's the case, use the
        # name from the first patch and update to series name
        if series['name'] == None:
            patch_1 = series['patches'][0]
            series['name'] = patch_1['name']
            log_debug(f"updated series name: {series['name']}")

        # Filter the series by include/exclude string
        if not filter_repo_space(ci_data, space_details, series,
                                 ci_data.src_dir):
            log_info(f"Series is NOT for this repo")
            continue

        # Check if PR already exist
        if ci_data.gh.pr_exist_title(f"PW_SID:{series['id']}"):
            log_info("PR exists already")
            continue

        # This series is ready to create PR
        series_check_patches(ci_data, series)

    log_debug("##### processing Series Done #####")

def sid_in_series_list(sid, series_list):

    log_debug(f"Search PW SID({sid} in the series list")
    for series in series_list:
        if int(sid) == series['id']:
            log_debug("Found matching PW_SID in series list")
            return series

    log_debug("No found matching PW_SID in series list")

    return None

def cleanup_pullrequest(ci_data, new_series):

    log_debug("##### Clean Up Pull Request #####")

    prs = ci_data.gh.get_prs(force=True)
    log_debug(f"Current PR: {prs}")
    for pr in prs:
        log_debug(f"PR: {pr}")
        pw_sid = pr_get_sid(pr.title)
        if not pw_sid:
            log_debug(f"Not a valid PR title: {pr.title}. Skip PR")
            continue

        log_debug(f"PW_SID: {pw_sid}")

        if sid_in_series_list(pw_sid, new_series):
            log_debug(f"PW_SID:{pw_sid} found in PR list. Keep PR")
            continue

        log_debug(f"PW_SID:{pw_sid} not found in PR list. Close PR")

        ci_data.gh.close_pr(pr.number)

    log_debug("##### Clean Up Pull Request Done #####")

def check_args(args):

    if not os.path.exists(os.path.abspath(args.config)):
        log_error(f"Invalid parameter(config) {args.config}")
        return False

    if args.space != 'kernel' and args.space != 'user':
        log_error(f"Invalid parameter(space) {args.space}")
        return False

    if not os.path.exists(os.path.abspath(args.src_dir)):
        log_error(f"Invalid parameter(src_dir) {args.src_dir}")
        return False

    return True

def parse_args():
    ap = argparse.ArgumentParser(description=
                            "Manage patch series in Patchwork and create PR")
    ap.add_argument('-c', '--config', default='./config.json',
                    help='Configuration file to use')
    ap.add_argument("-b", "--branch", default="master",
                    help="Name of branch in base_repo where the PR is pushed. "
                         "Use <BRANCH> format. i.e. master")
    ap.add_argument('-s', '--src-dir', required=True,
                    help='Source directory')
    ap.add_argument('-d', '--dry-run', action='store_true', default=False,
                    help='Run it without uploading the result')
    ap.add_argument('-p', '--disable-pr', action='store_true', default=False,
                    help='Disable creating pull request')

    # Positional paramter
    ap.add_argument('space', choices=['user', 'kernel'],
                    help="user or kernel space")
    ap.add_argument("repo",
                    help="Name of Github repository. i.e. bluez/bluez")
    return ap.parse_args()

def main():

    init_logger("SyncPatchwork", verbose=True)

    args = parse_args()
    if not check_args(args):
        sys.exit(1)

    # Set temp workspace
    temp_root = tempfile.TemporaryDirectory().name
    log_info(f"Temp Root Dir: {temp_root}")

    ci_data = Context(config_file=os.path.abspath(args.config),
                      github_repo=args.repo,
                      src_dir=args.src_dir,
                      patch_dir='', # XXX: convert script to use over temp_root
                      branch=args.branch,
                      space=args.space,
                      dry_run=args.dry_run,
                      disable_pr=args.disable_pr,
                      temp_root=temp_root)


    # Process the series, state 1 = NEW
    new_series = ci_data.pw.get_series_by_state(1)
    if len(new_series) == 0:
        log_info("No new patches/series found. Done. Exit")
        return

    # Process Series
    run_series(ci_data, new_series)

    # Cleanup PR
    cleanup_pullrequest(ci_data, new_series)

    log_debug("----- DONE -----")

if __name__ == "__main__":
    main()
