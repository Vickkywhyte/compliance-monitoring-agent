# Changelog

All notable changes to the Compliance Monitoring Agent are documented here.
Format: `[phase-N] type(scope): summary` (see CLAUDE.md §9).

---

## [Unreleased]

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
