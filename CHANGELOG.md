# Changelog

All notable changes to the Compliance Monitoring Agent are documented here.
Format: `[phase-N] type(scope): summary` (see CLAUDE.md §9).

---

## [Unreleased]

---

## Phase 11 — Documentation + launch 🟢 (2026-10-05)

### Phase 11 — Documentation + launch
**2026-10-05 — Completed**
- README.md: full public-facing rewrite — TL;DR, architecture diagram,
  agent reasoning steps, evaluation results table (20 metrics from
  results/evals/), security summary (39 controls, STRIDE), quick start,
  design decisions table (18 ADRs), project structure
- CONTRIBUTING.md: setup, commit format, what not to do, PR checklist
- LICENSE: MIT, Victor Daniel
- docs/screenshots/.gitkeep: placeholder directory for UI screenshots
- docs/demo.md: 60-second demo script with talking points and Q&A
- All 11 phases marked 🟢 in claude_chat/08_ROADMAP.md and
  claude_chat/00_START_HERE.md
- CI badge wired in README pointing to .github/workflows/ci.yml
- ADRs applied: ADR-013 (Docker), referenced ADR-001 to ADR-018 in README

---

## Phase 10 — Security hardening + Docker 🟢 (2026-10-05)

### Phase 10 — Security hardening + Docker
**2026-10-05 — Completed**
- Dockerfile: multi-stage build, CPU-only torch, poppler/tesseract/magic
  system deps, image size target < 3 GB
- docker-compose.yml: app service with healthcheck, data/logs/results
  volumes, optional Ollama sidecar via profile
- .dockerignore excludes .env and all generated artifacts
- .github/workflows/ci.yml: test + pip-audit jobs
- .gitattributes: line-ending normalization
- .github/pull_request_template.md: security checklist in PR template
- docs/security.md: public-facing threat model summary
- tests/security/test_error_envelopes.py (C-36, C-37)
- tests/security/test_dependency_pinning.py (C-29, C-30)
- Total tests: 204 + 8 new = 212
- All P0 and P1 controls verified implemented
- ADRs applied: ADR-013
- Dockerfile fix: source copied before editable install; demo/eval data included in runtime image

---

## Phase 9 — End-to-end pipeline + demo mode 🟢 (2026-10-05)

### Phase 9 — End-to-end pipeline + demo mode
**2026-10-05 — Completed**
- src/compliance_agent/pipeline.py — orchestration: ingest -> detect ->
  summarize -> map -> propose -> route; correlation_id per run;
  per-change fail-soft; PipelineReport with per_change list
- data/demo/ — 6 pre-scripted regulatory changes; seed script isolated
  to data/demo/changes/ only
- scripts/09_demo.py — one-command demo: reset DB, seed, run pipeline,
  optionally launch dashboard; --no-serve flag for CI/testing
- tests/test_pipeline_integration.py — 10 tests including pipeline runs
  end-to-end, pipeline does NOT bypass ApprovalService (C-18 guard),
  correlation_id consistency, per_change list matches counter
- Total tests: 204 (up from 194)
- Two real bugs fixed during verification:
  1. changes_detected counter semantics (was counting "newly detected"
     not "changes to process") — fixed by counting all_changes and
     exposing per_change list to prevent structural drift
  2. seed.py created withdrawn changes at version 2 when only version 1
     existed, causing detect() to insert a spurious 'new' change — fixed
     to seed at latest.version with prev_version=None
- ADRs applied: ADR-009 (pipeline creates proposals in pending state;
  no auto-approval)

---

## Phase 8 — Ground truth + golden set 🟢 (2026-10-05)

### Phase 8 — Ground truth + golden set
**2026-10-05 — Completed**
- 15 raw content fixtures under data/eval/raw/ (EUR-Lex XML, EU sanctions
  XML, EBA HTML)
- data/eval/golden.jsonl — 50 entries (20 new / 20 amended / 10 withdrawn)
  authored by Claude Code under human review; annotator field set to
  "claude_code" for honest provenance
