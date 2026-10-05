# Roadmap — Compliance Monitoring Agent

> **READ THIS FIRST (for Claude Code):**
> Work one phase at a time, in order. Do not start Phase N+1 until Phase N's
> checkpoint passes AND the phase-tracker agent has closed Phase N. Every
> phase has a prevention mechanism from `01_LESSONS_APPLIED.md` wired in.
> If a phase's checkpoint command is not documented here, it does not exist.
>
> **Dependencies:** `00_DISCOVERY.md` · `01_LESSONS_APPLIED.md` ·
> `02_PRD.md` · `03_ARCHITECTURE.md` · `04_TECH_DECISIONS.md` ·
> `05_DATA_SPEC.md` · `06_EVAL_SPEC.md` · `07_SECURITY_MODEL.md`
> **Depended on by:** `09_AGENT_DESIGN.md` · `CLAUDE.md`

---

## Overview

| # | Phase | Est. effort | Depends on |
|---|---|---|---|
| 1 | Scaffolding + safety rails | 0.5 day | — |
| 2 | Ingestion + storage | 1.5 days | 1 |
| 3 | Change detection | 1 day | 2 |
| 4 | Intelligence layer (summarize, map) | 2 days | 3 |
| 5 | Proposals + routing + approval | 2 days | 4 |
| 6 | Dashboard (Streamlit) | 1.5 days | 5 |
| 7 | Evaluation harness | 2 days | 5 |
| 8 | Ground truth + golden set | 1.5 days | 7 |
| 9 | End-to-end pipeline + demo mode | 1 day | 8 |
| 10 | Security hardening + Docker | 1 day | 9 |
| 11 | Documentation + launch | 1 day | 10 |
| | **Total** | **~15 days** | |

**Legend:** 🟢 done · 🟡 in progress · ⚪ not started · 🔴 blocked

---

## Phase 1 — Scaffolding + safety rails 🟢

**Goal:** A cloneable repo with the prevention mechanisms from Lessons 1, 5, 7,
8, and 9 already in place. No application logic yet.

**Deliverables:**
```
pyproject.toml                        # pinned dependencies
requirements.lock                      # exact versions (pinned)
.env.example                           # all env vars with empty values
.gitignore                             # covers .env, data/, logs/, results/, .venv/
.pre-commit-config.yaml                # CHANGELOG enforcement + secret scan
Makefile                               # all targets below
docker-compose.yml                     # stub
Dockerfile                             # stub
src/compliance_agent/__init__.py
src/compliance_agent/config/__init__.py
src/compliance_agent/config/loader.py  # ONLY place os.getenv is called
src/compliance_agent/config/models.py  # Pydantic config schemas
src/compliance_agent/utils/__init__.py
src/compliance_agent/utils/logging.py  # structlog + stdlib + secret scrubber
src/compliance_agent/utils/ids.py      # ULID + hashing helpers
src/compliance_agent/utils/ratelimit.py# token bucket + backoff utilities
src/compliance_agent/exceptions.py
src/compliance_agent/storage/__init__.py
src/compliance_agent/storage/db.py     # SQLite connection, migrations runner
src/compliance_agent/storage/models.py # Pydantic models (from 05_DATA_SPEC)
src/compliance_agent/storage/audit.py  # append-only repo + SQLite triggers
configs/sources.yaml                   # from 05_DATA_SPEC §5.1
configs/agent.yaml                     # from 05_DATA_SPEC §5.2
configs/routing.yaml                   # from 05_DATA_SPEC §5.3
configs/eval.yaml                      # from 05_DATA_SPEC §5.4
scripts/doctor.py                      # imports every public module
scripts/selftest.py                    # runs every module's __main__ selftest
tests/__init__.py
tests/test_config.py
tests/test_logging.py                  # verifies read-back (Lesson 5)
tests/test_ids.py
tests/security/__init__.py
tests/security/test_secret_scrubbing.py
tests/security/test_audit_immutability.py
```

**Prevention mechanisms active:**
- **Lesson 1:** `make sync` and `make doctor` targets
- **Lesson 5:** `tests/test_logging.py` reads back the log file
- **Lesson 7:** `.pre-commit-config.yaml` enforces CHANGELOG updates
- **Lesson 8:** `config/loader.py` is the only place `os.getenv` is called
- **Security:** C-06 to C-09 (secret scrubber, `.env` gitignore, tests), C-23 to C-25 (audit immutability)

