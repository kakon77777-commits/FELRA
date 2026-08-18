# Changelog

## 1.1.0 — 2026-08-18

FELRA v1.1.0 — the first slice of the whitepaper's implementation roadmap stage 4
(`docs/GCPR-RWL-FELRA_Technical_Whitepaper_zh-TW_v1.0.md` section 15,
"正式驗證後端"): external formal checkers, invoked but never depended on, with
their verdicts recorded beside the Python evidence rather than merged into it.

### Added

- **`formal_check` analysis type.** Invokes an external formal checker on a
  declared obligation and reports its verdict separately from FELRA's own
  pipeline flag. This implements the stage-4 requirement
  「將 Python 證據狀態與正式證明狀態分開標記」.
- **`felra.formal`** — a *closed* set of adapters (`lean`, `tlc`, `z3`). A project
  declares which adapter and what obligation; it never supplies a command to run.
  An unknown backend is refused rather than guessed at.
- **Four-valued formal status** — `verified`, `refuted`, `unknown`,
  `unavailable`. `unknown` (the checker ran and did not decide) and `unavailable`
  (the checker did not run) are distinct on purpose: collapsing them is how a
  missing tool becomes an implicit pass. A project declaring `expect: verified`
  **fails** on a machine where the checker is absent.
- **Verification certificates.** Every run records which program ran (backend,
  command, resolved path, version string, and the SHA-256 of the executable or
  archive that decided), what was checked (obligation path, SHA-256, size), what
  the verdict rests on (`assumptions`, `limitations`), and where the obligation
  came from (`derives_from`).
- **`docs/FORMAL_BACKENDS.md`** — a permanent register of every backend: what
  program it invokes, when it was added, and what real artifact it was validated
  against. Adding a backend without a register entry is a defect.
- **`examples/formal_check/`** — a self-contained TLA+ model plus a project
  demonstrating both a real check and the `unavailable` path. Environment-dependent
  by nature, so deliberately **not** part of the mandatory gate set in
  `AGENTS.md` section 8.
- `tests/test_v11.py` — 12 tests, none of which require a checker to be installed.

### Scope notes

- **No dependency was added.** FELRA does not ship, download, or require any
  solver or proof assistant. `tla2tools.jar` in particular is never fetched; its
  path is declared by the project.
- **No existing result changed meaning.** `success` keeps its pipeline semantics
  everywhere. `AGENTS.md` section 11 lists changing the meaning of "pass" or
  "proof" as requiring approval; adding a *separate* status alongside is what
  avoids being that change.
- **`z3`'s `unsat`/`sat` mapping has not been exercised against a real solver** —
  z3 is not installed on the machine where this slice was written. Only its
  `unavailable` path is tested. Recorded in the register rather than glossed.

### Fixed

- A path bug in the formal adapter, found by running a real checker rather than a
  mock. The obligation was resolved against the caller's working directory and the
  subprocess's directory was then set to the obligation's own parent, so the path
  was consumed twice. TLC's resulting "file not found" exit was nearly recorded as
  a refutation of a model it had in fact checked cleanly. Paths are absolute before
  invocation now, and a clean transcript with a non-zero exit is reported as
  `unknown` with the disagreement stated rather than resolved in either direction.

## 1.0.0 — 2026-07-20

FELRA v1.0.0 — completion of the whitepaper's implementation roadmap stage 2
(`docs/GCPR-RWL-FELRA_Technical_Whitepaper_zh-TW_v1.0.md` section 15:
"全域驗證編排與大量圖形生成"), defined as the full Python-first global
verification orchestration channel set V0-V8 (section 9.4) plus the Figure
Factory. Stage 3 onward (FELRA-Spec clause promotion, SMT/Lean backends, RWL
projection, the eight operators, dual memory) is explicitly out of scope for
1.0.0 and left for future versions.

- Added `cross_method` analysis type (V8 cross-method consistency): declares
  two or more independently-formulated or independently-evaluated methods
  (`numeric` via `felra.expressions`, `symbolic` via `felra.symbolic`, or
  `high_precision` via mpmath) for the same quantity and reports pairwise
  agreement — distinct from V3 numerical soundness, which checks a single
  fixed formula's own conditioning, not whether alternative formulations
  agree with it.
- Added v1.0 schema and a cross-method-consistency example with two real
  cases: independent-evaluator agreement on a trig identity, and a genuine
  disagreement between a naive formula and its algebraic simplification at
  a removable singularity (demonstrating that arbitrary precision alone
  does not resolve a literal 0/0 — only a different method does).
- 6 new regression tests (58 total across v0.1-1.0.0).

### V0-V8 status at v1.0.0

| Channel | Status | Since |
|---|---|---|
| V0 reproducibility & environment | done | v0.1 |
| V1 structural validation | done | v0.1 |
| V2 symbolic verification | done | v0.8.0 |
| V3 numerical soundness | done | v0.9.0 |
| V4 property/invariant checks | partial (claim expressions over sampled domains; no Hypothesis-style property-based test generator) | v0.1 |
| V5 boundary & counterexample search | done | v0.1-v0.2 |
| V6 statistics & uncertainty | done | v0.4-v0.6 |
| V7 sensitivity & global search | done | v0.3 |
| V8 cross-method consistency | done | 1.0.0 |
| V9 formal/external verification | explicitly out of scope for 1.0.0 — stage 3+ | — |

V4 is intentionally left "partial" rather than claimed done: FELRA's claim
expressions already check declared properties across sampled/exhaustive
domains (the same mechanism used throughout V0-V8), which satisfies the
whitepaper's V4 description in substance; a dedicated Hypothesis-style
property-based test *generator* was never built and is not required to
call stage 2 complete.

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