- data/eval/README.md — curation rules per 06_EVAL_SPEC.md §2.3
- scripts/08_seed_golden.py — generates synthetic candidates to
  golden_candidates.jsonl (pending human review)
- scripts/08b_validate_golden.py — quality gate runner (11 checks pass)
- tests/test_golden_schema.py — 9 tests
- Makefile: golden-seed, golden-validate targets
- Total tests: 194 (up from 185, +9 Phase 8 tests)
- Fixed: 4 dashboard tests (tests/test_dashboard_views.py) were failing
  at import time because plotly was declared in pyproject.toml but never
  installed in .venv. Cause: pip install -e ".[dev]" skipped already-
  satisfied deps. Fix: make sync now uses --upgrade. Added Lesson 1b to
  01_LESSONS_APPLIED.md.
- ADRs applied: ADR-011

---

## Phase 7 — Evaluation harness 🟢 (2026-10-05)

### Phase 7 — Evaluation harness
**2026-10-05 — Completed**
- 18 new files: Metric ABC + 7 metric modules (20 concrete metrics
  across coverage, summary, mapping, proposal, routing, operational),
  judge + 2 versioned judge prompts, golden loader with quality gate,
  runner, report renderer, bootstrap CI, 2 scripts, 3 test files,
  1 fixture file
- 3 updated files: Makefile (+eval, +eval-selftest), doctor.py
  (+14 modules → 84), eval.yaml
- Total tests: 185 (up from 154, +31 Phase 7 tests)
- Judge uses fence() on all untrusted content (C-01, C-02)
- Judge prompts (entailment_v1, rubric_v1) contain the system preamble
  from _shared_v1.txt; both require UNTRUSTED_SOURCE_CONTENT fencing
- Bootstrap CI: deterministic with seed, works on lists AND numpy,
  raises on empty input
- Golden quality gate catches 8 failure modes
- All 20 metrics from 06_EVAL_SPEC.md §3-§6 implemented and tested
- 06_EVAL_SPEC.md §9 fixtures covered; test naming uses
  actual_detected/actual_missed/actual_perfect/actual_wrong
  (semantically equivalent to spec's perfect_detection / one_missed /
  calibrated_confidence / overconfident)
- ADRs applied: ADR-011, ADR-012, ADR-015

---

## Phase 6 — Dashboard (Streamlit) 🟢 (2026-10-05)

### Phase 6 — Dashboard (Streamlit)
**2026-10-05 — Completed**
- 18 new files: 5 views (feed, queue, change_detail, audit_trail, digest),
  4 components (header, severity_badge, citation, evidence_list),
  app/state/theme/charts modules, dashboard selftest, dashboard views test
- 3 updated files: pyproject.toml (+streamlit, +plotly), Makefile
  (+serve, +dashboard-selftest), doctor.py (+16 dashboard modules → 70)
- Total tests: 154 (up from 144, +10 Phase 6 tests)
- Security control verified: C-18 — approval queue calls ApprovalService,
  never ProposalRepository writes directly
  (test_queue_module_does_not_import_proposal_repository_directly)
- Charts (charts.py) are pure functions — no Streamlit imports; testable
- Approval actions in the UI route through ApprovalService (edit_approve,
  reject); no bypass path exists
- ADRs applied: ADR-009 (human-in-the-loop), ADR-013 (Docker Compose)
- Dashboard selftest covers all 16 modules + 7 pure-function assertions

---

## Phase 5 — Proposals + routing + approval 🟢 (2026-10-05)

### Phase 5 — Proposals + routing + approval
**2026-10-05 — Completed**
- 19 new files: proposer (rules + LLM hybrid), routing (rule engine
  + router), approval (service + state machine), audit (recorder +
  exporter), storage (proposals + approvals repos), selftest, 4 test
  files, 1 fixture
- 5 updated files: exceptions.py (+ApprovalError,
  +ConcurrentModificationError), agent.yaml (+proposer config),
  pyproject.toml (+reportlab), config/models.py
  (+default_deadline_days), doctor.py (+12 modules), Makefile
  (+approve-selftest)