**Acceptance criteria:**
- `make sync` installs dependencies; `make doctor` reports all imports OK
- `make test` runs and passes
- `make selftest` runs every module's `__main__` block
- Logging writes JSON to `logs/app.jsonl` and read-back test passes
- `.env` is gitignored; secret scrubber test passes
- `audit_events` table rejects UPDATE and DELETE (test passes)
- Pre-commit hook fires on a test commit missing CHANGELOG update
- A deliberately malformed config raises `ConfigError`

**Checkpoint:**
```bash
make sync doctor test selftest
```
Expected: all pass; log file contains structured JSON; audit immutability
test passes.

**Risks:**
- Pre-commit hooks require `pre-commit install`; document in README
- SQLite trigger syntax differs across versions; test on target version

---

## Phase 2 — Ingestion + storage 🟢

**Goal:** Fetch from all three source types, normalize, and persist. No
detection yet.

**Deliverables:**
```
src/compliance_agent/sources/__init__.py
src/compliance_agent/sources/base.py       # Source ABC
src/compliance_agent/sources/eurlex.py
src/compliance_agent/sources/sanctions.py
src/compliance_agent/sources/eba.py
src/compliance_agent/sources/registry.py
src/compliance_agent/ingestion/__init__.py
src/compliance_agent/ingestion/fetch.py    # HTTP with retry + size limit + timeout
src/compliance_agent/ingestion/normalize.py# Raw → RegulatoryDocument
src/compliance_agent/ingestion/orchestrator.py # parallel per source
src/compliance_agent/storage/documents.py
scripts/ingest.py
scripts/01_ingest_selftest.py
tests/test_ingestion.py
tests/test_sources_eurlex.py
tests/test_sources_sanctions.py
tests/test_sources_eba.py
tests/security/test_parser_safety.py       # C-10 to C-14
tests/fixtures/raw/eurlex_sample.xml
tests/fixtures/raw/sanctions_sample.xml
tests/fixtures/raw/eba_sample.html
```

**Prevention mechanisms active:**
- **Lesson 6:** Per-source parallelism with semaphore
- **Security:** C-10 to C-14 (defusedxml, size limits, timeouts), C-15 to C-17 (parameterized SQL, repo encapsulation), C-38 to C-39 (path safety)

**Acceptance criteria:**
- Fetches from each of the three sources (with fixture fallback if offline)
- Normalizes to `RegulatoryDocument` matching `05_DATA_SPEC.md` §3.1
- Preserves source URL, fetch timestamp, content hash
- Idempotent: re-ingesting identical content produces no duplicates
- Handles source failure (503) with retry + backoff
- Rejects responses > 50 MB
- Rejects XML that would trigger XXE
- Runs sources in parallel (verifiable by timing test with fixtures)
- `scripts/ingest.py --self-test` passes

**Checkpoint:**
```bash
make ingest
python scripts/ingest.py --self-test
pytest tests/test_ingestion.py tests/security/test_parser_safety.py -v
```
Expected: ingest report shows fetched/parsed counts; self-test passes;
parser safety tests pass.

**Risks:**
- Real feeds may have subtle schema differences from docs; mitigate with
  fixture-based tests and clear error messages
- Offline dev environment: fixture mode required

---

## Phase 3 — Change detection 🟢

**Goal:** Compare new documents to stored versions; emit `Change` records.

**Deliverables:**
```
src/compliance_agent/detection/__init__.py
src/compliance_agent/detection/stable_id.py    # per-source ID extraction
src/compliance_agent/detection/diff.py         # structural diff
src/compliance_agent/detection/detector.py     # orchestration
src/compliance_agent/storage/changes.py
scripts/detect.py
scripts/03_detect_selftest.py
tests/test_detection.py
tests/fixtures/detection/before_after_pairs.json
```

**Prevention mechanisms active:**
- **Lesson 3:** Tests assert observable behavior (change records
  produced), not internal function calls

**Acceptance criteria:**
- Extracts stable IDs for each source type (CELEX, list entry ID, URI)
- Detects `new` (no prior version), `amended` (hash differs), `withdrawn`
  (prior exists, current absent)
- Computes deterministic `change_id` (same input → same ID)
- Produces a unified diff for `amended`
- Idempotent: re-running on the same data produces no new changes
- All detection tests pass with fixture pairs

**Checkpoint:**
```bash
make detect
python scripts/detect.py --self-test
pytest tests/test_detection.py -v
```
Expected: change count matches fixture expectations; change_ids are
deterministic across runs.

---

## Phase 4 — Intelligence layer (summarize, map) 🟢

