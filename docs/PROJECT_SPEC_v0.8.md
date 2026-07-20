# FELRA Project Specification v0.8

v0.8 extends v0.7 with a new `symbolic` analysis type — V2 symbolic
verification (exact algebraic equivalence and derivative checks via SymPy),
schema `schema/project-v0.8.schema.json`.

## Equivalence check

```yaml
analyses:
  - id: sqrt_square_positive
    type: symbolic
    check: equivalence
    variables: [x]
    assumptions:
      x: [positive]
    lhs: sqrt(x ** 2)
    rhs: x
```

Simplifies `lhs - rhs` with SymPy under the declared assumptions and reports
whether the result is identically zero.

## Derivative check

```yaml
analyses:
  - id: cubic_derivative
    type: symbolic
    check: derivative
    variables: [x]
    expression: x ** 3 + 2 * x
    with_respect_to: x
    expected_derivative: 3 * x ** 2 + 2
```

Computes the exact SymPy derivative of `expression` with respect to
`with_respect_to` and compares it (via simplification) against
`expected_derivative`.

## Fields

- `check`: `equivalence` or `derivative`;
- `variables`: declared symbol names (required, non-empty);
- `assumptions`: optional mapping of variable name to one or more of `real`,
  `positive`, `negative`, `nonnegative`, `nonpositive`, `nonzero`, `integer`,
  `rational`, `complex`; a variable with no declared assumption defaults to
  `real`;
- `lhs` / `rhs`: required when `check: equivalence`;
- `expression` / `with_respect_to` / `expected_derivative`: required when
  `check: derivative`; `with_respect_to` must be one of the declared
  `variables`.

## Expression grammar

Symbolic expressions are parsed by `felra.symbolic.parse_symbolic_expression`,
a safe AST-walking parser — never `sympy.sympify` or `eval` on raw input.
Supported: `+ - * / **`, the constants `pi` and `e`, and the function
whitelist `abs sqrt exp log sin cos tan asin acos atan sinh cosh tanh`.
Comparisons, Boolean logic, and conditionals are rejected — they are not
meaningful for symbolic algebra and are the numeric evaluator's job (see
`felra.expressions`), not this module's.

## Relationship to sampling-based channels

`symbolic` analyses make a *stronger and narrower* claim than
`residual` / `sensitivity` / a claim's `counterexample_search`: those find
(or fail to find) a mismatch at sampled points within a declared numeric
domain; a symbolic equivalence check either proves the two expressions
identical everywhere the declared assumptions hold, or reports the
simplified (generally nonzero) difference. Neither replaces the other —
`examples/symbolic/project.yaml` runs both channels against the same
question (`sqrt(x**2) == x`) precisely to show them agreeing.
