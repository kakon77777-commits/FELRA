# FELRA Agent Handoff Template

Use this file for each new release or implementation task. Fill in the fields and give it to the local Agent together with the release bundle, source archive, patch, or implementation specification.

---

## Task identity

```yaml
task_id: FELRA-SYNC-YYYYMMDD-001
repository: https://github.com/kakon77777-commits/FELRA
expected_base_version:
target_version:
preferred_branch:
direct_push_to_main: false
```

## Input artifacts

```yaml
artifacts:
  - path:
    type: release_bundle | source_archive | patch | upgrade_script | specification
    sha256:
```

## Intended scope

Describe the exact release objective.

```text
Example:
Upgrade FELRA from v0.4.0 to v0.5.0.
Add external dataset adapters, statistical power analysis, and experiment caching.
Preserve all v0.1–v0.4 public behavior unless the release notes explicitly state otherwise.
```

## Required validation

```yaml
checks:
  - python -m compileall src tests
  - pytest
  - ruff check src tests

examples:
  - felra run examples/basic/project.yaml --output artifacts/basic
  - felra run examples/advanced/project.yaml --output artifacts/advanced
  - felra run examples/data/project.yaml --output artifacts/data
  - felra batch examples/batch/batch.yaml --output artifacts/batch
```

## Allowed autonomous fixes

```yaml
allowed:
  - packaging errors
  - missing imports
  - path portability
  - lint failures
  - deterministic test repairs consistent with release intent
  - version-string synchronization
```

## Approval boundaries

```yaml
approval_required:
  - public API removal
  - scientific-claim changes
  - validation-threshold reductions
  - new telemetry
  - new cloud services
  - force push
  - repository visibility changes
  - license changes
  - publication or PyPI release
```

## Commit

```yaml
commit_message:
```

## Expected report

The Agent must return:

1. A concise human-readable synchronization summary.
2. A JSON object valid against `SYNC_REPORT_TEMPLATE.json`.
3. Exact details for any failed or unavailable validation.
4. The remote commit SHA after verification.
