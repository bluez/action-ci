#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import json
import logging
import argparse

from datetime import datetime, timezone
from github import Github

from libs import init_logger, log_debug, log_error, log_info, pr_get_sid
from libs import GithubTool, EmailTool, Patchwork

dry_run = False
email_config = None
email_token = None
pw = None

MAGIC_LINE = "BlueZ Testbot Message:"
MAGIC_LINE_2 = "BlueZ Testbot Message #2:"
MAGIC_LINE_3 = "BlueZ Testbot Message #3:"
MAGIC_LINE_4 = "BlueZ Testbot Message #4:"

PATCH_SUBMISSION_MSG = '''
This is an automated message and please do not change or delete.

Dear submitter,

Thanks for submitting the pull request to the BlueZ github repo.
Currently, the BlueZ repo in Github is only for CI and testing purposes,
and not accepting any pull request at this moment.

If you still want us to review your patch and merge them, please send your
patch to the Linux Bluetooth mailing list(linux-bluetooth@vger.kernel.org).

For more detail about submitting a patch to the mailing list,
Please refer \"Submitting patches\" section in the HACKING file in the source.

Note that this pull request will be closed in the near future.

Best regards,
BlueZ Team
'''

PATCH_SUBMISSION_MSG_2 = '''
This is an automated message and please do not change or delete.

Dear submitter,

This is a friendly reminder that this pull request will be closed within
a week or two.

If you already submitted the patches to the Linux Bluetooth mailing list
(linux-bluetooth@vger.kernel.org) for review, Please close this pull
request.

If you haven't submitted the patches but still want us to review your patch,
please send your patch to the Linux Bluetooth mailing list
(linux-bluetooth@vger.kernel.org).

For more detail about submitting a patch to the mailing list,
Please refer \"Submitting patches\" section in the HACKING file in the source.

Note that this pull request will be closed in a week or two.

Best regards,
BlueZ Team
'''

PATCH_SUBMISSION_MSG_3 = '''
This is an automated message and please do not change or delete.

Dear submitter,

Thanks for submitting the pull request to the BlueZ github repo.
Currently, the BlueZ repo in Github is only for CI and testing purposes,
and not accepting any pull request at this moment.

If you still want us to review your patch and merge them, please send your
patch to the Linux Bluetooth mailing list(linux-bluetooth@vger.kernel.org).

For more detail about submitting a patch to the mailing list,
Please refer \"Submitting patches\" section in the HACKING file in the source.

Note that this pull request will be closed in the near future.

Best regards,
BlueZ Team
'''

PATCH_SUBMISSION_MSG_4 = '''
This is an automated message and please do not change or delete.

Closing without taking any action.

If you still want this change to be considered, it must be resent as a
patch to the Linux Bluetooth mailing list
(linux-bluetooth@vger.kernel.org). Closing this pull request doesn't
submit anything on your behalf.

Best regards,
BlueZ Team
'''

ARCHIVE_EMAIL_SUBJECT = "[BlueZ] Pull Request #{number} was closed: {title}"

ARCHIVE_EMAIL_MESSAGE = '''This is an automated email and please do not reply to this email.

The following pull request was open for more than 2 weeks in the BlueZ
Github repository and it was closed automatically without taking any action.

   Pull Request: #{number}
   Title:        {title}
   Submitter:    {submitter}
   Created:      {created_at}
   URL:          {url}

Note that the BlueZ repo in Github is only for CI and testing purposes and
it doesn't accept any pull request. The patches should be sent to the Linux
Bluetooth mailing list (linux-bluetooth@vger.kernel.org) for review.

If the change should still be considered, it must be resent as a patch to
the Linux Bluetooth mailing list (linux-bluetooth@vger.kernel.org). Closing
the pull request doesn't submit anything on the submitter's behalf and no
further action is taken on it.

---
Regards,
Linux Bluetooth
'''

ARCHIVE_SERIES_EMAIL_MESSAGE = '''This is an automated email and please do not reply to this email.

Dear Submitter,

This series was picked up by the CI more than 2 weeks ago and the pull
request created for it is still open, which means the series was never
applied to the tree.

   Series:       {title}
   Pull Request: {url}
   Created:      {created_at}

The pull request has been closed and no further action is taken on this
series.

If the change should still be considered, it must be resent to the Linux
Bluetooth mailing list (linux-bluetooth@vger.kernel.org) so that it is
picked up again.

---
Regards,
Linux Bluetooth
'''

def get_archive_receivers(submitter=None):
    """
    Get the list of receivers for the archive notification.
    """
    receivers = []

    if email_config.get('only-maintainers', False):
        receivers.extend(email_config.get('maintainers', []))
    else:
        if 'default-to' in email_config:
            receivers.append(email_config['default-to'])
        if submitter:
            receivers.append(submitter)

    # Remove the duplicated entries but keep the order
    return list(dict.fromkeys(receivers))

