# Clean public release

This playbook replaces a repository with a new public object database. It is for a
privacy boundary, not routine versioning. The old repository must remain a private,
access-controlled archive; a force-push, branch deletion, or GitHub's **Archive this
repository** setting does not erase or hide old Git objects.

`pipeline/release.py` is deliberately a verifier, not a release tool. It performs
only local Git reads. It does not initialize, add, commit, clone, fetch, configure a
remote, push, call GitHub, change visibility, deploy, or run any project code. Every
state-changing command below is a maintainer action and must be reviewed before it
is run.

## What the verifier proves

Given a candidate working repository, an exact neutral commit identity, and a
private denylist, it checks:

- `.git` is an ordinary directory owned by this worktree, with no linked worktree,
  alternate object store, graft, shallow history, or partial-clone promisor;
- every ref resolves to one parentless commit and there are no tags, replacement
  refs, stashes, or other histories;
- the object database contains exactly the commit, trees, and blobs reachable from
  `HEAD`; strict full `git fsck` reports nothing, including unreachable objects;
- the index and working tree exactly match `HEAD`, the CI workflow is present, and
  the tree contains no submodule Git links;
- the author and committer name are exactly the declared neutral name and every
  email is the declared `@users.noreply.github.com` address;
- committed paths, every blob (including binary blobs), and raw commit metadata do
  not match home-directory, internal reviewer-identity, or private denylist
  patterns.

The output intentionally reports the file and pattern category, never the matched
private value. The verifier disables Git prompts, optional locks, automatic
maintenance, and filesystem monitoring. It does not prove that a denylist is
complete, that a remote is public, that hosted CI passed, or that a deployment is
safe. Those remain separate review evidence.

## Freeze and private denylist

Freeze writes to the old checkout and finish the intended release commit there.
Run the normal tests and generated-artifact validation before exporting. Record the
old repository path and commit for private recovery records only; do not copy that
commit ID into the new public repository if its old history is sensitive.

Create `privacy-patterns.txt` outside the old repository, candidate, and anonymous
clone. Put one case-insensitive literal on each line. Blank lines and lines beginning
with `#` are ignored; active values must be at least four bytes. Include, at minimum:

- legal and display names that must not be public;
- personal and former email addresses;
- private or unrelated GitHub, social, and forum handles, plus account-specific URLs;
- local account names, device names, absolute workspace components, and private
  hostnames;
- internal reviewer/fleet labels and private project or customer terms.

Keep this file out of shell history, CI logs, tickets, and both Git repositories.
Restrict it to the release reviewers. The generic rules cover root-account, Linux,
macOS, and Windows user-profile paths, but the private denylist is still required
because generic rules cannot know which public-looking name, email, or social URL
belongs to the maintainer.
Do not deny the public repository owner or the exact noreply identity intentionally
used for the release; those values must remain visible in the remote and root commit.

## Build the staging repository

Use three sibling locations on a protected volume:

- `/protected/work/atlas` — the frozen old checkout;
- `/protected/work/atlas-public-stage` — a new, empty directory;
- `/protected/work/privacy-patterns.txt` — the external private denylist.

Export only the reviewed committed tree. Never clone the old repository, copy its
`.git` directory, reuse an old empty-looking directory, or initialize inside the old
checkout. One reviewable approach is:

```sh
mkdir /protected/work/atlas-public-stage
git -C /protected/work/atlas archive --format=tar HEAD \
  | tar -x -C /protected/work/atlas-public-stage
```

Review the exported file manifest before initialization, including the effect of any
`.gitattributes` `export-ignore` rules. Then create the only public commit with
repository-local identity configuration. Use the account's exact GitHub noreply
address; the example is intentionally not a maintainer identity.

```sh
git -C /protected/work/atlas-public-stage init --initial-branch=main
git -C /protected/work/atlas-public-stage config --local user.name "Atlas Release"
git -C /protected/work/atlas-public-stage config --local user.email \
  "atlas-release@users.noreply.github.com"
git -C /protected/work/atlas-public-stage add -A
git -C /protected/work/atlas-public-stage commit --no-gpg-sign -m "Initial public release"
```

Run the project's test and build suite in the staging checkout as a separate step.
Then run the read-only verifier from the frozen trusted checkout:

```sh
python3 /protected/work/atlas/pipeline/release.py \
  /protected/work/atlas-public-stage \
  --identity-name "Atlas Release" \
  --identity-email "atlas-release@users.noreply.github.com" \
  --deny-file /protected/work/privacy-patterns.txt
```