**Goal:** LLM-powered summarization and process mapping, with rate-limit-aware
gateway and prompt injection defense.

**Deliverables:**
```
src/compliance_agent/llm/__init__.py
src/compliance_agent/llm/gateway.py            # rate-limited, retried, fallback
src/compliance_agent/llm/openrouter.py
src/compliance_agent/llm/ollama.py
src/compliance_agent/llm/prompts.py            # versioning + caching
src/compliance_agent/intelligence/__init__.py
src/compliance_agent/intelligence/summarizer.py
src/compliance_agent/intelligence/mapper.py
src/compliance_agent/intelligence/prompts/
    summarize_v1.txt
    map_v1.txt
src/compliance_agent/storage/summaries.py
src/compliance_agent/storage/mappings.py
scripts/process.py
scripts/04_process_selftest.py
tests/test_summarizer.py
tests/test_mapper.py
tests/security/test_prompt_injection.py        # C-05, 10 scenarios
tests/security/test_rate_limit.py
tests/fixtures/kb/                             # mock knowledge base for tests
```

**Prevention mechanisms active:**
- **Lesson 6:** Concurrency via gateway semaphore (C-26)
- **Security:** C-01 to C-05 (prompt injection defense), C-26 to C-28 (rate limits), C-33 to C-35 (local-first preference)

**Acceptance criteria:**
- Gateway enforces max 4 concurrent LLM calls (test verifies with mock)
- On 429, backs off and retries; after 3 consecutive, falls back to Ollama
- Prompt version recorded in every Summary and ProcessMapping
- Untrusted content is fenced; injection attempts fail gracefully (10
  scenarios in `test_prompt_injection.py` all pass)
- Summarizer produces ≤ 200 word summaries with ≥ 1 citation
- Mapper returns ranked list with confidence scores
- LLM cache works: second identical call hits cache
- `scripts/process.py --self-test` passes

**Checkpoint:**
```bash
make process
python scripts/process.py --self-test
pytest tests/test_summarizer.py tests/test_mapper.py tests/security/ -v
```
Expected: summaries and mappings produced; injection tests all pass;
rate-limit metrics logged.

**Risks:**
- Free-tier LLM quality varies; mitigate with conservative prompts and
  human-in-the-loop
- Ollama may not be installed; document as optional, gateway fails over
  to error if neither is available

---

## Phase 5 — Proposals + routing + approval ⚪

**Goal:** Convert mappings into structured proposals; route; enable
human-in-the-loop approval with audit.

**Deliverables:**
```
src/compliance_agent/intelligence/proposer.py
src/compliance_agent/intelligence/prompts/propose_v1.txt
src/compliance_agent/routing/__init__.py
src/compliance_agent/routing/rules.py
src/compliance_agent/routing/router.py
src/compliance_agent/approval/__init__.py
src/compliance_agent/approval/service.py    # approve / edit_approve / reject
src/compliance_agent/approval/state.py      # state machine + optimistic lock
src/compliance_agent/storage/proposals.py
src/compliance_agent/storage/approvals.py
src/compliance_agent/audit/__init__.py
src/compliance_agent/audit/recorder.py
src/compliance_agent/audit/exporter.py
scripts/05_approval_selftest.py
tests/test_proposer.py
tests/test_routing.py
tests/test_approval.py
tests/security/test_approval_integrity.py  # C-21, C-22
tests/fixtures/proposals/                   # sample proposals for tests
```

**Prevention mechanisms active:**
- **Lesson 3:** Tests assert state transitions and audit events
- **Security:** C-18 to C-22 (approval integrity), C-20 (audit in same transaction)

**Acceptance criteria:**
- Proposals match `05_DATA_SPEC.md` §3.5 schema exactly
- Routing follows `configs/routing.yaml`; every decision logged with matched rule
- Approval service writes the state change AND the audit event in one transaction
- Concurrent approval attempts: exactly one succeeds (test with threading)
- Rejected proposals cannot be approved (test)
- Approved proposals cannot be modified (test)
- Audit chain for any proposal is complete (source → change → summary → mappings → proposal → action)
- `scripts/05_approval_selftest.py` passes

**Checkpoint:**
```bash
python scripts/05_approval_selftest.py
pytest tests/test_proposer.py tests/test_routing.py tests/test_approval.py tests/security/test_approval_integrity.py -v
```
Expected: all pass; concurrency test proves single-winner; audit chain test passes.

---

## Phase 6 — Dashboard (Streamlit) ⚪

**Goal:** Three views: live feed, approval queue, change detail with audit trail.

