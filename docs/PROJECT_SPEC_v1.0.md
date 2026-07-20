# FELRA Project Specification v1.0

v1.0 extends v0.9 with a new `cross_method` analysis type — V8 cross-method
consistency, schema `schema/project-v1.0.schema.json`. This is the last of
the three gaps identified against the whitepaper's stage-2 checklist; see
`CHANGELOG.md`'s 1.0.0 entry for the full V0-V8 status table.

```yaml
analyses:
  - id: removable_singularity
    type: cross_method
    parameters: [x]
    tolerance: 1.0e-9
    methods:
      - name: naive_formula
        expression: (x ** 2 - 1) / (x - 1)
        backend: numeric
      - name: algebraically_simplified
        expression: x + 1
        backend: numeric
```

## What it checks

Declares two or more `methods` for the same quantity, evaluates all of them
over the same declared domain (`parameters`, sampled the same way as
`sensitivity`/`residual`/`numerical_soundness`), and reports pairwise
agreement. This answers a different question than V3 numerical soundness:
V3 asks whether *one fixed formula* is well-behaved (conditioning,
overflow, precision); V8 asks whether *different formulations or
evaluators* of the same mathematical quantity agree with each other. A
formula's own singularity is not automatically a V8 disagreement if every
declared method shares it — the example above's `naive_formula` also stays
undefined at arbitrary precision (`backend: high_precision`), because 0/0
is undefined regardless of precision; it *does* disagree with
`algebraically_simplified`, because that formulation has no singularity
there at all. That distinction — precision escalation doesn't fix a
literal indeterminate form, only a different method does — is the reason
V8 exists as separate from V3.

## Fields

- `parameters`: required, non-empty, must be declared in the project's
  `parameters` block — the shared sampling domain for every method;
- `methods`: required, at least two; each has:
  - `name` (required, unique within the analysis);
  - `expression` (required);
  - `backend` (default `numeric`): `numeric` evaluates via
    `felra.expressions` (the numpy AST-walking evaluator used everywhere
    else in FELRA — supports the full numeric function set, comparisons,
    `where`/`clip`); `symbolic` parses via `felra.symbolic` (the same safe
    parser V2 uses) then evaluates via SymPy's `lambdify` to numpy — a
    genuinely independent implementation of the same expression, catching
    parser-level bugs that agreement-with-itself can't; `high_precision`
    also parses via `felra.symbolic` but evaluates through `mpmath` at
    `precision_digits` (default 30), one point at a time (not
    numpy-vectorized — keep declared domains modest when using this
    backend);
- `tolerance` (default `1e-9`): the relative-difference threshold above
  which a pair of methods is reported as disagreeing at a point;
- `precision_digits` (default 30, minimum 15): only used by
  `high_precision`-backend methods.

## Output

For every pair of declared methods, `disagreement_count` (points where
both are finite but differ by more than `tolerance`, relatively) and
`nonfinite_mismatch_count` (points where exactly one method is finite and
the other is not — itself a disagreement, distinct from both agreeing that
a point is undefined) are reported separately, with up to 20 worked
examples per pair. The analysis succeeds only if every pair agrees
everywhere.
