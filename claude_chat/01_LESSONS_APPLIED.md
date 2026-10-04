# Lessons Applied — From RAG to Compliance Agent

> **READ THIS FIRST (for Claude Code):**
> This document is a *prevention checklist*. It records the ten concrete
> failures from the previous project (Document Intelligence Platform)
> and the specific mechanism that prevents each from recurring here.
> When making any build decision, treat this as a constraint, not a
> suggestion. If a proposed approach contradicts a prevention mechanism,
> stop and flag it.
>
> This document is referenced by `04_TECH_DECISIONS.md` (ADRs) and
> `CLAUDE.md` (operating rules for AI agents).

---

## Why this document exists

The previous project (Document Intelligence Platform — RAG with evaluation)
shipped successfully but consumed 30% more time than necessary due to
preventable friction. This document ensures the same class of problems
does not recur.

Each lesson below is: **(a)** what went wrong, **(b)** the concrete cost,
**(c)** the mechanism that prevents it now.

---

## Lesson 1 — Dependency drift

**What went wrong.** At almost every phase boundary, `pyproject.toml` was
edited to add new dependencies, but the active virtual environment was
never updated. The missing import was discovered only when the phase's
checkpoint command ran. This happened with `unstructured`, `tiktoken`,
`chromadb`, `openai`, `plotly`, `kaleido`, `fastapi`, and `streamlit`.

**Cost.** ~90 minutes total across the project, spread over 8 incidents.

**Prevention mechanism.**
- A `make sync` target exists from Phase 1 that runs `pip install -e ".[dev]"`.
- A `make doctor` target exists from Phase 1 that imports every public
  module and reports missing dependencies.
- **Every phase checkpoint begins with `make sync && make doctor`.**
- `CLAUDE.md` instructs: *"After editing `pyproject.toml`, run `make sync`
  and `make doctor` before proceeding."*

---

## Lesson 2 — Verification at the wrong granularity

**What went wrong.** Verification happened at the phase level, so
sub-tasks inside a phase were skipped. The Phase 10 incident where
`app.routes` showed only `/health` (a FastAPI lazy-registration quirk)
was 20 minutes of panic caused by testing at the wrong layer.

**Cost.** ~45 minutes total; one near-miss on a false alarm.

**Prevention mechanism.**
- Every runnable entry point (script, CLI, endpoint handler) supports a
  `--self-test` flag that runs a 3-second smoke test asserting its own
  correctness.
- Every phase has a `make verify-phase-N` target that runs all of that
  phase's self-tests.
- **No sub-task is marked complete until its self-test passes.**

---

## Lesson 3 — Tests that pass without testing

**What went wrong.** In Phase 10, the API tests passed even though the
routes weren't registered. Some tests were checking "did the function
get called" instead of "did the endpoint return the right response."

**Cost.** Nearly shipped a broken API. Caught by manual verification.

**Prevention mechanism.**
- Every test must assert an **observable behavior**: return value, HTTP
  status code, persisted side effect, or emitted log event.
- **No tests that only verify function invocation** (no `mock.assert_called`).
- The evaluation harness's critical path (`06_EVAL_SPEC.md` metrics) is
  verified by **mutation testing**: for each metric, we intentionally
  break one line and confirm a test fails.

---

## Lesson 4 — Golden dataset quality discovered late

**What went wrong.** The curated dataset (75 Q&A pairs) had two problems
discovered *after* curation: 43 answers were fragmented substrings, and
18 questions were near-duplicates. Fixing required a rewrite pass.

**Cost.** ~2 hours; ~$0.01 in LLM calls; required a second human review.

**Prevention mechanism.**
- Every curated dataset (this project will have one for change detection
  and one for process mapping) has a **quality gate script** that runs
  *during* curation, not after.
