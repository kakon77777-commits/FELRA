# FELRA Project Specification v0.5

## Execution cache

```yaml
execution:
  seed: 2026
  cache: true
  cache_dir: .felra-cache
  refresh_cache: false
```

`cache_dir` is resolved relative to the project file unless absolute.

## Dataset formats

```yaml
datasets:
  records:
    path: data/records.jsonl
    format: jsonl        # csv | json | jsonl
    encoding: utf-8
    on_error: drop       # drop | error | keep
    columns:
      id: str
      group: str
      score: float
```

JSON files require a list of objects. JSONL files require one object per line. `.gz` files are supported.

## Power analysis

```yaml
analyses:
  - id: independent_t_power
    type: power
    title: Independent-samples power curve
    test: independent_t       # one_sample_t | paired_t | independent_t | correlation
    effect_size: 0.6
    alpha: 0.05
    target_power: 0.8
    alternative: two-sided    # two-sided | less | greater
    allocation_ratio: 1.0
    max_sample_size: 500
```

Use `sample_size` instead of or in addition to `target_power` to report achieved power at a fixed size.

For `independent_t`, `sample_size` and the required sample size refer to group 1; group 2 is determined by `allocation_ratio`.

## Robustness analysis

```yaml
  - id: treatment_effect_robustness
    type: robustness
    dataset: records
    statistic: mean_difference
    columns: [score]
    group_by: group
    groups: [control, treatment]
    method: bootstrap          # bootstrap | subsample
    repetitions: 2000
    fraction: 0.8              # used by subsample
    confidence: 0.95
    seed: 305
    bins: 40
```

Other valid statistics:

```text
mean
median
std
correlation
```

`correlation` requires exactly two columns. `mean_difference` uses the second declared group's mean minus the first group's mean.