def get_series(pw_sid):
    """
    Get the patchwork series for the given series id. Returns None if the
    series cannot be retrieved.
    """
    if not pw or not pw_sid:
        return None

    try:
        series = pw.get_series(pw_sid)
    except Exception as e:
        log_error(f"Failed to get the series {pw_sid} from patchwork: {e}")
        return None

    if not series or not series.get('patches', None):
        log_error(f"No patch found in the series {pw_sid}")
        return None

    return series

def compose_archive_email(pr, series):
    """
    Compose the archive notification email. If the PR was created from a
    patchwork series, the email is sent as a reply to the first patch of
    the series so that it lands in the original thread.
    """
    headers = {}

    if series:
        patch_1 = series['patches'][0]
        # Reply to the original submission instead of starting a new thread
        headers['In-Reply-To'] = patch_1['msgid']
        headers['References'] = patch_1['msgid']

        subject = f"RE: {series['name']}"
        body = ARCHIVE_SERIES_EMAIL_MESSAGE.format(title=series['name'],
                                                   url=pr.html_url,
                                                   created_at=pr.created_at)
        submitter = series['submitter']['email']
    else:
        subject = ARCHIVE_EMAIL_SUBJECT.format(number=pr.number,
                                               title=pr.title)
        body = ARCHIVE_EMAIL_MESSAGE.format(
                            number=pr.number,
                            title=pr.title,
                            submitter=pr.user.login if pr.user else "Unknown",
                            created_at=pr.created_at,
                            url=pr.html_url)
        submitter = None

    if 'default-to' in email_config:
        headers['Reply-To'] = email_config['default-to']

    return subject, body, headers, submitter

def send_archive_email(pr, series=None):
    """
    Send an email notification when the PR is archived(closed)
    """
    if not email_config:
        log_debug("No email configuration. Skip sending email")
        return

    subject, body, headers, submitter = compose_archive_email(pr, series)

    receivers = get_archive_receivers(submitter)
    if not receivers:
        log_error("No email receiver found. Skip sending email")
        return

    # Use a new EmailTool instance for each email to avoid reusing the
    # same message object.
    email = EmailTool(token=email_token, config=email_config)
    email.set_receivers(receivers)
    email.compose(subject, body, headers)

    if dry_run:
        log_info("Dry-Run: Skip sending email")
        return

    if not email_token:
        log_info("No EMAIL_TOKEN found. Skip sending email")
        return

    log_info(f"Sending archive notification email for PR#{pr.number}")
    email.send()

def get_comment_str(magic_line):
    """
    Generate the comment string including magic_line
    """
    if magic_line == MAGIC_LINE:
        msg = PATCH_SUBMISSION_MSG
    if magic_line == MAGIC_LINE_2:
        msg = PATCH_SUBMISSION_MSG_2
    if magic_line == MAGIC_LINE_3:
        msg = PATCH_SUBMISSION_MSG_3
    if magic_line == MAGIC_LINE_4:
        msg = PATCH_SUBMISSION_MSG_4

    return magic_line + "\n\n" + msg

def get_magic_line(body):
    if (body.find(MAGIC_LINE) >= 0):
        return MAGIC_LINE
    if (body.find(MAGIC_LINE_2) >= 0):
        return MAGIC_LINE_2
    if (body.find(MAGIC_LINE_3) >= 0):
        return MAGIC_LINE_3
    if (body.find(MAGIC_LINE_4) >= 0):
        return MAGIC_LINE_4
    return None

def pr_add_comment(gh, pr, magic_line):
    """
    Add the comment based on magic line
    """
    comment = get_comment_str(magic_line)

    log_debug(f"Add PR comments{magic_line}:\n{comment}")

    if dry_run:
        log_info("Dry-Run: Skip adding comment to PR")
        return

    gh.pr_post_comment(pr, comment)

def pr_close(gh, pr):
    """
    Close pull request
    """
    log_debug(f"Close PR{pr.number}")

    if dry_run:
        log_info("Dry-Run: Skip closing PR")
        return

    gh.pr_close(pr)

def get_latest_comment(gh, pr):
    """
    Search through the comments and find the latest comment
    """
    comments = gh.pr_get_issue_comments(pr)
    if not comments:
        log_error("Unable to get the comments")
        return None

    log_info(f"PR#{pr.number} Comment count: {comments.totalCount}")

    for comment in comments.reversed:
        magic_line = get_magic_line(comment.body)
        if magic_line != None:
            log_debug(f"The most recent comment: {magic_line}")
            return magic_line

    log_debug("No bluez comment found")
    return None

