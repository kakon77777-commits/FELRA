# FELRA Formal Backend Register

**What this file is.** A permanent record of every external formal checker FELRA
knows how to invoke: *which program*, *why it was added*, *when*, and *what real
artifact it was validated against before it was trusted*.

A formalisation decision cannot be added quietly. FELRA integrates other people's
formalisation tools rather than building its own, which makes the question "which
program actually said yes, and on what" the whole of the evidential content. This
register is the answer, and it is a file rather than a commit message so that it
can be read without `git log`.

**Adding a backend is a documented act.** `felra.formal.BACKENDS` is a closed
tuple. A project file selects an adapter by name; it never supplies a command to
run. Extending the tuple without adding a section here is a defect, and
`tests/test_v11.py::test_backend_list_is_closed` fails on an unknown name.

---

## The rule these backends exist under

From the whitepaper's own stage-4 list (§15, 階段 4：正式驗證後端):

> 將 Python 證據狀態與正式證明狀態分開標記
> — mark the Python evidence status and the formal proof status separately

So a `formal_check` analysis carries **two** results and never merges them:

| field | meaning |
| --- | --- |
| `success` | FELRA's pipeline flag: the analysis ran and the **declared expectation** was met. Not a claim that anything was proved. |
| `metrics.formal_status` | the external checker's verdict: `verified`, `refuted`, `unknown`, or `unavailable`. |

`AGENTS.md` §11 lists *changing the meaning of "pass" or "proof"* as requiring
approval. Adding a separate status **alongside** the existing one is what keeps
this feature from being that change: no existing FELRA result means anything
different than it did before v1.1.0.

### Why four statuses and not a boolean

`unknown` (the checker ran and did not decide) and `unavailable` (the checker did
not run) are different facts. Collapsing them is the mechanism by which a machine
without the tool becomes a machine that passed. A missing checker is never
`verified`, and a project that declares `expect: verified` **fails** on a machine
where the checker is absent.

### What is always recorded

Per `AGENTS.md` §9.4, every run records:

- **which program ran** — backend name, exact command, resolved path, version
  string, and the SHA-256 of the executable or archive that decided;
- **what was checked** — the obligation's path, SHA-256, and size;
- **what it rests on** — declared `assumptions` and `limitations`;
- **where it came from** — `derives_from`, the FELRA claim and analysis ids that
  produced the obligation.

"A prover said yes" is not evidence. "This artifact, with this hash, checked by
this binary, with this hash, said yes" is.

---

## Registered backends

### `lean` — Lean 4 via `lake`

- **Program invoked:** `lake env lean <obligation>`, run inside a declared
  `project_dir`. FELRA does not install Lean, does not manage toolchains, and
  does not fetch mathlib.
- **Availability:** requires `lake` on `PATH`. Absent → `unavailable`.
- **Verdict mapping:** non-zero exit or `error:` in the output → `refuted`;
  `sorry` present → `unknown` (an incomplete proof is not a proof and is not a
  refutation); otherwise → `verified`.
- **Added:** 2026-08-18, v1.1.0.
- **Validated against:** the `collatz-lean` development
  (`kakon77777-commits/collatz-lean`), `Collatz/AllOnes.lean`, 10,005 bytes, on a
  tree of 184 theorems with its own axiom audit. Result `verified`, exit 0, 48.0 s,
  with Lake 5.0.0-src+d8b1897 / Lean 4.33.0. A real development rather than a toy
  file, because an adapter that has only met a passing one-liner has not been
  tested.

### `tlc` — TLA+ model checker via `tla2tools.jar`

- **Program invoked:** `java -jar <jar> [-config <cfg>] <module>`. The `jar` path
  is declared by the project and may use `${ENV_VAR}`. **FELRA neither ships nor
  downloads `tla2tools.jar`**, so no third-party binary enters this repository and
  no dependency is added.
- **Availability:** requires `java` on `PATH` **and** the declared jar to exist.
  Either absent → `unavailable`. A `tlc` analysis without a `jar` field is
  rejected at config-parse time.
