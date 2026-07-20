# FELRA Project Specification v0.9

v0.9 extends v0.8 with a new `numerical_soundness` analysis type — V3
numerical soundness (overflow/NaN, condition number, and float64-vs-
arbitrary-precision catastrophic-cancellation detection), schema
`schema/project-v0.9.schema.json`.

```yaml
analyses:
  - id: cancellation
    type: numerical_soundness
    expression: (1 - cos(x)) / x ** 2
    parameters: [x]
    precision_digits: 30
    relative_error_threshold: 1.0e-6
```

## What it checks

A single symbolic parse of `expression` (the same safe parser V2 symbolic
verification uses, `felra.symbolic`) drives all three checks from one
source of truth:

1. **Overflow / NaN** — a fast numpy-vectorized evaluation over the
   declared domain (built from `project.parameters`, same sampling as
   `sensitivity`/`residual`), checked for non-finite output.
2. **Condition number** — the *exact* symbolic derivative (not a
   finite-difference estimate) gives the classic scalar relative condition
   number `kappa_i(x) = |x_i * df/dx_i / f(x)|` at every sample point; the
   maximum over the declared parameters is reported per point.
3. **Precision loss** — the float64 evaluation is compared against an
   arbitrary-precision (`mpmath`) reference on a bounded subset of points
   (`precision_sample_limit`, default 200 — arbitrary-precision evaluation
   cannot be vectorized the way numpy can, so it is explicitly budgeted,
   not silently applied to every sample).

Points where `f(x)` is finite but exactly zero are reported separately as
`singular`, not folded into the condition-number statistics (division by
zero there is undefined, not merely large) and excluded from the
precision-loss check for the same reason.

## Fields

- `expression`: required, parsed with the same grammar as `symbolic`
  (arithmetic + the approved function whitelist — no comparisons, Boolean
  logic, or conditionals, since those aren't differentiable);
- `parameters`: required, non-empty, must be declared in the project's
  `parameters` block — these are both the sampling domain and the
  variables condition number is computed with respect to;
- `precision_digits` (default 30, minimum 15 — float64 already carries
  ~15-17 significant digits, so anything less wouldn't be a meaningful
  reference);
- `precision_sample_limit` (default 200);
- `condition_threshold` (default `1e6`) — points above this are reported
  `ill_conditioned`;
- `relative_error_threshold` (default `1e-6`) — points above this
  (checked only among the `precision_sample_limit` sampled points) are
  reported `precision_loss`.

## Relationship to V2 symbolic verification

`numerical_soundness` is not a new independent parser — it reuses
`felra.symbolic.parse_symbolic_expression` and `sympy.diff` directly, so
the condition number is computed from the exact derivative V2 already
knows how to take, evaluated at real sampled points rather than compared
against a declared closed form. The three worked cases in
`examples/numerical_soundness/project.yaml` are deliberately real, not
illustrative: a genuine pole (`1/(x-1)`) and a textbook catastrophic-
cancellation case (`(1-cos(x))/x**2` for `x` as small as `1e-10`, where
float64 computes exactly `0.0` against a true value of `0.5`).
