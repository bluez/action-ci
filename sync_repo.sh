#!/bin/sh

set -e

# Synchronize the current repo with upstream repo
#
# The source should be in $GITHUB_WORKSPACE

# Input Parameters:
UPSTREAM_REPO=$1
UPSTREAM_BRANCH=$2
ORIGIN_BRANCH=$3
WORKFLOW_BRANCH=$4

echo ">>> Setup repo"
echo "$ git checkout $ORIGIN_BRANCH"
git checkout $ORIGIN_BRANCH
echo "$ git remote set-url origin $GITHUB_REPOSITORY"
git remote set-url origin "https://$GITHUB_ACTOR:$GITHUB_TOKEN@github.com/$GITHUB_REPOSITORY"
echo "$ git remote add upstream $UPSTREAM_REPO"
git remote add upstream "$UPSTREAM_REPO"
echo "$ git fetch upstream $UPSTREAM_BRANCH"
git fetch upstream $UPSTREAM_BRANCH

echo ">>> Check Origin and Upstream"
ORIGIN_HEAD=$(git log -1 --format=%H origin/$ORIGIN_BRANCH)
echo "ORIGIN_HEAD: $ORIGIN_HEAD"
UPSTREAM_HEAD=$(git log -1 --format=%H upstream/$UPSTREAM_BRANCH)
echo "UPSTREAM_HEAD: $UPSTREAM_HEAD"

if [ "$ORIGIN_HEAD" = "$UPSTREAM_HEAD" ]; then
    echo "Repos are already synched. Eixt..."
    exit 0
fi
echo "Repos are NOT synced. Need to merge..."

echo ">>> Sync origin with upstream"
echo "$ git remote set-branches origin *"
git remote set-branches origin '*'
echo "$ git fetch origin --unshallow"
git fetch origin --unshallow
echo "$ git push -f origin refs/remotes/upstream/$UPSTREAM_BRANCH:refs/heads/$ORIGIN_BRANCH"
git push -f origin "refs/remotes/upstream/$UPSTREAM_BRANCH:refs/heads/$ORIGIN_BRANCH"
echo "$ git push -f origin refs/tags/*"
git push -f origin "refs/tags/*"

echo ">>> Rebase workflow commits onto updated master"
# Fetch the updated origin to get the new master ref
echo "$ git fetch origin $ORIGIN_BRANCH $WORKFLOW_BRANCH"
git fetch origin $ORIGIN_BRANCH $WORKFLOW_BRANCH

# Find workflow-only commits: those that touch .github/ and are unique to
# the workflow branch (not in master). We filter by path to avoid picking
# up old Bluetooth commits that may linger if the branches had diverged.
WORKFLOW_COMMITS=$(git log --reverse --format=%H origin/$ORIGIN_BRANCH..origin/$WORKFLOW_BRANCH -- .github/)
COMMIT_COUNT=$(echo "$WORKFLOW_COMMITS" | grep -c . || true)
echo "Found $COMMIT_COUNT workflow commit(s) to rebase"

if [ "$COMMIT_COUNT" -eq 0 ]; then
    echo "ERROR: No workflow commits found to rebase. Aborting."
    exit 1
fi

echo "$ git checkout -b $WORKFLOW_BRANCH origin/$ORIGIN_BRANCH"
git checkout -b $WORKFLOW_BRANCH origin/$ORIGIN_BRANCH
echo "$ git branch"
git branch

for SHA in $WORKFLOW_COMMITS; do
    SUBJECT=$(git log -1 --format=%s $SHA)
    echo "Cherry-picking: $SHA ($SUBJECT)"
    git cherry-pick $SHA
done

echo "$ git push -f origin $WORKFLOW_BRANCH"
git push -f origin $WORKFLOW_BRANCH

echo ">>> Done Exit"
exit 0
