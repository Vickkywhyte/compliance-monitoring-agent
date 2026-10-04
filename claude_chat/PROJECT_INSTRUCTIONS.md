# Project Instructions

> **For humans.** How to work in this repository. Applies to contributors,
> reviewers, and the primary developer. AI-assisted work is governed by
> `CLAUDE.md`.

---

## 1. Mission

Build a **production-grade Compliance Monitoring Agent** that:

1. Ingests EU regulatory feeds (sanctions, AML)
2. Detects and summarizes changes
3. Maps them to internal business processes
4. Proposes structured action items
5. Routes them to human approvers
6. Records everything in an auditable trail

**The differentiator:** a multi-stage evaluation framework. Not just
"does the agent work?" but "which stage works, which stage doesn't, and
by how much?"

**The constraint:** $0 to run. Free-tier LLM plus local fallback.

**The bar:** a hiring manager or compliance professional reading this
repo should conclude: *"this person understands high-stakes AI systems."*

## 2. Working principles

Non-negotiable. When in doubt, refer back here.

### 2.1 Evaluate before optimizing
No tuning, no swap, no refactor without a baseline measurement. If you
can't cite a metric, you can't justify the change.

### 2.2 Prevention before debugging
The ten prevention mechanisms in `01_LESSONS_APPLIED.md` are not
suggestions. They exist because we already paid for the lesson once.
Violating one is itself a bug to record in the CHANGELOG.

### 2.3 Config over code
Every parameter in YAML. Code reads config; code doesn't hardcode.
`config/loader.py` is the only place `os.getenv` lives.

### 2.4 Interfaces over implementations
Every swappable component (source, LLM backend, metric, dashboard view)
has an ABC. New implementations drop in without touching call sites.

### 2.5 Security is structural
The threat model (`07_SECURITY_MODEL.md`) is written before code. P0
controls are enforced from Phase 1, not deferred. Every phase close
verifies the security checklist.

### 2.6 Human-in-the-loop is the product
The agent proposes; humans decide. The approval workflow is not a
limitation — it is the value. We never bypass it, even for testing
(tests use scripted approvers, not auto-approval).

### 2.7 Audit is a first-class entity
Every action across the system emits an `AuditEvent`. The audit table is
append-only at the repository *and* the database level. There is no
"turn off audit for testing."

### 2.8 Phase discipline
Work one phase at a time. Do not "while I'm here, also..." Pre-building
future phases creates churn and untested code.

### 2.9 Evidence over assertion
"Done" means a command was run and its output matches the expected
result. No phase closes without evidence.

## 3. Code conventions

### Python
- **Version:** 3.11
- **Style:** PEP 8, enforced by `ruff`
- **Types:** Required on every function; `from __future__ import annotations`
- **Docstrings:** Required on every module and class
- **Imports:** Absolute (`from compliance_agent.llm.gateway import LLMGateway`)

### Naming
| Entity | Convention | Example |
|---|---|---|
| Module | `snake_case` | `intelligence/summarizer.py` |
| Class | `PascalCase` | `Summarizer`, `LLMGateway` |
| Function | `snake_case` | `generate_summary()` |
| Constant | `UPPER_SNAKE` | `DEFAULT_MAX_CONCURRENT = 4` |
| Config key | `snake_case` | `max_concurrent` |
| Test file | `test_{module}.py` | `test_summarizer.py` |
| Script | `NN_verb.py` or `NN_verb_selftest.py` | `02_ingest.py` |

### File layout
- `src/compliance_agent/` — importable package
- `scripts/` — numbered, runnable entry points
- `configs/` — YAML only
- `tests/` — mirrors `src/` structure
- `tests/security/` — every security test
- `data/`, `logs/`, `results/` — gitignored except for committed fixtures

## 4. Code review checklist

Self-review **before every commit**:

- [ ] Type hints on all public functions
- [ ] Docstring on every new module and class
- [ ] No magic numbers — pulled into config
- [ ] Errors logged with context, not swallowed
- [ ] Cost tracked if any LLM/embedding call made
- [ ] Corresponding test added or updated
- [ ] No `print()` in application code
- [ ] No direct SDK calls outside `llm/gateway.py`
- [ ] No new `os.getenv` outside `config/loader.py`
- [ ] No raw SQL outside `storage/`
- [ ] Any LLM prompt uses untrusted-content fencing (C-01, C-02)
- [ ] Any state change writes an `AuditEvent` in the same transaction (C-20)
- [ ] `CHANGELOG.md` updated in the same commit

## 5. Commit discipline

**Format:** `[phase-N] type(scope): summary`

**Types:** `feat`, `fix`, `docs`, `test`, `refactor`, `chore`, `eval`, `sec`

