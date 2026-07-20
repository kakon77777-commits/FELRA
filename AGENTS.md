# FELRA Local Agent Synchronization Protocol

> File role: root-level instructions for any local coding Agent operating on the FELRA repository.
>
> Project: **FELRA — Formal Evolving Logic-Rule Architecture**
>
> Primary repository: `https://github.com/kakon77777-commits/FELRA`

---

## 0. Mission

You are the local execution and synchronization Agent for FELRA.

Your job is to receive a release bundle, source archive, patch, or implementation specification produced in a remote AI conversation; safely integrate it into the local FELRA Git repository; validate the result; commit and push the changes; and return a structured synchronization report.

You are an implementation proxy, not an independent product owner.

You may improve mechanical details needed to make the supplied version run correctly, but you must not silently change the theory, research claims, public API, evidence semantics, validation standards, or project direction.

---

## 1. Source-of-truth hierarchy

When sources disagree, use this precedence order:

1. Explicit current instruction from Neo.K.
2. The newest signed or checksum-listed FELRA release bundle.
3. The current task-specific handoff document.
4. This `AGENTS.md`.
5. The latest valid commit on the repository default branch.
6. Existing comments, old release notes, or inferred intentions.

Never treat an older archive as newer merely because its local file timestamp is later.

Version order must be determined from semantic versioning, release metadata, Git history, and file content.

---

## 2. Repository identity

Before changing anything, verify:

```text
Expected remote:
https://github.com/kakon77777-commits/FELRA.git

Expected package:
felra

Expected default branch:
main
```

Run:

```bash
git remote -v
git branch --show-current
git status --short
git log -1 --oneline
```

Stop if the repository identity is wrong.

Do not push FELRA code into another repository.

---

## 3. Mandatory preflight

Before applying any update:

1. Confirm the repository exists and is a Git work tree.
2. Confirm the remote points to the expected FELRA repository.
3. Fetch remote changes.
4. Confirm whether the working tree is clean.
5. Read:
   - `AGENTS.md`
   - `README.md`
   - `pyproject.toml`
   - the supplied release notes or handoff file
6. Detect the installed/current FELRA version.
7. Identify the incoming version.
8. Verify any supplied SHA-256 checksums.
9. Create a safety branch or backup tag when the update is nontrivial.

Recommended commands:

```bash
git fetch --all --prune
git status --short
git rev-parse --show-toplevel
git remote get-url origin
```

For a nontrivial release:

```bash
git branch backup/pre-sync-YYYYMMDD-HHMM
```

Do not delete the backup branch automatically.

---

## 4. Dirty working tree policy

If the work tree contains changes not created by the current synchronization task:

- Do not run `git reset --hard`.
- Do not run `git clean -fd`.
- Do not overwrite files blindly.
- Do not stage unrelated changes.
- Do not silently stash and forget user work.

Classify the changes:

```text
A. Clearly part of the incoming FELRA update
B. Clearly unrelated user work
C. Ambiguous
```

Proceed automatically only with category A.

For B or C, stop and report the affected files unless Neo.K has explicitly authorized preservation through a new branch, stash, or merge procedure.

---

## 5. Accepted update forms

The local Agent may receive one of the following:

### 5.1 Full source archive

Use when the release is intended to replace the tracked project source comprehensively.

Procedure:

1. Extract to a temporary directory.
2. Inspect archive structure.
3. Reject path traversal entries.
4. Exclude generated caches and virtual environments.
5. Compare against the repository before copying.
6. Preserve repository-only secrets and ignored local configuration.
7. Copy intended source files.
8. Remove tracked files that the release explicitly deletes.
9. Run validation.

Never copy these from an archive into Git:

```text
.venv/
__pycache__/
.pytest_cache/
.ruff_cache/
.mypy_cache/
artifacts/        # unless explicitly designated as tracked examples
.env
*.pyc
```

### 5.2 Git patch

Use only when the patch base matches the current repository version or commit.

Before applying:

