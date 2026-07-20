# FELRA v0.6.0 Release Notes

**Release date:** 2026-07-14  
**Theme:** Multiple Comparisons, Standardized Effects, Cross-Validation, Model Comparison, and Experiment Registry

## Highlights

FELRA v0.6 adds family-wise and false-discovery p-value corrections, richer standardized effect sizes, leakage-aware numerical cross-validation, shared-fold model comparison, and an append-only local research experiment registry.

## New analysis types

- `multiple_comparisons`: independent $t$ or Mann–Whitney pairwise comparisons with none, Bonferroni, Holm, or Benjamini–Hochberg correction.
- `cross_validation`: out-of-fold predictions for linear and per-feature polynomial least-squares models.
- `model_comparison`: fair comparison of multiple candidates on identical folds and seeds.

## Effect-size expansion

Hypothesis-test metrics now retain test-appropriate standardized effects rather than only one unnamed scalar. The legacy `effect_size` field remains for compatibility, while `effect_sizes` provides named measures.

## Experiment registry

Projects may append run records to a JSONL registry. Every registered run also writes `registry_record.json` into its output Evidence Bundle. `felra registry` supports basic project and pass/fail filtering.

## Compatibility

v0.6 preserves v0.1–v0.5 project behavior. Existing projects require no migration. The new registry is disabled by default.

## Known limits

- Cross-validation currently supports numeric regression and least-squares linear/polynomial models only.
- Polynomial features contain independent powers and no interaction terms.
- Model selection on the same folds is exploratory; nested cross-validation is not yet implemented.
- The registry is local append-only JSONL, not a cryptographic ledger or hosted experiment tracker.


## Packaging compatibility revision

The distributed source archive now uses ASCII-safe physical paths. The Traditional Chinese whitepaper is stored as `docs/GCPR-RWL-FELRA_Technical_Whitepaper_zh-TW_v1.0.md`; legacy path migration is declared in `ARCHIVE_FILENAME_MAP.json`.
