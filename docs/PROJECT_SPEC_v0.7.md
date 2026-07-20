# FELRA Project Specification v0.7

v0.7 extends v0.6 with the optional root-level `preregistration` object.

```yaml
preregistration:
  enabled: true
  path: preregistration.json
  mode: strict
```

Fields:

- `enabled`: activate verification during `felra run`;
- `path`: JSON preregistration record, resolved relative to `project.yaml`;
- `mode`: `warn` or `strict`.

Commands:

```bash
felra preregister project.yaml --output preregistration.json
felra verify-preregistration project.yaml --record preregistration.json
felra run project.yaml --output artifacts/run
felra replay artifacts/run --output artifacts/replay
felra export artifacts/run --output artifacts/paper-bundle
```

Every successful v0.7 run writes:

```text
manifest.json
project_snapshot.yaml
replay_project.yaml
provenance/provenance.json
provenance/provenance.dot
provenance/provenance.svg
```

When preregistration is enabled it also writes:

```text
preregistration_verification.json
```