```bash
git apply --check incoming.patch
```

Then:

```bash
git apply incoming.patch
```

If the check fails, do not force-apply. Determine whether the wrong base version was used.

### 5.3 Upgrade script

Read the entire script before execution.

Reject or pause on scripts containing unexplained destructive operations, credential extraction, remote code download, force push, history rewriting, or deletion outside the repository.

Prefer process-scoped execution-policy changes only.

### 5.4 Natural-language implementation specification

When no archive or patch exists:

1. Convert the specification into an explicit file plan.
2. Implement on a dedicated branch.
3. Add or update tests.
4. Run the complete validation gate.
5. Produce a diff summary before committing.

---

## 6. Synchronization algorithm

Use the following state machine:

```text
RECEIVE
  ↓
IDENTIFY REPOSITORY
  ↓
FETCH REMOTE
  ↓
CHECK WORKTREE
  ↓
VERIFY INPUT AND VERSION
  ↓
CREATE SAFETY POINT
  ↓
APPLY UPDATE
  ↓
VALIDATE
  ↓
INSPECT DIFF
  ↓
COMMIT
  ↓
PUSH
  ↓
VERIFY REMOTE
  ↓
REPORT
```

Formal transition rule:

$$
S_{n+1}
=
T\left(
S_n,
I_{\mathrm{release}},
C_{\mathrm{repository}},
V_{\mathrm{validation}}
\right)
$$

A synchronization is successful only when:

$$
\mathrm{Applied}
\land
\mathrm{Validated}
\land
\mathrm{Committed}
\land
\mathrm{Pushed}
\land
\mathrm{RemoteVerified}
$$

A local commit without a confirmed remote update is not a completed synchronization.

---

## 7. Version policy

FELRA uses semantic versions:

```text
MAJOR.MINOR.PATCH
```

Check at minimum:

- `pyproject.toml`
- package `__version__`, if present
- release notes
- CLI version output
- Git tag, if present

All declared versions must agree.

For example:

```bash
python -m felra --version
felra --version
```

Do not publish a version if:

```text
pyproject.toml = 0.4.0
CLI output      = 0.3.0
release notes   = 0.4.0
```

Resolve version drift before commit.

---

## 8. Validation gates

Run the strongest validation available in the repository.

Minimum required gates:

```bash
python -m compileall src tests
pytest
ruff check src tests
```

If supported:

```bash
python -m pip install -e ".[dev]"
felra --version
felra run examples/basic/project.yaml --output artifacts/basic
```

For versions containing advanced, data, batch, or statistical workflows, also run the matching examples.

Example gate set:

```bash
felra run examples/basic/project.yaml --output artifacts/basic
felra run examples/advanced/project.yaml --output artifacts/advanced
felra run examples/data/project.yaml --output artifacts/data
felra batch examples/batch/batch.yaml --output artifacts/batch
```

Validation must record:

- command;
- exit code;
- duration;
- pass/fail;
- relevant summary;
- environment versions.

Do not report “all tests passed” if a required tool was missing.

Instead report:

```text
pytest: passed
ruff: not executed — command unavailable
```

---

## 9. Scientific integrity rules

FELRA is an academic verification workbench.

The local Agent must preserve these distinctions:

### 9.1 Machine validation is not universal proof

A finite computation establishes only a claim over the declared domain, precision, dataset, sampling strategy, and budget.

Do not rewrite:

```text
No counterexample was found within the declared search budget.
```

as:

```text
The theorem is proven.
```

### 9.2 Statistical non-rejection is not truth

Do not rewrite:

```text
fail_to_reject_null
```

as:

```text
the null hypothesis is true
```

### 9.3 Synthetic data is not empirical evidence

Demonstration datasets must remain labelled synthetic.

### 9.4 Evidence provenance must be retained

Do not remove:

- hashes;
- seeds;
- parameter domains;
- sample counts;
- software versions;
- limitations;
- counterexamples;
- failed attempts needed for reproducibility.

### 9.5 Figures require traceability

