# CLAUDE.md — Operating Rules for Claude Code

> **READ THIS FILE COMPLETELY before making any change to this repository.**
> It is the operating manual for AI-assisted work on the Compliance
> Monitoring Agent. It supersedes any default behavior you might otherwise
> apply.
>
> **Precedence order (highest to lowest):**
> 1. This file
> 2. `04_TECH_DECISIONS.md` (locked ADRs)
> 3. `07_SECURITY_MODEL.md` (P0 controls)
> 4. `06_EVAL_SPEC.md` (metric definitions)
> 5. Everything else
>
> If two sources conflict, the higher-precedence source wins. Flag the
> conflict. Do not resolve it silently.

---

## 1. Project in one paragraph

A compliance monitoring agent for a synthetic EU financial services firm.
It ingests regulatory feeds (EU sanctions, EU AML), detects changes,
summarizes them with citations, maps them to internal business processes,
proposes structured action items, and routes them to human approvers.
Every proposal is traceable from source to approval. It costs $0 to run
(free-tier LLM + local fallback). It is evaluated on six independent
stages.

**The pitch:** *"A compliance agent with a multi-stage evaluation
framework, a security threat model, an audit trail, and full traceability
— and it costs $0 to run."*

## 2. Required reading before any non-trivial change

Read in this order before touching code:

1. `CLAUDE.md` (this file)
2. `00_DISCOVERY.md` — problem, scope, success metrics
3. `01_LESSONS_APPLIED.md` — 10 prevention mechanisms (mandatory)
4. `02_PRD.md` — functional requirements
5. `03_ARCHITECTURE.md` — component structure
6. `04_TECH_DECISIONS.md` — 18 locked ADRs
7. `05_DATA_SPEC.md` — every schema
8. `06_EVAL_SPEC.md` — every metric
9. `07_SECURITY_MODEL.md` — threat model + P0/P1 controls
10. `08_ROADMAP.md` — current phase and its deliverables
11. `09_AGENT_DESIGN.md` — prompt and reasoning design

**Never contradict a locked ADR.** If you believe one should change,
propose a new ADR (e.g., ADR-019 supersedes ADR-013) and wait for
approval. Do not edit a locked ADR in place.

**Never weaken a P0 security control.** If you believe one is wrong,
flag it and wait.

## 3. Repository layout (quick reference)

```
compliance-monitoring-agent/
├── claude_chat/                # ALL planning docs (this file's home)
├── configs/                    # YAML configs (one file per concern)
├── data/
│   ├── raw/                    # fetched content (gitignored)
│   ├── kb/                     # knowledge base (committed)
│   ├── eval/                   # golden set + raw eval fixtures (committed)
│   ├── demo/                   # pre-seeded demo data (committed)
│   └── compliance.db           # SQLite (gitignored)
├── logs/                       # app.jsonl (gitignored)
├── results/                    # eval outputs (gitignored)
├── src/compliance_agent/       # library code (see 03_ARCHITECTURE §6)
├── scripts/                    # numbered runnable entry points
├── api/                        # FastAPI routes
├── dashboard/                  # Streamlit views
├── tests/                      # mirrors src/
├── notebooks/                  # exploration only
├── pyproject.toml              # single dependency declaration
├── requirements.lock           # pinned versions
├── Makefile                    # all commands
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── .gitignore
├── .pre-commit-config.yaml
└── .github/workflows/ci.yml
```

## 4. Phase discipline

Work on exactly one phase at a time, in order, from `08_ROADMAP.md`. The
current phase is stated at the top of the user's message. If unstated,
**ask before proceeding.**

Do not pre-build future phases. Do not volunteer future-phase work.

**At the start of every phase:**
1. Read the phase's deliverables in `08_ROADMAP.md`
2. Read the prevention-mechanism checklist at the end of `08_ROADMAP.md`
3. Confirm the checkpoint command

**At the end of every phase:**
1. Run `make sync && make doctor` (Lesson 1)
2. Run every new module's `__main__` self-test (Lesson 2)
3. Run the phase's checkpoint command
4. Run `make test`
5. Update `CHANGELOG.md` in the SAME commit as the code (Lesson 7)
6. Invoke the `phase-tracker` agent (see §12)
7. Only then declare the phase complete

