# FELRA v0.9.0 Release Notes

## Theme

V3 numerical soundness — the second of three defined steps toward v1.0.0.

## Added

- `numerical_soundness` analysis type: overflow/NaN detection, exact-
  derivative condition-number estimation, and float64-vs-arbitrary-
  precision (mpmath) catastrophic-cancellation detection;
- `mpmath` promoted from a transitive (sympy) dependency to an explicit one;
- v0.9 JSON Schema and a numerical-soundness example with three real worked
  cases: a well-conditioned control, a genuine pole at `1/(x-1)`, and
  textbook catastrophic cancellation in `(1-cos(x))/x**2`.

## Path to v1.0.0

Gap status after v0.9.0:

- V2 symbolic verification — done (v0.8.0);
- V3 numerical soundness — done (this release);
- V8 cross-method consistency (same claim checked by two independent
  methods) — not yet implemented, planned for v1.0.0 alongside final
  stage-2 documentation and README/whitepaper sign-off.

## Scientific interpretation

A condition-number or precision-loss report describes numerical behavior
*at the sampled points, under this implementation's specific evaluation
path* (SymPy's `lambdify` to numpy for float64, to `mpmath` for the
high-precision reference) — it is evidence that a specific computational
approach is numerically fragile in a region, not a claim that every
possible implementation of the same mathematical expression would fail the
same way. `singular` points (where `f(x)` is exactly zero) are reported
separately from `ill_conditioned` ones precisely because "the condition
number is undefined here" and "the condition number is large here" are
different findings.