All checks must pass. Record the full staging `HEAD` SHA in the private release
worksheet. Do not “clean” a failure with object deletion or history rewriting;
discard the staging directory, correct the frozen source, and create another fresh
staging directory so the fresh-object-database claim stays simple.

## GitHub cutover

Do not reuse the old GitHub repository. A one-commit force-push can leave old
objects, pull-request refs, caches, forks, releases, Actions artifacts, or third-party
clones outside the new branch history.

The reviewed cutover order is:

1. Confirm the old GitHub repository is private. If it has ever been public, treat
   its contents as disclosed: revoke exposed credentials, remove sensitive hosted
   artifacts, and follow the incident process. A clean replacement cannot recall
   existing clones or forks.
2. Rename the old private GitHub repository to a clearly private archive name. Keep
   it private, remove deploy credentials and scheduled workflows, restrict access,
   and only then use GitHub's archive setting. Archiving alone is not a privacy
   control.
3. Create a brand-new, empty GitHub repository at the final public name. Do not add
   a README, license, `.gitignore`, template, or initial commit in the GitHub UI.
4. Only after the local proof passes, attach that new URL to the staging repository
   and push its single branch. Review the exact remote URL before pushing. Never add
   the new public remote to the old checkout.
5. Enable public visibility only after the pushed SHA equals the recorded staging
   SHA and repository settings, Actions permissions, secrets, variables, Pages, and
   branch rules have been reviewed. Keep scheduled feed and deployment switches off
   until their separate release reviews pass.
6. Complete the anonymous-clone and hosted-CI proof below before changing local
   directory names or announcing the release.

These actions change GitHub state and are intentionally not encoded in the verifier.
Use GitHub's UI or an independently reviewed runbook so visibility changes cannot be
mistaken for a local validation command.

## Anonymous clone and CI proof

On a clean machine or disposable account-free environment, clone the exact public
HTTPS URL with credential helpers disabled. Do not use SSH, GitHub CLI authentication,
a filesystem path, or a clone made before the visibility change.

```sh
git -c credential.helper= clone \
  https://github.com/example/atlas.git \
  /protected/proof/atlas-anonymous
```

Transfer the denylist through the approved private channel to a path outside the
clone, then verify the anonymous clone against the SHA recorded from staging:

```sh
python3 /protected/proof/atlas-anonymous/pipeline/release.py \
  /protected/proof/atlas-anonymous \
  --identity-name "Atlas Release" \
  --identity-email "atlas-release@users.noreply.github.com" \
  --deny-file /protected/proof/privacy-patterns.txt \
  --origin https://github.com/example/atlas.git \
  --expected-head 0123456789abcdef0123456789abcdef01234567
```

The anonymous mode still performs no network operation. It additionally requires
the exact credential-free GitHub HTTPS origin, the expected public SHA, one local
branch, and only the corresponding `origin` tracking refs.

Complete and retain this checklist with the release evidence:

- [ ] The clone succeeded without a prompt, token, SSH key, GitHub session, or
      credential helper.
- [ ] Every verifier check passed and its SHA matched the staging SHA.
- [ ] Logged-out browser access to the repository, root commit, and file tree
      succeeds; the commits view contains only the root release commit.
- [ ] The `check` workflow ran for that exact SHA in the new repository and every
      required job is green. A local test run or a workflow from the old repository
      is not substitute evidence.
- [ ] Logged-out Pages access succeeds only if Pages is in scope, and browser network
      inspection shows no maintainer-only hosts, paths, keys, or account data.
- [ ] Repository releases, packages, Actions artifacts/caches, environments, Pages
      history, pull requests, issues, wikis, and tags contain no inherited old data.
- [ ] Scheduled feed and automatic deploy jobs remain disabled until separately
      authorized.

## Local archive/staging swap

After the anonymous and CI evidence is complete, close processes using either
checkout. Rename the old checkout first and never overwrite it:

```sh
mv /protected/work/atlas /protected/work/atlas-private-archive-20260825
mv /protected/work/atlas-public-stage /protected/work/atlas
```

Confirm the new `/protected/work/atlas` still has the verified SHA and public remote.
Keep the old directory on encrypted, access-controlled storage; its `.git` directory,
reflogs, ignored files, caches, local configuration, and credentials are all private.
Do not zip it into the public repository, upload it as a release asset, or use it for
public deployment.

If the cutover fails, make the new repository private and restore the old local
directory name only after reviewing the exact paths. Do not solve a failed privacy
proof by force-pushing the old history or deleting the private archive.