- The gate fails on:
  - Duplicates (semantic similarity > 0.95)
  - Fragments (answers/summaries that don't start with a capital letter
    or end with terminal punctuation)
  - Missing fields (schema violations)
  - Length violations (per-schema min/max)
  - Cross-reference failures (a cited source that doesn't exist)
- **No dataset is committed unless the gate passes.**

---

## Lesson 5 — Logging that didn't log

**What went wrong.** `logs/app.jsonl` was intended to receive structured
JSON events. In reality it received only third-party plaintext. The bug
existed from Phase 1 and was discovered in Phase 11 because nothing had
ever *read back* from the file.

**Cost.** ~30 minutes; required a logging module rewrite late in the
project.

**Prevention mechanism.**
- **Every write has a read-back.** If code writes to a file, a test
  reads the file back and asserts its content.
- The logging subsystem has a self-test that runs in Phase 1's checkpoint.
- **No blind writes anywhere in the codebase.** The pattern is always:
  write → verify → proceed.

---

## Lesson 6 — Serial execution where parallelism was possible

**What went wrong.** The 6-config evaluation matrix ran 450 LLM calls
strictly sequentially. Wall time: ~30 minutes. Parallelism was possible
but not designed in.

**Cost.** Not fatal for a one-off run, but blocked faster iteration.

**Prevention mechanism.**
- **Concurrency is in the architecture, not bolted on.** Every component
  that can run concurrently has an explicit concurrency model in
  `03_ARCHITECTURE.md`.
- Rate-limit-aware concurrency: a semaphore caps in-flight LLM requests,
  and a queue ensures ordered completion.
- The compliance agent processes feeds concurrently by source.

---

## Lesson 7 — CHANGELOG lag

**What went wrong.** CHANGELOG updates were often applied retroactively,
leading to less-detailed records and memory drift about what happened.

**Cost.** ~1 hour of reconstruction effort across the project.

**Prevention mechanism.**
- **CHANGELOG updates happen in the same commit as the code change that
  produces them.** Enforced by a `pre-commit` hook that fails if
  `CHANGELOG.md` wasn't touched in a commit that changed `src/` or
  `scripts/`.
- Every phase close triggers the `phase-tracker` agent automatically.

---

## Lesson 8 — Ad-hoc configuration decisions

**What went wrong.** Configuration parameters (paths, thresholds, model
names) were sometimes decided in code, sometimes in YAML, sometimes in
environment variables, and sometimes in three places with different
values.

**Cost.** Debugging time and confusion, especially around Phase 4 and 9.

**Prevention mechanism.**
- **One config file per concern.** `configs/sources.yaml`,
  `configs/processes.yaml`, `configs/agent.yaml`, `configs/eval.yaml`.
- **Every parameter is loaded via a Pydantic config model.** No `os.getenv`
  calls scattered throughout the codebase.
- Lint rule: `grep -r "os.getenv" src/` returns only hits inside
  `src/compliance_agent/config/loader.py`.

---

## Lesson 9 — "Done" assumed, not demonstrated

**What went wrong.** Phases were sometimes declared done based on
Claude Code's self-report. When verification was performed, it occasionally
revealed that a step had been skipped or a file was missing.

**Cost.** Several partial re-runs and one near-miss on a broken API.

**Prevention mechanism.**
- The DoD (`00_DISCOVERY.md` §11) is a checklist with evidence
  requirements. Every box has a specific, verifiable proof:
  - A passing test path
  - A file path that exists
  - A log line that appeared
  - A screenshot or report artifact
- **No box is checked without evidence.** The phase-tracker agent refuses
  to mark a phase complete if any DoD item lacks an evidence field.

---

## Lesson 10 — Mid-build technology debates

**What went wrong.** Late in the project, there was a debate about
Streamlit vs. Next.js for the UI. This consumed half a day of decision
anxiety that could have been avoided if the UI framework had been locked
earlier.

**Cost.** ~4 hours of "should we or shouldn't we" that produced no output.

**Prevention mechanism.**
- **All technology decisions are made before Phase 1 and locked in
  `04_TECH_DECISIONS.md` as ADRs.**
- Changing a locked decision requires a new ADR that explicitly supersedes
  the old one, with a documented reason. The project pauses until the new
  ADR is approved.
- **No mid-build debates.** If you feel the urge, write the ADR.

---

## Bonus lessons from RAG that don't map to the numbered list

**B1 — Free-tier design as a feature, not a workaround.** The RAG project
used a paid OpenRouter tier. This project uses free tiers plus Ollama.
Designing for rate limits produces a system that is *more* portable and
cost-conscious. It is a portfolio signal, not a compromise.

**B2 — Evaluation is the differentiator, so it must be built first.**
The RAG project built the pipeline first and the evaluation second. This
project builds the eval spec (`06_EVAL_SPEC.md`) as part of Batch 2 —
before the pipeline exists. Metrics define the interface.

**B3 — Security cannot be an afterthought.** RAG's security section was
written at Phase 11. This project writes `07_SECURITY_MODEL.md` in Batch 3
and enforces its controls from Phase 1.

**B4 — Documentation as context, not as output.** RAG's `claude_chat/`
docs were written for humans. This project's docs are also written for
future Claude Code sessions. Every doc opens with a "READ THIS FIRST"
block declaring its scope, its dependencies, and its rules.

---

## The scoreboard

By the end of this project we will be able to say:

| Lesson | Prevented by | Verified at |
|---|---|---|
| 1. Dependency drift | `make sync` + `make doctor` | Every phase checkpoint |
| 2. Wrong verification granularity | `--self-test` + `make verify-phase-N` | Every phase |
| 3. Tests that don't test | Behavior-only assertions + mutation check | Every metric |
| 4. Late dataset quality | Quality gate script during curation | Phase 7 |
| 5. Broken logging | Read-back verification | Phase 1 |
| 6. Serial execution | Concurrency in architecture | Phases 2, 4, 6 |
| 7. CHANGELOG lag | Same-commit rule + pre-commit hook | Every commit |
| 8. Ad-hoc configuration | One config file per concern + lint rule | Every phase |
| 9. Assumed done | DoD with evidence requirements | Every phase |
| 10. Mid-build debates | ADRs locked before Phase 1 | Stage 0 |

**If any of these mechanisms is bypassed during the build, the bypass
is itself a bug and must be recorded in the CHANGELOG with the reason.**