- Total tests: 144 (up from 115, +29 Phase 5 tests)
- Security controls verified in this phase: C-18, C-19, C-20, C-21, C-22
  - C-18: single-writer for proposal state (only ApprovalService mutates)
  - C-19: optimistic locking on every state transition
  - C-20: audit event written in same transaction as state change
  - C-21: concurrent approval test spawns 5 real threads against a
    file-based SQLite DB; exactly 1 winner (BEGIN IMMEDIATE + version lock)
  - C-22: rejected proposal cannot be approved; approved proposal cannot
    be modified (terminal states enforced by state machine)
- ADRs applied: ADR-008, ADR-009, ADR-010
- Rules vs LLM separation verified by empty grep: LLM never produces
  severity or deadline
- Router contains no LLM calls (rules-only)

---

## Phase 4 — Intelligence layer (summarize, map) 🟢 (2026-10-04)

### Phase 4 — Intelligence layer
**2026-10-05 — Completed**
- LLM layer: LLMBackend ABC, LLMGateway (threading.Semaphore(4),
  queue_max 100, jittered backoff, Ollama fallback after 3 consecutive
  429s), OpenRouterBackend, OllamaBackend, PromptRegistry with disk cache
- Intelligence layer: fence() (escape-then-wrap, verified against
  fence-escape attack), index_knowledge_base(), Summarizer
  (citations sourced from doc.content span, never LLM), Mapper
  (top-K retrieval, drops low-confidence / invalid impact / unknown
  section IDs)
- Prompt versioning: _shared_v1.txt, summarize_v1.txt, map_v1.txt;
  prompt_version recorded on every Summary/ProcessMapping
- Storage: SummaryRepository, ProcessMappingRepository
- Knowledge base: 6 process documents indexed in Chroma via MiniLM
- Test infrastructure: FakeLLMBackend with call recording
- Security: 10 prompt-injection scenarios + 5 rate-limit tests, all pass
- Total tests: 115 (up from 90)
- Security controls verified: C-01, C-02, C-03, C-04, C-05, C-26, C-27,
  C-28, C-33, C-34, C-35
- ADRs applied: ADR-004, ADR-014, ADR-015, ADR-016, ADR-018

### [phase-4] feat(intelligence): LLM gateway, summarizer, mapper, prompt injection defense

**2026-10-04 — Completed**
- 30 new files across llm/, intelligence/, storage/, scripts/, tests/, data/
- `llm/`: LLMBackend ABC + LLMResponse, LLMGateway (semaphore, backoff, fallback),
  OpenRouterBackend, OllamaBackend, PromptRegistry with disk cache
- `intelligence/`: fencing (C-01/C-02), KB indexer (Chroma + MiniLM), Summarizer
  (citation-grounded), Mapper (top-K retrieval, confidence/impact/section filtering)
- `intelligence/prompts/`: _shared_v1.txt (system preamble), summarize_v1.txt, map_v1.txt
- `storage/`: SummaryRepository, ProcessMappingRepository
- `data/kb/processes/`: 6 process markdown files (kyc, aml, sanctions_screening,
  regulatory_reporting, customer_due_diligence, transaction_monitoring)
- `tests/mocks/llm.py`: FakeLLMBackend (pre-configured responses, no network)
- `tests/test_summarizer.py` (5 tests), `tests/test_mapper.py` (5 tests)
- `tests/security/test_prompt_injection.py` (10 injection scenarios — all pass)
- `tests/security/test_rate_limit.py` (5 tests: concurrency, queue overflow, retry,
  fail-fast, fallback activation)
- `scripts/04_process.py`, `scripts/04_process_selftest.py` (4 assertions pass)
- Existing files updated: exceptions.py (+LLMUnavailableError), doctor.py (+13 modules → 42),
  Makefile (process, process-selftest targets)
- Test count: 115 (up from 90, +25 Phase 4 tests)

