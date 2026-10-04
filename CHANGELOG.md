# Changelog

All notable changes to the Compliance Monitoring Agent are documented here.
Format: `[phase-N] type(scope): summary` (see CLAUDE.md §9).

---

## [Unreleased]

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
