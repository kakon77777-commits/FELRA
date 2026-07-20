# FELRA v0.8.0 Release Notes

## Theme

V2 symbolic verification — the first of three remaining gaps toward v1.0.0.

## Added

- `symbolic` analysis type: `check: equivalence` (exact algebraic identity via
  SymPy simplification) and `check: derivative` (exact symbolic
  differentiation compared against a declared closed form);
- per-variable symbolic assumptions (`real`, `positive`, `negative`,
  `nonnegative`, `nonpositive`, `nonzero`, `integer`, `rational`, `complex`);
- a safe AST-based symbolic expression parser (`felra.symbolic`), separate
  from and narrower than the existing numeric expression evaluator;
- v0.8 JSON Schema and a symbolic-verification example project.

## Path to v1.0.0

FELRA v1.0.0 is defined as completion of the whitepaper's implementation
roadmap stage 2 (full Python-first global verification orchestration,
channels V0-V8; see `docs/GCPR-RWL-FELRA_Technical_Whitepaper_zh-TW_v1.0.md`
section 15). Stage 3 onward (FELRA-Spec clause promotion, SMT/Lean backends,
RWL projection, the eight operators) is out of scope for v1.0.0 and tracked
as post-1.0 work.

Gap status after v0.8.0:

- V2 symbolic verification — done (this release);
- V3 numerical soundness (conditioning, overflow, precision loss) — not yet
  implemented, planned for v0.9.0;
- V8 cross-method consistency (same claim checked by two independent
  methods) — not yet implemented, planned for v1.0.0 alongside final
  stage-2 documentation.

## Scientific interpretation

A symbolic equivalence result is a claim about the expressions under the
*declared* assumptions only — an unconstrained variable defaults to `real`,
not to whatever domain a reader might assume from context. Changing the
declared assumptions can change the result (this is demonstrated
deliberately in `examples/symbolic/project.yaml`, not an inconsistency).
