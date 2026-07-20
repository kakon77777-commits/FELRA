# FELRA v0.5 — Statistical Power, Robustness and Content-Addressed Cache

## 1. Purpose

FELRA v0.5 adds three academic workflow capabilities:

1. prospective or achieved statistical power analysis;
2. resampling-based robustness analysis;
3. content-addressed reuse of deterministic analysis evidence.

It also expands the external dataset layer from CSV to CSV, JSON, and JSON Lines.

## 2. Statistical power

A power analysis asks whether a planned or observed sample size is sufficient to detect an assumed effect under a declared test, significance level, and alternative.

For a one-sample or paired $t$ test, FELRA uses a noncentral $t$ distribution with

$$
\delta=d\sqrt{n}.
$$

For a balanced or unbalanced independent-samples $t$ test,

$$
\delta=\frac{d}{\sqrt{1/n_1+1/n_2}}.
$$

For correlation, FELRA uses a Fisher-$z$ normal approximation. These are design calculations under model assumptions, not guarantees that a future study will produce a significant result.

## 3. Robustness analysis

The `robustness` analysis repeatedly resamples a declared dataset and recalculates a statistic. Supported statistics are:

- `mean`;
- `median`;
- `std`;
- `correlation`;
- `mean_difference`.

Supported methods are:

- `bootstrap`: sample with replacement at the original usable sample size;
- `subsample`: sample without replacement at a declared fraction.

FELRA reports the observed estimate, resampling mean, dispersion, percentile interval, sign stability, failed resamples, and a complete replicate CSV.

The result describes stability under the chosen resampling scheme. It does not remove sampling bias, measurement error, confounding, or model misspecification.

## 4. Content-addressed analysis cache

When `execution.cache` is enabled, FELRA computes an analysis fingerprint from:

$$
H=
\operatorname{SHA256}
\left(
V_{\mathrm{FELRA}},
A_{\mathrm{spec}},
P_{\mathrm{project}},
H_{\mathrm{datasets}},
S_{\mathrm{seed}}
\right).
$$

A cached result is reused only when the complete fingerprint matches. Each analysis metrics file records:

```json
{
  "cache_hit": true,
  "cache_fingerprint": "..."
}
```

`refresh_cache: true` forces recomputation and replaces the matching cache entry after successful execution.

The cache is an optimization, not a source of authority. The copied evidence retains the original metrics, figures, reports, seeds, and source hashes.

## 5. Dataset adapters

v0.5 supports:

```yaml
format: csv
format: json
format: jsonl
```

JSON must contain a top-level list of objects. JSONL must contain one object per non-empty line. Files ending in `.gz` are read transparently for all three formats.

All formats pass through the same declared column contract and produce the same normalized CSV evidence.
