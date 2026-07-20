# FELRA v0.7 — Preregistration, Provenance, Replay, and Paper Export

## 1. Purpose

FELRA v0.7 adds a research-governance layer above computation. Its goal is to distinguish:

1. the plan declared before execution;
2. the computation actually performed;
3. the evidence objects produced;
4. the result reproduced by an independent replay.

The complete chain is:

$$
\mathcal P_{	ext{plan}}
\xrightarrow{H_{	ext{plan}}}
	ext{Preregistration}
\xrightarrow{	ext{execute}}
	ext{Evidence DAG}
\xrightarrow{H_{	ext{result}}}
	ext{Run fingerprint}
\xrightarrow{	ext{replay}}
	ext{Reproduction comparison}.
$$

## 2. Scientific-plan fingerprint

FELRA canonicalizes the project plan and calculates:

$$
H_{	ext{plan}}
=
\operatorname{SHA256}
\left(
\operatorname{CanonicalJSON}(
P,D,C,A,S
)
\right),
$$

where $P$ is parameter declarations, $D$ dataset contracts, $C$ claims, $A$ analyses, and $S$ scientific execution settings such as random seeds and budgets.

Operational fields such as cache directories, cache refresh switches, Registry paths, and the preregistration configuration itself are excluded.

## 3. Enforcement modes

- `warn`: record a missing or mismatched preregistration and continue execution.
- `strict`: stop before computation when the record is missing or mismatched.

A fingerprint match establishes only that the current declared plan equals the locked plan. It does not establish that the plan is unbiased, adequate, ethical, or scientifically correct.

## 4. Provenance graph

Every run creates a directed evidence graph with nodes for:

- project configuration;
- normalized datasets;
- claims;
- analyses;
- generated artifacts and figures;
- final manifest.

It is exported as JSON, Graphviz DOT, and dependency-free SVG.

## 5. Result fingerprint

FELRA calculates a stable scientific result payload from normalized-data hashes, claim outcomes, counterexamples, and sanitized analysis metrics. Timestamps, cache hits, output paths, and Registry side effects are excluded.

$$
H_{	ext{result}}
=
\operatorname{SHA256}
\left(
D_{	ext{normalized}},
V_{	ext{claim}},
M_{	ext{analysis}}
\right).
$$

## 6. Replay

The original run writes `replay_project.yaml`, which references the run's normalized datasets. `felra replay` re-executes the plan without analysis cache and compares the new result fingerprint with the stored fingerprint.

A match means computational reproduction under the current environment. Floating-point libraries, platform differences, nondeterministic external code, or future implementation changes may produce a mismatch even when high-level conclusions are similar.

## 7. Paper export

`felra export` creates:

- `METHODS.md`;
- `RESULTS.md`;
- `LIMITATIONS.md`;
- `CITATION.cff`;
- claims, analyses, figures, and provenance files;
- `EXPORT_MANIFEST.json` with per-file SHA-256 hashes.

The export is an evidence-assistance package, not an automatically publishable paper.