**Deliverables:**
```
src/compliance_agent/dashboard/__init__.py
src/compliance_agent/dashboard/app.py          # entry point
src/compliance_agent/dashboard/state.py
src/compliance_agent/dashboard/views/
    feed.py
    queue.py
    change_detail.py
    audit_trail.py
    digest.py
src/compliance_agent/dashboard/components/
    __init__.py
    header.py
    severity_badge.py
    citation.py
    evidence_list.py
src/compliance_agent/dashboard/charts.py
src/compliance_agent/dashboard/theme.py
scripts/dashboard_selftest.py
tests/test_dashboard_views.py                  # only pure-function tests
```

**Prevention mechanisms active:**
- **Lesson 2:** `scripts/dashboard_selftest.py` verifies each view
  imports and renders from fixtures

**Acceptance criteria:**
- `make serve` starts API + dashboard
- Five views render correctly from fixture data
- Approval actions work end-to-end via the UI
- Change detail view shows: summary, citations, mappings, proposals,
  audit chain
- Latency: view renders in ≤ 2 sec for 500 items (fixture test)
- Empty states handled gracefully

**Checkpoint:**
```bash
make serve &
sleep 5
curl -s http://localhost:8501 | head -20
python scripts/dashboard_selftest.py
pytest tests/test_dashboard_views.py -v
kill %1
```
Expected: dashboard HTML served; selftest passes; view tests pass.

---

## Phase 7 — Evaluation harness ⚪

**Goal:** Implement every metric from `06_EVAL_SPEC.md` with fixtures.

**Deliverables:**
```
src/compliance_agent/evaluation/__init__.py
src/compliance_agent/evaluation/metrics/
    base.py
    detection.py
    summary.py
    mapping.py
    proposal.py
    routing.py
    operational.py
src/compliance_agent/evaluation/runner.py
src/compliance_agent/evaluation/report.py
src/compliance_agent/evaluation/stats.py
src/compliance_agent/evaluation/judge.py
src/compliance_agent/evaluation/judge_prompts/
    entailment_v1.txt
    rubric_v1.txt
src/compliance_agent/evaluation/golden.py      # loader + quality gate
scripts/eval.py
scripts/07_eval_selftest.py
tests/test_metrics.py                          # all fixtures from §9
tests/test_stats.py
tests/test_golden_gate.py
```

**Prevention mechanisms active:**
- **Lesson 3:** Mutation test on one metric per category
- **Lesson 4:** Quality gate runs during curation

**Acceptance criteria:**
- Every metric in `06_EVAL_SPEC.md` §3–§6 implemented
- Every fixture in §9 passes at stated tolerance
- Bootstrap CI computed with seed = 0
- Judge prompts pinned and versioned
- `make eval` produces `results/evals/{timestamp}.json` with all metrics
- Quality gate script refuses a deliberately broken golden entry

**Checkpoint:**
```bash
make eval
python scripts/07_eval_selftest.py
pytest tests/test_metrics.py tests/test_stats.py tests/test_golden_gate.py -v
```
Expected: all fixtures pass; eval report produced; gate test rejects bad entry.

---

## Phase 8 — Ground truth + golden set ⚪

**Goal:** Curate 50+ labeled regulatory changes; validate; commit.

**Deliverables:**
```
data/eval/golden.jsonl                          # ≥ 50 entries
data/eval/raw/g001.xml ... g0NN.xml             # raw content per entry
data/eval/README.md                             # curation rules
scripts/08_seed_golden.py                       # proposes candidates (no LLM)
scripts/08b_validate_golden.py                  # quality gate
tests/test_golden_schema.py
```

**Prevention mechanisms active:**
- **Lesson 4:** Quality gate runs *during* curation, blocks commit on failure
- **ADR-011:** Human-curated, version-controlled

**Acceptance criteria:**
- ≥ 50 entries total (20 new, 20 amended, 10 withdrawn)
- Every entry has: source, raw content path, change_type, expected summary
  rubric, expected mappings, expected proposals, expected severity,
  expected deadline
- Quality gate passes (no duplicates, no fragments, no missing fields,
  all references resolve)
- `data/eval/README.md` documents curation rules

**Checkpoint:**
```bash
python scripts/08b_validate_golden.py
pytest tests/test_golden_schema.py -v
```
Expected: gate passes; schema tests pass.

**Risks:**
- Curation is time-consuming; allow 1.5 days
- Sample source content must be synthetic-cached (not live-fetched) for
  reproducibility

---

## Phase 9 — End-to-end pipeline + demo mode ⚪

