# Safe branch maintenance

## Recorded ancestry after v2.0.0

At the start of the post-release work, `origin/master`, `codex/v2-release-candidate`, and the commit referenced by `v2.0.0` were all `7b17e7a`. `v2/provider-health` was four commits behind `origin/master` at `fe8056e`. The user's local `master` was older at `b61c9c7`; it was deliberately not moved. Dependabot PR branches were one commit ahead of an older common base and mostly two commits behind `origin/master`.

Use `git rev-parse v2.0.0^{commit}` for annotated tags; plain `git rev-parse v2.0.0` returns the tag object, not the tagged commit.

## Move the primary checkout back to current master

Run these commands in the user's primary checkout, not in an active Codex worktree:

```powershell
git status --short --branch
git fetch --all --tags --prune
git worktree list
git switch master
git merge --ff-only origin/master
git status --short --branch
```

If `git status` reports uncommitted tracked work, stop before switching. Commit it to a clearly named backup branch or save `git diff` and `git diff --staged` patches first. Do not discard files, and never copy `config.json` or `history.json` into Git.

The `--ff-only` guard prevents an accidental merge commit or history rewrite. It is expected to update the stale local `master` after the user's work is secured.

## Delete only proven merged branches

First prove ancestry and ensure no worktree is using the branch:

```powershell
git fetch origin --prune
git worktree list
git merge-base --is-ancestor v2/provider-health origin/master
git merge-base --is-ancestor codex/v2-release-candidate origin/master
```

Exit code 0 means the named branch tip is reachable from `origin/master`. Only then, and only when `git worktree list` does not show the branch as active, the owner may run:

```powershell
git branch -d v2/provider-health
git branch -d codex/v2-release-candidate
git push origin --delete v2/provider-health
git push origin --delete codex/v2-release-candidate
```

These are owner cleanup commands, not release automation. Never use `-D`, force-push, or delete a branch merely because it looks old in a UI.

Preview stale remote-tracking refs before pruning them:

```powershell
git remote prune origin --dry-run
git fetch origin --prune
```

Pruning removes only local references to remote branches that are already gone; it does not delete remote branches or active worktrees.