**Checkpoint evidence:**
- `make sync` → OK
- `make doctor` → 42 imports OK
- `make test` → 115 passed
- `make process-selftest` → 4 assertions passed
- `pytest tests/security/test_prompt_injection.py -v` → 10 passed
- `pytest tests/security/test_rate_limit.py -v` → 5 passed
- Lesson 8 grep (`os.getenv`/`os.environ` outside `config/loader.py`) → empty

**Security controls verified:**
- C-01: All external document content wrapped in UNTRUSTED_SOURCE_CONTENT tags
- C-02: fence() escapes embedded tags before wrapping (escape-then-wrap order enforced)
- C-05: 10 injection scenarios tested: wrapping, escaping, containment of 8 attack patterns
- C-26: Gateway semaphore enforces max 4 concurrent LLM calls (threading test passes)
- C-27: Queue overflow (>queue_max_size in-flight) raises RateLimitError immediately
- C-28: Backoff ±20% jitter on 429/503; after 3 consecutive, Ollama fallback armed
- C-33: Local Ollama preferred after primary rate-limit threshold (fallback-first design)
- Citation grounding: quoted_text always extracted from doc.content[span:span], never from LLM output

**Prevention mechanisms active:**
- Lesson 3: All tests assert on Summary/ProcessMapping records, not mock call counts
- Lesson 6: Gateway semaphore baked in from day one (not retrofitted)
- Lesson 8: os.getenv/os.environ still only in config/loader.py (grep → empty)

---

## Phase 3 — Change detection 🟢 (2026-10-04)

### [phase-3] feat(detection): stable ID extraction, unified diff, detector, ChangeRepository

**2026-10-04 — Completed**
- 9 new files: stable_id extraction (CELEX/sanctions/EBA), unified diff,
  detector, ChangeRepository, 2 scripts, 15 tests, 1 fixture file
- Existing files updated: exceptions.py (+StableIDError, DiffError),
  storage/documents.py (+list_stable_ids, list_latest_by_source),
  doctor.py (+5 modules → 29 total), Makefile (detect, detect-selftest)
- Test count: 90 (up from 75, +15 detection tests)
- Verified: deterministic change IDs (sha256[source|stable_id|version][:16]),
  idempotent re-detection, unified diff format, stable ID extraction
  raises StableIDError on failure
- No LLM calls, no network calls — pure data engineering
- Known scope decision: withdrawn change_type is defined in the model but
  not tested in v1 (sources don't reliably provide complete published-ID
  lists). Deferred to v2 with clear mitigation path.

---

## Phase 2 — Ingestion + storage 🟢 (2026-10-04)

### [phase-2] feat(ingestion): source adapters, HTTP fetcher, normalizer, orchestrator, document repository

**Deliverables (21 files + 5 modified):**
- `tests/fixtures/raw/eurlex_sample.xml`, `sanctions_sample.xml`, `eba_sample.html`
- `src/compliance_agent/sources/` — `base.py` (RawDocument + Source ABC), `eurlex.py`, `sanctions.py`, `eba.py`, `registry.py`, `__init__.py`
- `src/compliance_agent/ingestion/` — `fetch.py` (Fetcher with retry/size/fixture), `normalize.py`, `orchestrator.py` (asyncio semaphore=3), `__init__.py`
- `src/compliance_agent/storage/documents.py` — DocumentRepository with idempotent upsert
- `scripts/02_ingest.py`, `scripts/02_ingest_selftest.py`
- `tests/test_ingestion.py`, `tests/test_sources_eurlex.py`, `tests/test_sources_sanctions.py`, `tests/test_sources_eba.py`
- `tests/security/test_parser_safety.py`
- Modified: `exceptions.py` (+SourceParseError), `config/models.py` (+fixture_mode), `configs/sources.yaml` (EBA URL, fixture_mode flag), `scripts/doctor.py` (+11 modules), `Makefile` (ingest/ingest-selftest targets)