## 5. Coding rules

1. **Type hints on every function.** `from __future__ import annotations`.
2. **ABCs before implementations.** New source, LLM backend, or metric →
   inherit from base in that package and register in `registry.py`.
3. **Pydantic v2** for all data crossing module boundaries. See
   `05_DATA_SPEC.md`.
4. **No direct LLM SDK calls** outside `llm/gateway.py`. All LLM traffic
   routes through the gateway.
5. **No direct `os.getenv` outside `config/loader.py`** (Lesson 8).
6. **No raw SQL outside `storage/`.** Parameterized queries only (C-15).
7. **No `eval`, `exec`, or `shell=True` anywhere.** (C-11)
8. **Every LLM/embedding call logs** `{model, prompt_tokens,
   completion_tokens, cost_usd, latency_ms}` via `utils/cost_tracker.py`.
9. **Config over constants.** No magic numbers. Chunk sizes, k, thresholds,
   model names → YAML (Lesson 8).
10. **Determinism.** `temperature=0`, seed from config, cache enabled.
    Log any source of nondeterminism.
11. **Fail loud in dev, fail soft in prod.** Config/schema errors raise.
    Per-document ingestion errors are logged, skipped, and summarized.
12. **No `print()`.** Use `structlog`. Exception: `__main__` self-tests
    may use `print()` for readable output.
13. **Docstrings** on every module and class. One-line summary minimum.
14. **Typed exceptions** from `exceptions.py`. No bare `except:`.

## 6. Do NOT

- ❌ Do not install packages without updating `pyproject.toml` AND running
  `make sync`
- ❌ Do not call real LLMs in unit tests (mock via `tests/mocks/llm.py`)
- ❌ Do not modify `data/eval/golden.jsonl` programmatically
- ❌ Do not add a metric without updating `06_EVAL_SPEC.md` + adding a test
- ❌ Do not use `print()` in application code — use `structlog`
- ❌ Do not add files outside the current phase's deliverable list
- ❌ Do not refactor previous phases' code while in the current phase
- ❌ Do not silently change an ADR — propose a new one
- ❌ Do not weaken a P0 security control
- ❌ Do not bypass human-in-the-loop for any reason, ever
- ❌ Do not let the LLM decide severity, deadline, or routing
- ❌ Do not modify anything in `claude_chat/` unless the user explicitly
  asks for a documentation update
- ❌ Do not create configuration sources outside `config/loader.py`
- ❌ Do not write to `audit_events` outside its repository

## 7. Prevention mechanisms (from `01_LESSONS_APPLIED.md`)

These are enforced every phase. Refer to `01_LESSONS_APPLIED.md` for the
full rationale behind each.

| # | Mechanism | Where enforced |
|---|---|---|
| 1 | `make sync` + `make doctor` before every phase checkpoint | Every phase |
| 2 | `--self-test` on every runnable entry point | Every script/module |
| 3 | Tests assert observable behavior, not function calls | Every test |
| 4 | Quality gate runs during curation, not after | Datasets |
| 5 | Every write has a read-back test | Every persistence layer |
| 6 | Concurrency in architecture, not bolted on | LLM gateway, ingestion |
| 7 | CHANGELOG updates in same commit as code | Pre-commit hook |
| 8 | One config file per concern; `os.getenv` only in `config/loader.py` | Lint rule + review |
| 9 | DoD checked with evidence, not assumed | phase-tracker agent |
| 10 | Decisions locked before build; changes need new ADRs | This file + ADRs |

## 8. Checkpoint commands

