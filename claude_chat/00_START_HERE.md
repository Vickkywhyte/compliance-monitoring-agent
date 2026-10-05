# Start Here — Compliance Monitoring Agent

Quick reference for the current project state. Full details in `08_ROADMAP.md`.

## Phase status

| # | Phase | Status | Notes |
|---|---|---|---|
| 1 | Scaffolding + safety rails | 🟢 Complete | Phase 2 next |
| 2 | Ingestion + storage | 🟢 Complete | Phase 3 next |
| 3 | Change detection | 🟢 Complete | Phase 4 next |
| 4 | Intelligence layer (summarize, map) | 🟢 Complete | Phase 5 next |
| 5 | Proposals + routing + approval | 🟢 Complete | Phase 6 next |
| 6 | Dashboard (Streamlit) | 🟢 Complete | Phase 7 next |
| 7 | Evaluation harness | 🟢 Complete | Phase 8 next |
| 8 | Ground truth + golden set | 🟢 Complete | Phase 9 next |
| 9 | End-to-end pipeline + demo mode | 🟢 Complete | Phase 10 next |
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