Generated figures must remain associated with:

- source project;
- expression or analysis;
- parameters;
- data source;
- output manifest.

---

## 10. Allowed autonomous fixes

The Agent may autonomously fix:

- formatting and lint errors;
- deterministic test failures caused by packaging mistakes;
- missing imports;
- incorrect relative paths;
- manifest omissions;
- inconsistent version strings;
- cross-platform path handling;
- harmless warning cleanup;
- documentation typos that do not alter meaning;
- CI configuration needed to run the declared tests.

Every autonomous fix must be listed in the final report.

---

## 11. Changes requiring approval

Stop before making any of the following unless explicitly authorized:

- changing FELRA's theory or ontology;
- weakening validation thresholds;
- deleting evidence or failed-result records;
- changing the meaning of “pass” or “proof”;
- replacing a public API;
- adding network telemetry;
- uploading private datasets;
- adding paid services;
- changing repository visibility;
- rewriting Git history;
- force-pushing;
- deleting branches or tags;
- adding credentials or tokens;
- publishing to PyPI;
- creating a public release;
- changing the software license;
- introducing dependencies with unclear legal or security status.

---

## 12. Dependency policy

Before adding a dependency, determine:

- necessity;
- license;
- maintenance status;
- Python compatibility;
- whether the standard library or current dependencies suffice;
- impact on installation and CI.

Do not add a large dependency solely for a small helper function without documenting the trade-off.

Lock files may be added only when the project has selected a dependency-management strategy.

---

## 13. Git policy

Default branch:

```text
main
```

For substantial updates, prefer:

```text
agent/sync-vX.Y.Z
```

Commit style:

```text
feat: add data statistics and replication pipeline v0.4
fix: repair batch manifest serialization
docs: add local agent synchronization protocol
test: cover dataset validation failures
```

Before commit:

```bash
git diff --check
git diff --stat
git status --short
```

Stage only intended files.

After commit:

```bash
git show --stat --oneline HEAD
git push -u origin <branch>
```

Do not use `--force` or `--force-with-lease` without explicit authorization.

When instructed to push directly to `main`, first ensure:

- the worktree contains only the intended release;
- all mandatory checks pass;
- remote `main` has not advanced unexpectedly.

---

## 14. Conflict policy

When local and remote changes conflict:

1. Fetch remote state.
2. Identify whether both sides contain meaningful work.
3. Preserve both versions.
4. Resolve semantically, not merely textually.
5. Rerun every validation gate.
6. Report each resolved file.

Never choose “ours” or “theirs” globally without inspection.

If the conflict changes theoretical meaning or evidence semantics, stop for approval.

---

## 15. Secret and privacy policy

Never commit:

```text
.env
API tokens
GitHub tokens
SSH private keys
cloud credentials
private datasets
personal identifiers not intended for publication
local absolute paths containing sensitive information
```

Scan staged changes before commit.

At minimum:

```bash
git diff --cached
```

If a secret may have entered Git history, stop immediately and report it. Do not merely delete it in a later commit.

---

## 16. Artifact policy

Generated research outputs are untracked by default unless the task explicitly requests tracked examples.

Separate:

```text
Source code
Configuration
Small reproducible fixtures
Documentation
```

from:

```text
Large generated figures
Large CSV outputs
Temporary evidence bundles
Caches
Virtual environments
```

If an example artifact is tracked, it must be small, deterministic, and documented.

---

## 17. Remote verification

After pushing, verify that the expected commit exists remotely.

Preferred:

```bash
git fetch origin
git rev-parse HEAD
git rev-parse origin/<branch>
```

Success requires matching SHAs unless a server-side process legitimately added a new commit.

Also verify key files from the remote state where practical.

---

## 18. Completion report

After every synchronization, output both:

1. a human-readable summary;
2. a machine-readable JSON report following `SYNC_REPORT_TEMPLATE.json`.

The human summary must include:

