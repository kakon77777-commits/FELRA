# FELRA v0.5.0 Release Notes

**Release date:** 2026-07-14  
**Theme:** Statistical Power, Resampling Robustness, Dataset Adapters, and Content-Addressed Cache

## Highlights

FELRA v0.5 adds prospective and achieved statistical power analysis, resampling-based robustness diagnostics, JSON/JSONL dataset adapters, transparent gzip reading, and deterministic per-analysis caching.

## New analysis types

### `power`

Supported designs:

- `one_sample_t`;
- `paired_t`;
- `independent_t`;
- `correlation`.

The t-test designs use noncentral t distributions. Correlation uses a Fisher-z normal approximation. The analysis can search for the minimum sample size meeting `target_power`, report power at a fixed `sample_size`, or do both.

### `robustness`

Supported statistics:

- mean;
- median;
- standard deviation;
- correlation;
- two-group mean difference.

Supported resampling methods:

- bootstrap with replacement;
- fixed-fraction subsampling without replacement.

Outputs include the full resampling distribution, percentile interval, sign stability, relative dispersion, and failed-resample count.

## Dataset formats

The same typed column contract now accepts:

- CSV;
- JSON containing a top-level list of objects;
- JSON Lines containing one object per non-empty line.

Any supported format can be gzip-compressed when the filename ends in `.gz`.

## Analysis cache

Enable with:

```yaml
execution:
  cache: true
  cache_dir: .felra-cache
  refresh_cache: false
```

The cache key includes the FELRA version, full analysis specification, project configuration, source dataset hashes, and execution seed. Cache provenance is written into each analysis metrics file and the project manifest.

## Local Agent synchronization

The repository now includes:

- `AGENTS.md`;
- `AGENT_HANDOFF_TEMPLATE.md`;
- `SYNC_REPORT_TEMPLATE.json`.

These files define the safe local synchronization workflow, test gates, Git policy, scientific integrity boundaries, and structured completion report.

## Compatibility

FELRA v0.5 preserves v0.1-v0.4 project and batch behavior. Existing CSV projects require no migration.

## Validation completed

- `pytest`: 26 passed;
- `ruff check src tests`: passed;
- `python -m compileall -q src tests`: passed;
- project v0.5 JSON Schema validation: passed;
- basic example: passed;
- advanced analysis example: passed;
- v0.4 data/statistics example: passed;
- repeated parallel batch example: passed;
- v0.5 robustness/power example: passed;
- second identical v0.5 run: all three analyses restored from cache with matching fingerprints.

## Demonstration result

For the synthetic v0.5 independent-samples example with assumed standardized effect size $d=0.6$, two-sided $\alpha=0.05$, equal allocation, and target power $0.8$, FELRA reports:

$$
n_1=n_2=45,
\qquad
\operatorname{Power}\approx0.8037.
$$

This is a design calculation under the declared assumptions, not an empirical clinical result.

## Known limits

- Power analysis currently covers four common designs, not arbitrary generalized linear models or clustered designs.
- Correlation power is an approximation based on Fisher's transformation.
- Resampling stability does not correct bias, confounding, measurement error, or nonrepresentative sampling.
- The cache is local and content-addressed; distributed cache coordination is not included.
- Parquet, Excel, SQL, and remote dataset connectors are not included in v0.5.
