# Start Here — Compliance Monitoring Agent

Quick reference for the current project state. Full details in `08_ROADMAP.md`.

## Phase status

| # | Phase | Status | Notes |
|---|---|---|---|
| 1 | Scaffolding + safety rails | 🟢 Complete | Phase 2 next |
| 2 | Ingestion + storage | 🟢 Complete | Phase 3 next |
| 3 | Change detection | 🟢 Complete | Phase 4 next |
| 4 | Intelligence layer (summarize, map) | 🟢 Complete | Phase 5 next |
| 5 | Proposals + routing + approval | ⚪ Not started | |
| 6 | Dashboard (Streamlit) | ⚪ Not started | |
| 7 | Evaluation harness | ⚪ Not started | |
| 8 | Ground truth + golden set | ⚪ Not started | |
| 9 | End-to-end pipeline + demo mode | ⚪ Not started | |
| 10 | Security hardening + Docker | ⚪ Not started | |
| 11 | Documentation + launch | ⚪ Not started | |

## Last checkpoint (Phase 1)

```
make sync      → OK (all dependencies installed)
make doctor    → 13 imports OK
make test      → 37 passed
make selftest  → 5 module self-tests passed
Lesson 8 grep  → empty (os.getenv/os.environ only in config/loader.py)
detect-secrets → Passed
```

## Next action

Start Phase 2 — Ingestion + storage. Read `08_ROADMAP.md` Phase 2 section
before writing any code.