- **Hashing note:** the **jar** is hashed, not `java`. The jar is what decides.
- **Verdict mapping:** `Error:` in the transcript → `refuted`; no completion line
  → `unknown`; a clean transcript with a **non-zero exit** → `unknown` with the
  disagreement stated, never resolved in either direction; clean transcript and
  exit 0 → `verified`.
- **Added:** 2026-08-18, v1.1.0.
- **Validated against:** `examples/formal_check/Counter.tla` (378 bytes,
  9 reachable states) with TLC2 2.19 from `tla2tools.jar` v1.7.4, SHA-256
  `936a262061c914694dfd669a543be24573c45d5aa0ff20a8b96b23d01e050e88`.

  **A real bug was found by this validation and is the reason the verdict mapping
  is written the way it is.** The first version of the adapter reported `refuted`
  on exit 255 for a model TLC had in fact checked cleanly. The non-zero exit came
  from a path this adapter had mangled — it resolved the obligation against the
  caller's working directory and then set the subprocess's directory to the
  obligation's own parent, so the path was consumed twice and the file was not
  found. Trusting the exit code alone would have recorded a correct model as
  refuted; trusting the transcript alone would hide a genuine crash. Both are read
  now, and a disagreement is reported rather than resolved. A mocked test would
  have used exit 0 and never surfaced this.

### `z3` — SMT solver

- **Program invoked:** `z3 <obligation>` on an SMT-LIB2 file.
- **Availability:** a declared `path:` is honoured first, then `PATH`. Absent →
  `unavailable`. FELRA does **not** take a dependency on `z3-solver`; see
  `AGENTS.md` §12.
- **Verdict mapping:** `unsat` → `verified` (the negated obligation has no model);
  `sat` → `refuted` (a counter-model exists); anything else → `unknown`.
- **Added:** 2026-08-18, v1.1.0.
- **Validated against:** initially the **absent** path only — z3 was not installed
  on the machine where the adapter was written, and that was recorded here rather
  than glossed. Z3 5.1.0 (x64 Windows) was installed on 2026-08-18 and **both
  directions are now exercised by the real solver**:

  | obligation | z3 says | adapter reports |
  | --- | --- | --- |
  | `examples/formal_check/exact_sum.smt2` | `unsat` | `verified` |
  | `examples/formal_check/counter_model.smt2` | `sat` | `refuted` |

  The satisfiable obligation exists precisely so the `refuted` path is run rather
  than assumed: an adapter that has only ever seen `unsat` has not been tested.

  `exact_sum.smt2` is the same identity `examples/cross_backend` measures in exact
  rational arithmetic, posed to a different instrument as a proof obligation in
  the reals. Two channels meeting on one fact is worth more than either alone —
  and they answer *different* questions, so agreement is informative rather than
  circular.

---

## Not registered

Deliberately absent, and each for a reason rather than by oversight:

- **Coq, Isabelle, Tamarin, ProVerif, EasyCrypt, cvc5** — the whitepaper's stage 4
  names several of these. None is installed on the machine where this slice was
  built, so writing an adapter for one would produce an unexercised code path with
  a plausible-looking verdict mapping. `z3` is already one such entry and one is
  enough; more would dilute the register's meaning.
- **Any "run this command" backend.** A generic adapter taking a shell command
  from a project file would make every project file executable code and would make
  this register meaningless, since the program invoked would no longer be knowable
  from the backend name.

---

## History

| date | version | change |
| --- | --- | --- |
| 2026-08-18 | 1.1.0 | Register created. `lean`, `tlc`, `z3` added. `formal_check` analysis type introduced with the four-valued status and the evidence/formal separation. TLC path-and-exit-code bug found during validation and fixed. |
| 2026-08-18 | 1.3.0 | Z3 5.1.0 installed under `D:\Ai\work together	ools\`; the `z3` entry moves from *adapter present, never exercised* to **both verdict directions run against the real solver**. Adapters now accept a declared `path:`, so a locally installed checker need not be on `PATH`. Tool provenance recorded in `tools/README.md`, including the fact that Z3 publishes no checksum for this release, so its hashes are *recorded* rather than *verified* — unlike `tla2tools.jar`, whose SHA-1 matches a value written down independently in Neo.K's own v0.9 package. |
