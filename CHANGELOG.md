# Changelog

## 0.9.0 — 2026-07-20

- Added `numerical_soundness` analysis type (V3 numerical soundness): overflow/NaN detection, exact-derivative condition-number estimation, and float64-vs-arbitrary-precision (mpmath) catastrophic-cancellation detection, all driven from a single symbolic parse of the expression (reuses `felra.symbolic` from v0.8).
- Added `mpmath` as an explicit dependency (previously only a transitive dependency of sympy).
- Added v0.9 schema, a numerical-soundness example with three worked cases (well-conditioned control, a real pole, and textbook catastrophic cancellation in `(1-cos(x))/x**2`), documentation, and 5 regression tests.
- Second step toward FELRA v1.0.0. Remaining gap: V8 cross-method consistency.

## 0.8.0 — 2026-07-20

- Added `symbolic` analysis type (V2 symbolic verification): exact algebraic-equivalence and derivative checks via SymPy, complementing the existing sampling-based residual/sensitivity/counterexample channels.
- Added per-variable symbolic assumptions (`real`, `positive`, `negative`, `nonnegative`, `nonpositive`, `nonzero`, `integer`, `rational`, `complex`); unassumed variables default to `real`.
- Added a safe AST-based symbolic expression parser (`felra.symbolic`), mirroring the existing numeric expression evaluator's whitelist approach — no `sympify`/`eval` on raw strings.
- Added v0.8 schema, symbolic-verification example, documentation, and 7 regression tests.
- First step toward FELRA v1.0.0 (defined as: full Python-first global verification orchestration, V0-V8, per `docs/GCPR-RWL-FELRA_Technical_Whitepaper_zh-TW_v1.0.md` section 15 stage 2). Remaining gaps: V3 numerical soundness, V8 cross-method consistency.

## 0.7.0 — 2026-07-14

- Added immutable scientific-plan preregistration with warning and strict enforcement modes.
- Added canonical plan SHA-256 fingerprints that exclude operational cache and registry settings.
- Added JSON, Graphviz DOT, and portable SVG evidence-provenance graphs.
- Added normalized-data replay projects and stable scientific-result SHA-256 fingerprints.
- Added `felra replay` for independent result-fingerprint reproduction checks.
- Added `felra export` for paper-ready Methods, Results, Limitations, CITATION, figures, reports, and file hashes.
- Added v0.7 schema, strict preregistration example, documentation, and 33 regression tests.

## 0.6.0 — 2026-07-14

- Added Bonferroni, Holm, and Benjamini–Hochberg correction for declared comparison families.
- Added named standardized effect sizes for parametric, rank-based, and correlation tests.
- Added leakage-aware numeric regression cross-validation with out-of-fold predictions.
- Added shared-fold linear and polynomial model comparison with RMSE, MAE, and R² ranking.
- Added an append-only JSONL experiment registry and `felra registry` inspection command.
- Added v0.6 schema, documentation, synthetic research example, and 30 regression tests.

## 0.5.0 — 2026-07-14

- Added CSV, JSON, JSONL, and transparent gzip dataset readers under one typed data contract.
- Added noncentral-t power analysis for one-sample, paired, and independent-samples designs.
- Added Fisher-z approximate power analysis for correlation designs.
- Added bootstrap and subsample robustness analyses for means, medians, standard deviations, correlations, and group mean differences.
- Added sign stability, relative dispersion, percentile intervals, and full resampling distributions.
- Added content-addressed per-analysis caching keyed by FELRA version, analysis spec, project config, dataset hashes, and execution seed.
- Added cache provenance to analysis metrics and project manifests.
- Added root-level local Agent synchronization protocol and structured handoff/report templates.
- Added v0.5 examples, schemas, documentation, and 26 regression tests.

## 0.4.0 — 2026-07-14

- Added typed external CSV datasets with deterministic normalization and source SHA-256.
- Added missing, invalid, dropped, and duplicate-row data-quality evidence.
- Added dataset-row claims over the full normalized dataset.
- Added grouped descriptive statistics and Student-t mean confidence intervals.
- Added one-sample, Welch/independent, paired, Mann-Whitney, Wilcoxon, Pearson, and Spearman tests.
- Added reproducible percentile bootstrap confidence intervals and distributions.
- Added repeated experiment expansion, seed schedules, process-parallel batch execution, and replicate aggregation.
- Added data/statistics examples, v0.4 schemas, documentation, and 20 regression tests.

## 0.3.0 — 2026-07-14

- Added local finite-difference sensitivity analysis with normalized ranking.
- Added residual analysis with MAE, RMSE, bias, dispersion, and residual figures.
- Added one-, two-, and high-dimensional parameter sweeps with best-point extraction.
- Added exact two-objective Pareto-frontier detection for finite candidate sets.
- Added analysis-level CSV, JSON, Markdown, and figure evidence bundles.
- Added `felra batch` with reproducible dot-path overrides and aggregate reports.
- Added advanced and batch example projects.
- Added project and batch JSON Schemas for v0.3.
- Added analysis-aware project manifests and claim-linked analysis figures.
- Expanded the automated test suite to 13 tests.

## 0.2.0 — 2026-07-14

- Added executable `project.yaml` specifications.
- Added safe AST-based numerical expression evaluation.
- Added multidimensional declared-grid, boundary, and random counterexample sampling.
- Added the `felra run` command and project-level Evidence Bundles.
- Added line, scatter, histogram, heatmap, contour, and phase-map figures.
- Added configuration snapshots, SHA-256 fingerprints, environment metadata, and aggregate reports.
- Added one- and two-parameter example projects and expanded tests.

## 0.1.0

- Initial Python-first research workbench MVP.