def update_pull_request(gh, pr, days_created, magic_line, pw_sid=None):
    """
    Update the pull request based on the days passed since it was created
    and the latest comment line
    """

    # The PRs created from a patchwork series are created by the CI itself,
    # so there is no point in asking the submitter to send the patches to
    # the mailing list. Only close them once they get too old.
    if pw_sid:
        if days_created > 14:
            log_debug("PR from patchwork series is more than 2 weeks. Closing")
            series = get_series(pw_sid)
            pr_close(gh, pr)
            if series:
                send_archive_email(pr, series)
            else:
                # Without the series there is no message to reply to and
                # the generic notification doesn't apply to a PR created
                # by the CI itself.
                log_error(f"No series for SID {pw_sid}. Skip sending email")
        return

    if days_created < 7:
        log_debug("Days created < 7")
        if not magic_line:
            log_debug("New PR without any bot comment. Adding the 1st comment")
            pr_add_comment(gh, pr, MAGIC_LINE)
        else:
            log_debug(f"Found bot comment and skip for now: {magic_line}")

    if days_created >= 7 and days_created < 14:
        log_debug("7 <= Days created < 14")
        if magic_line == MAGIC_LINE_2 or magic_line == MAGIC_LINE_3:
            log_debug(f"Found bot comment and skip for now: {magic_line}")
        else:
            if magic_line == MAGIC_LINE:
                log_debug("Found 1st comment. Adding the 2nd comment")
                pr_add_comment(gh, pr, MAGIC_LINE_2)
            else:
                log_debug("Old but no comment. Adding the comment #3")
                pr_add_comment(gh, pr, MAGIC_LINE_3)

    if days_created > 14:
        log_debug("Days created > 14")
        log_debug("PR is more than 2 weeks and close the PR")
        pr_add_comment(gh, pr, MAGIC_LINE_4)
        pr_close(gh, pr)
        send_archive_email(pr)

def manage_pr(gh):

    prs = gh.get_prs(force=True)
    log_info(f"Pull Request count: {prs.totalCount}")

    # Handle each PR
    for pr in prs:
        log_debug(f"Check PR#_{pr.number}")

        # Check if this PR is created from a Patchwork series.
        pw_sid = pr_get_sid(pr.title)
        if pw_sid:
            log_info(f"PR is created with Patchwork SID: {pw_sid}")

        # Calculate the number of days since PR was created
        # PyGithub returns timezone-aware datetimes (UTC), but older
        # versions returned naive ones. Normalize before subtracting.
        created_at = pr.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - created_at
        days_created = delta.days

        log_debug(f"PR opened {days_created} days ago")

        # No bot comment is posted to the PRs created from a patchwork
        # series, so there is no need to look them up.
        magic_line = None if pw_sid else get_latest_comment(gh, pr)

        # Update the PR
        update_pull_request(gh, pr, days_created, magic_line, pw_sid)

def parse_args():
    """ Parse input argument """

    ap = argparse.ArgumentParser(description="Clean up PR")
    ap.add_argument('-d', '--dry-run', action='store_true', default=False,
                    help='Run it without updating the PR')
    ap.add_argument('-c', '--config', default=None,
                    help='Configuration file with the email settings')
    # Positional parameter
    ap.add_argument("repo",
                    help="Name of Github repository. i.e. bluez/bluez")
    return ap.parse_args()

def main():

    global dry_run
    global email_config
    global email_token
    global pw

    init_logger("ManagePR", verbose=True)

    args = parse_args()

    # Make sure GITHUB_TOKEN exists
    if 'GITHUB_TOKEN' not in os.environ:
        log_error("Set GITHUB_TOKEN environment variable")
        sys.exit(1)

    # Load the email and the patchwork configuration if it is available.
    # The email notification is optional and it is skipped when the
    # configuration or the token is missing.
    if args.config:
        config_file = os.path.abspath(args.config)
        if not os.path.exists(config_file):
            log_error(f"Invalid parameter(config) {args.config}")
            sys.exit(1)
        with open(config_file, 'r') as f:
            config = json.load(f)

        email_config = config.get('email', None)
        if not email_config:
            log_error("No email section in the configuration file")

        pw_config = config.get('patchwork', None)
        if pw_config:
            try:
                pw = Patchwork(pw_config['url'], pw_config['project_name'])
            except Exception as e:
                log_error(f"Failed to initialize Patchwork class: {e}")
        else:
            log_error("No patchwork section in the configuration file")

    email_token = os.environ.get('EMAIL_TOKEN', None)
    if not email_token:
        log_info("No EMAIL_TOKEN found. Email notification is disabled")

    # Initialize github repo object
    try:
        gh = GithubTool(args.repo, os.environ['GITHUB_TOKEN'])
    except:
        log_error("Failed to initialize GithubTool class")
        sys.exit(1)

    dry_run = args.dry_run

    manage_pr(gh)

if __name__ == "__main__":
    main()


