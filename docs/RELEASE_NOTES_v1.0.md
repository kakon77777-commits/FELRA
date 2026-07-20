# FELRA v1.0.0 Release Notes

## Theme

V8 cross-method consistency, and completion of the whitepaper's
implementation-roadmap stage 2.

## What "v1.0.0" means here

Per `docs/GCPR-RWL-FELRA_Technical_Whitepaper_zh-TW_v1.0.md` section 15,
stage 2 ("全域驗證編排與大量圖形生成") is the full Python-first global
verification orchestration channel set V0-V8 (section 9.4) plus the Figure
Factory. FELRA's package version reaching 1.0.0 means *that* is complete —
not that stage 3 onward (FELRA-Spec clause promotion, SMT/Lean formal
backends, RWL projection, the eight operators, dual memory) has started.
Those remain explicitly future work; a Python-first verification workbench
is already a complete, independently useful tool without them.

This distinction matters because the whitepaper document itself is
separately versioned "v1.0" (its own naming, referring to the Python-first
pivot from the original GCPR-RWL-Axiom architecture) — the document's
version and the package's version are two different counters that happen
to share the digits "1.0" by coincidence, not because one caused the other.

## Added

- `cross_method` analysis type: `numeric` / `symbolic` / `high_precision`
  backends for independently-formulated or independently-evaluated methods
  of the same quantity, with pairwise agreement reporting;
- v1.0 JSON Schema and a cross-method-consistency example with two real
  cases (a trig-identity agreement check, and a genuine naive-vs-simplified
  disagreement at a removable singularity).

## Scientific interpretation

Agreement between methods within the declared `tolerance` is evidence that
the declared formulations are numerically consistent under the tested
domain and precision — not a proof that either method is mathematically
correct (two methods can share the same bug). Disagreement is a genuine
finding, not necessarily an error: which method (if either) is "right"
still requires domain judgment, exactly as `nonfinite_mismatch` in this
release's own example shows (the naive formula isn't *wrong* at x=1 — the
underlying mathematical quantity really is undefined there in that
formulation; the simplified formula answers a subtly different, if
equivalent-almost-everywhere, question).
