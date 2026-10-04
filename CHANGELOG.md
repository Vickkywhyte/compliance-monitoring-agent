# Changelog

All notable changes to the Compliance Monitoring Agent are documented here.
Format: `[phase-N] type(scope): summary` (see CLAUDE.md §9).

---

## [Unreleased]

### [phase-1] feat(scaffolding): initial project scaffold with safety rails

**Deliverables:**
- `pyproject.toml` with pinned dependencies
- `.env.example`, `.gitignore`, `.pre-commit-config.yaml`
- `Makefile` with sync/doctor/test/selftest targets and phase stubs
- `docker-compose.yml` and `Dockerfile` stubs (finalized Phase 10)
- `src/compliance_agent/config/` — loader (sole os.getenv caller), Pydantic models
- `src/compliance_agent/utils/` — structlog logging with secret scrubber, IDs, rate-limit
- `src/compliance_agent/exceptions.py` — typed exception hierarchy
- `src/compliance_agent/storage/` — db migrations, Pydantic entity models, audit repository
- `configs/` — sources, agent, routing, eval YAML configs
- `scripts/doctor.py`, `scripts/selftest.py`
- `tests/` — config, logging, IDs, security (secret scrubbing, audit immutability)

**Prevention mechanisms active:**
- Lesson 1: `make sync` + `make doctor`
- Lesson 5: `tests/test_logging.py` reads back `logs/app.jsonl`
- Lesson 7: CHANGELOG updated in same commit
- Lesson 8: `config/loader.py` is the only `os.getenv` caller
- Security: C-06 to C-09 (secret scrubber), C-23 to C-25 (audit immutability), C-29 to C-30 (pinned deps)
