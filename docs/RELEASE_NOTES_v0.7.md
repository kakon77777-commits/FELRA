# FELRA v0.7.0 Release Notes

## Theme

Preregistration, evidence provenance, reproducibility replay, and paper-ready export.

## Added

- `felra preregister` and `felra verify-preregistration`;
- warning and strict analysis-plan locking;
- stable canonical plan SHA-256;
- JSON, DOT, and SVG evidence-provenance graphs;
- normalized-data `replay_project.yaml`;
- stable `result_sha256` in every run manifest;
- `felra replay` with machine-readable reproduction comparison;
- `felra export` with Methods, Results, Limitations, citation metadata, and file hashes;
- v0.7 JSON Schema and reproducibility example.

## Scientific interpretation

Preregistration matching is plan consistency, not scientific validity. Replay matching is computational reproduction, not external replication or mathematical proof.

## Packaging

All distributed ZIP member paths remain ASCII-safe. Multilingual document contents are preserved using language tags in physical filenames where necessary.