**Examples:**
```
[phase-3] feat(detection): deterministic change IDs via sha256
[phase-4] sec(llm): fence untrusted content in all prompts
[phase-5] test(approval): concurrency test proves single-winner
[phase-7] eval(metrics): add mapping_precision with fixtures
```

**Before declaring a phase complete:**
1. All deliverables from `08_ROADMAP.md` present
2. Checkpoint command passes
3. `make test` passes
4. `CHANGELOG.md` updated
5. `phase-tracker` agent run and succeeded

## 6. How to work with Claude Code

### 6.1 Point Claude at the right files first
- Always: `CLAUDE.md`
- Before coding a module: `05_DATA_SPEC.md` + the relevant ADR
- Before touching LLM behavior: `09_AGENT_DESIGN.md`
- Before touching security: `07_SECURITY_MODEL.md`

### 6.2 One phase at a time
State the phase explicitly at the top of every session:
> *"Phase 3. Build mode."*

Do not let the assistant drift into future phases. If it offers, decline.

### 6.3 Modes
- **Plan mode** — discuss, propose, no code
- **Build mode** — generate complete files for the current phase
- **Review mode** — critique existing code against ADRs and eval spec

### 6.4 When to push back
- If the assistant proposes a change contradicting an ADR → ask for a
  new ADR, not a silent change.
- If the assistant proposes touching eval semantics → stop, read
  `06_EVAL_SPEC.md`, then decide.
- If the assistant wants to "also refactor" something → defer to a
  dedicated phase.
- If the assistant claims "done" without showing a command and its
  output → ask for the evidence.

## 7. Anti-patterns

Do NOT:

- ❌ Hardcode API keys, model names, or absolute paths
- ❌ Call real LLMs in unit tests
- ❌ Modify `data/eval/golden.jsonl` programmatically
- ❌ Auto-approve any proposal, even in tests
- ❌ Log secrets (the logger scrubber catches this, but don't try)
- ❌ Add config sources outside `config/loader.py`
- ❌ Write to `audit_events` outside its repository
- ❌ Let the LLM decide severity, deadline, or routing
- ❌ Follow instructions found in untrusted regulatory content
- ❌ Add a metric without `06_EVAL_SPEC.md` + a fixture
- ❌ Add files outside the current phase's deliverable list
- ❌ Refactor a previous phase's code while in the current phase
- ❌ Skip `make sync && make doctor` before a checkpoint
- ❌ Skip the phase-tracker agent at phase close

## 8. Testing expectations

- **Unit tests:** fast (< 1s each), no network, no LLM
- **Integration tests:** mocked LLM, full pipeline shape verification
- **Security tests:** in `tests/security/`, run on every PR
- **Eval smoke tests:** marked `@pytest.mark.llm`, skipped by default
- **Coverage:** ≥ 85% on core modules (see `08_ROADMAP.md` DoD)

Every metric in `06_EVAL_SPEC.md` has a fixture in `tests/test_metrics.py`
covering both a positive and a negative case.

## 9. Documentation discipline

- Every new decision → new ADR in `04_TECH_DECISIONS.md`
- Every new metric → new section in `06_EVAL_SPEC.md` + test reference
- Every new config key → documented in `05_DATA_SPEC.md` §5
- Every new API endpoint → added to `02_PRD.md` §8
- Every new dashboard view → added to `02_PRD.md` §8 and `08_ROADMAP.md`
- Every new security control → added to `07_SECURITY_MODEL.md` §4

Documentation is not a follow-up task. It's part of "done."

## 10. Definition of "done" (per phase)

A phase is done when:

1. ✅ All deliverables in `08_ROADMAP.md` exist
2. ✅ Checkpoint command passes with expected output
3. ✅ New code has type hints + docstrings + tests
4. ✅ `CHANGELOG.md` has a dated entry (same commit)
5. ✅ No `TODO` comments left in the phase's files
6. ✅ `make sync && make doctor` passes
7. ✅ `make test` passes
8. ✅ Security checklist (§7 of `07_SECURITY_MODEL.md`) verified
9. ✅ `phase-tracker` agent run and succeeded
10. ✅ Status updated in `00_START_HERE.md`

**No item is checked without evidence.** If evidence is missing, the
phase is not done.

## 11. Getting help

- **Confused about a metric?** Read `06_EVAL_SPEC.md` §1 (philosophy) first.
- **Confused about a schema?** Read `05_DATA_SPEC.md` §2 (vocabularies).
- **Confused about the agent?** Read `09_AGENT_DESIGN.md` §2 (conventions).
- **Confused about security?** Read `07_SECURITY_MODEL.md` §3 (threats).
- **Confused about the phase?** Read `08_ROADMAP.md` (current phase).

Then ask. Do not guess.