**Checkpoint evidence:**
- `make sync` → OK
- `make doctor` → 24 imports OK
- `make test` → 75 passed
- `make ingest-selftest` → all 3 assertions passed
- Lesson 8 grep → empty

**Security controls verified:**
- C-10: defusedxml blocks XXE and billion laughs in EUR-Lex and sanctions XML (4 tests)
- C-11: BeautifulSoup html.parser handles malformed HTML and script injection without crash (2 tests)
- C-12: Fetcher rejects responses > 50 MB before parsing (2 tests)
- C-15: All SQL in DocumentRepository uses parameterized queries only
- C-38, C-39: Fetcher validates source_type against [a-zA-Z0-9_-] before constructing cache path (3 tests)

**Prevention mechanisms active:**
- Lesson 2: `scripts/02_ingest_selftest.py` self-tests all 3 sources + idempotency + read-back
- Lesson 3: Tests assert observable output (stored docs, error types, report counts)
- Lesson 5: `test_document_read_back` and selftest[3] verify write→read round-trip
- Lesson 6: `asyncio.gather` + `Semaphore(3)` baked into orchestrator design
- Lesson 8: `os.getenv`/`os.environ` still only in `config/loader.py` (grep → empty)

---

## Phase 1 — Scaffolding + safety rails 🟢 (2026-10-04)

### [phase-1] feat(scaffolding): initial project scaffold with safety rails

**Deliverables (36 files):**
- `pyproject.toml` with pinned dependencies; `requirements.lock` (123 packages)
- `.env.example`, `.gitignore`, `.pre-commit-config.yaml` (detect-secrets + CHANGELOG hook)
- `Makefile` with sync/doctor/test/selftest targets and phase stubs
- `docker-compose.yml` and `Dockerfile` stubs (finalized Phase 10)
- `src/compliance_agent/config/` — loader (sole `os.getenv`/`os.environ` caller), Pydantic models
- `src/compliance_agent/utils/` — structlog JSON logging with secret scrubber, IDs (ULID + sha256), rate-limit (token bucket + backoff)
- `src/compliance_agent/exceptions.py` — typed exception hierarchy
- `src/compliance_agent/storage/` — SQLite connection + idempotent migrations, Pydantic entity models (all 05_DATA_SPEC §3 entities), append-only audit repository
- `configs/` — sources.yaml, agent.yaml, routing.yaml, eval.yaml
- `scripts/doctor.py`, `scripts/selftest.py`, `scripts/check_changelog.py`
- `tests/` — test_config.py, test_logging.py, test_ids.py
- `tests/security/` — test_secret_scrubbing.py (6 tests), test_audit_immutability.py (8 tests)
- `claude_chat/00_START_HERE.md` — project status dashboard

**Checkpoint evidence:**
- `make sync` → OK
- `make doctor` → 13 imports OK
- `make test` → 37 passed
- `make selftest` → 5 module self-tests passed
- Lesson 8 grep (`os.getenv`/`os.environ` outside `config/loader.py`) → empty
- `pre-commit run detect-secrets --all-files` → Passed

**Prevention mechanisms active:**
- Lesson 1: `make sync` + `make doctor` targets in place
- Lesson 5: `tests/test_logging.py` reads back `logs/app.jsonl` (verified write → read)
- Lesson 7: CHANGELOG pre-commit hook enforced; updated in same commit
- Lesson 8: `config/loader.py` is the only `os.getenv`/`os.environ` caller; `get_secret_env_values()` exported for scrubber

**Security controls verified:**
- C-06, C-07, C-08: secret scrubber wired at structlog config level; 6 tests confirm `sk-or-*`, `sk-ant-*`, `sk-*`, `Bearer *`, and env var secrets are all redacted to `[REDACTED]`
- C-23, C-24, C-25: `AuditRepository` exposes only `append()` and `query()`; SQLite `BEFORE UPDATE` and `BEFORE DELETE` triggers raise `ABORT`; 8 tests confirm both repository contract and direct-SQL rejection