| Phase | Command | Expected |
|---|---|---|
| 1 | `make sync doctor test selftest` | All pass; JSON logs verified |
| 2 | `make ingest && pytest tests/test_ingestion.py tests/security/test_parser_safety.py -v` | Fetched + normalized; safety tests pass |
| 3 | `make detect && pytest tests/test_detection.py -v` | Changes emitted; deterministic IDs |
| 4 | `make process && pytest tests/test_summarizer.py tests/test_mapper.py tests/security/ -v` | Summaries + mappings; injection tests pass |
| 5 | `pytest tests/test_proposer.py tests/test_routing.py tests/test_approval.py tests/security/test_approval_integrity.py -v` | Proposals + approvals; concurrency test passes |
| 6 | `make serve & sleep 5 && curl -s localhost:8501 \| head -20 && kill %1` | Dashboard renders |
| 7 | `make eval && pytest tests/test_metrics.py tests/test_stats.py tests/test_golden_gate.py -v` | Report produced; fixtures pass |
| 8 | `python scripts/08b_validate_golden.py && pytest tests/test_golden_schema.py -v` | Gate passes |
| 9 | `make demo && pytest tests/test_pipeline_integration.py -v` | Demo runs; integration test passes |
| 10 | `pytest tests/security/ -v && pip-audit && docker compose up -d` | Security tests pass; audit clean; compose starts |
| 11 | `gh run list --limit 3` | CI green |

**If a checkpoint fails, do not proceed to the next phase.**

## 9. Commit message format

`[phase-N] type(scope): summary`

Types: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`, `eval`, `sec`

Examples:
```
[phase-3] feat(detection): deterministic change IDs via sha256
[phase-4] sec(llm): fence untrusted content in all prompts
[phase-5] test(approval): concurrency test proves single-winner
[phase-7] eval(metrics): add mapping_precision with fixtures
```

**Every commit that changes `src/` or `scripts/` must also update
`CHANGELOG.md`.** The pre-commit hook enforces this.

## 10. Response style (for AI assistant)

- **Concise and technical.** No filler.
- **Show, don't tell.** Full code blocks, exact paths, real commands.
- **Flag uncertainty explicitly.** Propose how to verify.
- **Surface trade-offs** in one sentence when a choice is non-obvious.
- **Respect "one step at a time."** Do not volunteer future phases.
- **Never claim "done" without evidence.** Paste the exact command and
  its output.

## 11. When to ask vs. proceed

**Ask before proceeding if:**
- The change touches metric definitions (`06_EVAL_SPEC.md`)
- The change contradicts an ADR
- The change weakens a P0 security control
- The phase is ambiguous
- A library behavior is uncertain and affects correctness
- Cost implication > $0.10 per run

**Proceed without asking if:**
- Clear deliverable within the current phase
- Follows an established pattern from a previous phase
- Bug fix with obvious correct behavior
- Formatting, docstrings, or type hints

## 12. The phase-tracker agent

Located at `.claude/agents/phase-tracker.md`.

**When to invoke:** at the close of every phase.

**What it does:**
1. Verifies every deliverable exists
2. Verifies every prevention-mechanism checkbox is checked with evidence
3. Updates `08_ROADMAP.md` (phase → 🟢)
4. Updates `00_START_HERE.md` (status table)
5. Updates `CHANGELOG.md` with a completed entry
6. Refuses to close if any DoD item lacks evidence

**The phase is not complete until the agent has run and succeeded.**

## 13. Session hygiene

Before ending any session:

- [ ] `CHANGELOG.md` updated (if a phase moved)
- [ ] Phase status updated in `08_ROADMAP.md` and `00_START_HERE.md`
- [ ] Any new decision captured as an ADR
- [ ] Any new metric added to `06_EVAL_SPEC.md` with test reference
- [ ] No `TODO` comments left in committed files
- [ ] `make test` passes
- [ ] No `.env` file staged or committed
- [ ] No secrets in log output (spot-check)

## 14. What to do when stuck

Ask. Do not guess.

- **Uncertain about a metric?** Read `06_EVAL_SPEC.md` and ask.
- **Uncertain about a schema?** Read `05_DATA_SPEC.md` and ask.
- **Uncertain about a security control?** Read `07_SECURITY_MODEL.md`
  and ask.
- **Uncertain about phase scope?** Read `08_ROADMAP.md` and ask.
- **Uncertain about the agent's behavior?** Read `09_AGENT_DESIGN.md`
  and ask.

**A wrong guess costs hours. A question costs seconds.**