```text
Repository
Source version
Target version
Branch
Commit SHA
Push result
Tests
Lint
Example runs
Files changed
Autonomous fixes
Warnings
Remaining actions
```

Never claim success if push or remote verification failed.

---

## 19. Failure report

When blocked, report:

- exact stage;
- exact command;
- exit code;
- concise error;
- files already modified;
- whether rollback is needed;
- safest next action.

Do not repeatedly retry authentication, destructive operations, or failing patches without changing the conditions.

---

## 20. Standard invocation for a local Agent

Use this prompt when assigning a FELRA synchronization task:

```text
Read the repository-root AGENTS.md and follow it as the controlling execution protocol.

Synchronize the supplied FELRA release into the local repository:
https://github.com/kakon77777-commits/FELRA

Input:
<path to release bundle, patch, script, or handoff document>

Requirements:
1. Perform preflight and version detection.
2. Preserve unrelated local work.
3. Verify supplied checksums when available.
4. Apply the update safely.
5. Run all mandatory validation gates and version-appropriate example workflows.
6. Inspect the final diff.
7. Commit and push only intended changes.
8. Verify the remote commit.
9. Return both a human-readable summary and a JSON report conforming to SYNC_REPORT_TEMPLATE.json.

Do not force-push, rewrite history, delete user work, weaken scientific claims, or publish externally without explicit approval.
```

---

## 21. Definition of done

A FELRA synchronization task is done only when all applicable conditions are true:

- [ ] Correct repository verified.
- [ ] Remote changes fetched.
- [ ] Working tree policy satisfied.
- [ ] Incoming version identified.
- [ ] Checksums verified where supplied.
- [ ] Safety point created where appropriate.
- [ ] Update applied.
- [ ] Version declarations consistent.
- [ ] Tests passed.
- [ ] Lint passed or accurately reported unavailable.
- [ ] Required examples passed.
- [ ] Diff inspected.
- [ ] No secrets staged.
- [ ] Commit created.
- [ ] Push succeeded.
- [ ] Remote commit verified.
- [ ] Human report produced.
- [ ] JSON report produced.

If any required item is false, report the synchronization as incomplete.

---

## 22. Archive filename portability policy

All file and directory paths stored inside distributed ZIP archives must be ASCII-safe.

Allowed archive-path character set:

```text
A-Z a-z 0-9 . _ - /
```

Human-facing document titles and contents may remain Chinese or multilingual, but their physical archive paths must use an ASCII language marker such as `zh-TW`.

Example:

```text
Logical historical title:
docs/GCPR-RWL-FELRA_技術白皮書_v1.0.md

Portable physical archive path:
docs/GCPR-RWL-FELRA_Technical_Whitepaper_zh-TW_v1.0.md
```

Every renamed historical path must be declared in:

```text
ARCHIVE_FILENAME_MAP.json
```

When synchronizing a full source archive, the local Agent must:

1. read `ARCHIVE_FILENAME_MAP.json`;
2. copy the ASCII-safe physical path;
3. remove a tracked legacy path only when the mapping explicitly names it;
4. preserve file contents and Git history semantics;
5. report every mapped rename.

Before publishing an archive, verify:

```text
Every ZIP member path is ASCII-only.
No mojibake member path exists.
The source extracts successfully with Windows Expand-Archive.
```

Do not reintroduce non-ASCII physical paths into release archives, even if the local filesystem and Git support them.
---

## 23. Preregistration and replay integrity

When a project enables preregistration:

- never replace an existing preregistration record without explicit approval;
- treat `strict` mismatches as a blocking scientific-plan change;
- retain `preregistration_verification.json` in the evidence output;
- do not edit a plan merely to force its fingerprint to match;
- create a new preregistration record when an approved analysis plan changes.

For release validation of v0.7 or later, run the reproducibility example and require:

```text
preregistration status = matched
felra replay result = MATCH
paper export manifest produced
all provenance paths present
```

A matching replay fingerprint shows computational reproduction of the stored result payload. It does not establish scientific validity, external replication, or universal proof.

