## Summary

<!-- 1-3 bullet points describing what this PR does. -->

## Test plan

- [ ] `make sync && make doctor` passes
- [ ] `make test` passes (all tests, `not llm` marker)
- [ ] `pytest tests/security/ -v` passes

## Security checklist

- [ ] No new hardcoded secrets (ran `grep -rn "sk-\|password\|token" src/`)
- [ ] No new `os.getenv` outside `config/loader.py`
- [ ] No new raw SQL outside `storage/` (parameterized queries only)
- [ ] No new `eval` / `exec` / `shell=True`
- [ ] All new LLM prompts wrap untrusted content in fences (C-01, C-02)
- [ ] Any new state transitions write to `audit_events` in the same transaction (C-20)
- [ ] No `.env` file staged or committed

## CHANGELOG

- [ ] `CHANGELOG.md` updated if `src/` or `scripts/` changed (Lesson 7)

## Phase

<!-- Which phase does this belong to? (e.g. Phase 9 — pipeline orchestration) -->
