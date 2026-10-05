# Contributing

This is a portfolio project. External contributions are welcome for bug fixes and documentation improvements.

## Ground rules

- Read [`claude_chat/CLAUDE.md`](claude_chat/CLAUDE.md) before touching code. It is the operating manual.
- Do not contradict a locked ADR. Propose a new one (ADR-019+) and flag it in the PR.
- Do not weaken a P0 security control. See [`claude_chat/07_SECURITY_MODEL.md`](claude_chat/07_SECURITY_MODEL.md).
- Every PR that changes `src/` or `scripts/` must update `CHANGELOG.md` in the same commit.

## Setup

```bash
git clone https://github.com/Vickkywhyte/compliance-monitoring-agent.git
cd compliance-monitoring-agent
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
make sync
make doctor          # all imports OK
make test            # all tests pass
```

## Before you open a PR

```bash
make sync && make doctor   # dependency check
make test                  # full test suite (excludes live LLM)
pytest tests/security/ -v  # security controls
```

Use the PR template at `.github/pull_request_template.md`. It includes a security checklist.

## Commit format

```
[phase-N] type(scope): summary

Co-Authored-By: Your Name <email>
```

Types: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`, `eval`, `sec`

## What not to do

- No `print()` in application code — use `structlog`
- No `os.getenv` outside `config/loader.py`
- No raw SQL outside `storage/`
- No `eval`, `exec`, or `shell=True`
- No new metric without updating `claude_chat/06_EVAL_SPEC.md` and adding a test
- No committing `.env` or any file under `data/raw/`

## Questions

Open an issue. The planning documents in `claude_chat/` contain the full context for every design decision.
