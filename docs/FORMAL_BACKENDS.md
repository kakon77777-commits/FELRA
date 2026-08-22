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
- **`axioms_within:`** turns "this file elaborates" into a claim about a whole
  development. Lean's `#print axioms` output is parsed and every reported theorem
  must rest only on the declared axioms; one that does not → `refuted`, naming it.

  Three things make this safe to have:

  * **Both output forms are read.** A theorem depending on nothing prints
    "does not depend on any axioms", and reading only the bracketed form silently
    drops the cleanest theorems in a development from the audit.
  * **An axiom claim about nothing is `unknown`, never `verified`.** A file that
    prints no axiom lines audits no theorem, and reporting success there would
    mean "no theorem exceeded the allowed set" of an empty set.
  * **It is refused on any other backend.** Declaring it for `z3` or `tlc` would
    be a claim nothing checks, so the loader rejects it.

  The count of theorems audited and the axioms actually seen are both recorded, so
  a shrinking audit is visible rather than silent.
- **Added:** 2026-08-18, v1.1.0.
- **Validated against:** the `collatz-lean` development
  (`kakon77777-commits/collatz-lean`), `Collatz/AllOnes.lean`, 10,005 bytes, on a
  tree of 184 theorems with its own axiom audit. Result `verified`, exit 0, 48.0 s,
  with Lake 5.0.0-src+d8b1897 / Lean 4.33.0. A real development rather than a toy
  file, because an adapter that has only met a passing one-liner has not been
  tested.

  Then against the **whole** development via `axioms_within`: `Collatz/Audit.lean`,
  **184 theorems audited, every one resting only on `propext`, `Classical.choice`
  and `Quot.sound`**, in 15.8 s. That 184 independently agrees with the number the
  development's own `gate/audit_axioms.py` reports — and the two reach it by
  different routes, one scanning the sources for declarations and the other parsing
  the checker's output. Two methods meeting on a count is worth more than either
  asserting it.

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

## Generating obligations, not only checking them

Everything above is an adapter over an obligation **somebody wrote**. From v1.8.0
FELRA can also **render one from a claim** — the direction the addendum's stage F
names, and the one with a failure mode the sections above do not have.

- **Program invoked:** `z3`, through the adapter already registered above. No new
  program is added, and no new dependency. What is new is who wrote the file the
  solver reads.
- **What is generated:** SMT-LIB2 only. `(set-logic AUFNIRA)`, the declared domain
  of every parameter, and the **negation** of the claim — so `unsat` means no
  counterexample exists on that domain, and `sat` *is* a counterexample.
- **Lean and Coq are named in stage F and are deliberately not generated.**
  Producing a proof script that both typechecks and states the intended thing is a
  different problem from translating an expression. Attempting it would emit
  artifacts that mostly fail to compile and occasionally compile while meaning
  something else — the second kind being far worse than no feature at all.

### The failure mode, and the guard

An exporter that emits a trivially unsatisfiable obligation — contradictory domain
constraints, a mistranslated connective collapsing to `false` — is reported `unsat`
by any solver, for every claim, forever. It would look exactly like a verifier that
proves everything, and each individual run would look like a success.

So every export is checked **twice**: as written, and with the conclusion flipped.

| obligation | twin | verdict | meaning |
| --- | --- | --- | --- |
| `unsat` | `sat` | `verified` | no counterexample, and the domain is non-empty |
| `sat` | `unsat` | `refuted` | the claim fails everywhere on the domain |
| `sat` | `sat` | `refuted` | the claim holds at some points and fails at others |
| `unsat` | `unsat` | **`unknown`** | the domain is empty; every obligation over it is vacuously unsat |

The last row is the guard, and no certificate is issued for it. The third row is
worth stating too, because the first version of this guard got it wrong: it
refused whenever the pair *agreed*, which turned a perfectly good refutation into
`unknown`. Running a claim that is true somewhere and false elsewhere is what
exposed that — a false claim, run on purpose, rather than a review of the code.

### Faithfulness over coverage

The translator refuses whatever it cannot render exactly, with a reason: a function
call, a non-literal or non-integer exponent, a numeric expression used as a truth
value, an operator with no exact SMT rendering. A finite value list becomes a
disjunction rather than a range, because widening it would make the obligation
cover points the claim never spoke about — and a proof of the wider statement is
not a proof of this one. An obligation that is *nearly* the claim is an obligation
about a different claim, and a solver's verdict on it is worth nothing.

- **Added:** 2026-08-21, v1.8.0.
- **Validated against:** the real solver, in all four rows of the table above.
  Three are reachable from well-formed projects (`examples/obligation_export/`).
  The fourth is not — `load_project` refuses an inverted range, so an empty domain
  can only arise from a defect in the exporter itself. It is therefore reached by
  **planting that defect**: `scripts/drill_v18.py` injects contradictory domain
  constraints into FELRA's own output, and requires the run to come back `unknown`
  with no certificate. The same drill plants 12 defects in total and requires
  each to be caught **by the check named for it**, not merely by something. As of
  2026-08-21 it reports 12/12.

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
| 2026-08-21 | 1.8.0 | The **generating** direction added: FELRA renders an obligation from a claim (SMT-LIB2 only) and checks it against its discriminating twin. No new backend, no new program, no new dependency. Two reproducibility defects found in code shipped since v1.1.0 and fixed: `duration_seconds` was inside `result_sha256`, so every formal analysis had an unstable fingerprint and `felra replay` reported MISMATCH on untouched projects; and replay never captured the declared obligation, so every replayed `formal_check` degraded to "obligation not found" without the checker ever seeing the file. Obligations are now captured into the run beside datasets. `scripts/drill_v18.py` added. |
| 2026-08-18 | 1.3.0 | `axioms_within` added to the `lean` backend, so a formal claim can be about a whole development rather than one file; validated against collatz-lean's 184 theorems. Z3 5.1.0 installed under `D:\Ai\work together\tools\`; the `z3` entry moves from *adapter present, never exercised* to **both verdict directions run against the real solver**. Adapters now accept a declared `path:`, so a locally installed checker need not be on `PATH`. Tool provenance recorded in `tools/README.md`, including the fact that Z3 publishes no checksum for this release, so its hashes are *recorded* rather than *verified* — unlike `tla2tools.jar`, whose SHA-1 matches a value written down independently in Neo.K's own v0.9 package. |