**Goal:** Wire all stages together; `make demo` runs the full pipeline
from a fresh clone in ≤ 5 minutes.

**Deliverables:**
```
src/compliance_agent/pipeline.py               # orchestrator
scripts/09_demo.py                             # seed + run + open dashboard
data/demo/                                     # pre-seeded demo data
Makefile                                       # demo target
tests/test_pipeline_integration.py             # end-to-end with mock LLM
```

**Prevention mechanisms active:**
- **Lesson 2:** Integration test verifies every stage's output
- **Lesson 9:** DoD evidence collected automatically

**Acceptance criteria:**
- `make demo` on a fresh clone: seeds data, runs pipeline on 5 pre-scripted
  changes, opens dashboard, all in ≤ 5 minutes
- Integration test runs the pipeline end-to-end with mock LLM (no network)
- Every stage's output is persisted and readable
- Audit chain completes for all demo proposals

**Checkpoint:**
```bash
make demo
pytest tests/test_pipeline_integration.py -v
```
Expected: demo opens in browser; integration test passes.

---

## Phase 10 — Security hardening + Docker ⚪

**Goal:** Implement P1 controls; finalize Docker; verify all security tests.

**Deliverables:**
```
Dockerfile                          # multi-stage, CPU-only torch
docker-compose.yml                  # app + optional ollama (profile)
.github/workflows/ci.yml            # test + pip-audit
.gitattributes
.github/pull_request_template.md
docs/security.md                    # threat model summary (public-facing)
tests/security/                     # complete coverage of C-*
```

**Prevention mechanisms active:**
- **Security:** C-29 to C-37 (dependency pinning, pip-audit, local-first,
  error envelopes)

**Acceptance criteria:**
- All P0 and P1 controls implemented
- All `tests/security/*` pass
- `pip-audit` reports no high-severity vulnerabilities
- `docker compose up` starts the app; dashboard reachable
- `docker compose --profile with-ollama up` starts with local LLM
- CI runs tests + pip-audit on every push

**Checkpoint:**
```bash
pytest tests/security/ -v
pip-audit
docker compose up -d && sleep 10 && curl localhost:8501 | head -5
docker compose down
```
Expected: security tests pass; audit clean; compose starts; dashboard responds.

---

## Phase 11 — Documentation + launch ⚪

**Goal:** Public-facing polish; README; architecture diagram; screenshots;
push to GitHub.

**Deliverables:**
```
README.md                            # public-facing
CONTRIBUTING.md
LICENSE                              # MIT
docs/screenshots/                    # 3 screenshots
docs/architecture.png                # rendered from ASCII
CHANGELOG.md                         # complete
.github/workflows/ci.yml             # badge
docs/demo.md                         # 60-second demo script
```

**Acceptance criteria:**
- README has: TL;DR, results/metrics table, architecture, quick start,
  security summary, evaluation explanation, 30-second pitch, screenshots
- All 11 phases marked 🟢 in this file
- CHANGELOG complete (no gaps)
- CI green
- Repo pushed (private → public when ready)

**Checkpoint:**
```bash
git log --oneline | head -10
gh run list --limit 3
```
Expected: clean history; CI green.

---

## Prevention mechanism checklist (per phase)

Every phase close must verify:

- [ ] `make sync` runs and updates the venv (Lesson 1)
- [ ] `make doctor` reports all imports OK (Lesson 1)
- [ ] Every new module has a `__main__` self-test (Lesson 2)
- [ ] Every new test asserts observable behavior (Lesson 3)
- [ ] Any new dataset passes its quality gate (Lesson 4)
- [ ] Any new write is read back by a test (Lesson 5)
- [ ] Any parallelizable work is parallel (Lesson 6)
- [ ] CHANGELOG updated in the same commit (Lesson 7)
- [ ] No new config sources outside `config/loader.py` (Lesson 8)
- [ ] DoD items checked with evidence (Lesson 9)
- [ ] No ADR contradictions (Lesson 10)

**The phase-tracker agent refuses to close a phase if any box is
unchecked without a documented exception.**

## Definition of Done (project level)

- [ ] All 11 phases marked 🟢
- [ ] All success metrics in `00_DISCOVERY.md` §6 within target
- [ ] All P0 and P1 security controls implemented
- [ ] `make demo` works from a fresh clone in ≤ 5 minutes
- [ ] Test coverage ≥ 85% on core modules
- [ ] CI green; `pip-audit` clean
- [ ] README complete with real numbers
- [ ] Repo pushed to GitHub
