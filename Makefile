.PHONY: sync doctor test selftest clean clean-cache clean-data \
        ingest ingest-selftest detect detect-selftest \
        process process-selftest eval demo serve lock

# Prefer the activated venv's pip; fall back to the Homebrew Python 3.11
PIP ?= $(shell command -v pip || echo /opt/homebrew/opt/python@3.11/bin/pip3.11)
PYTHON ?= $(shell command -v python || echo /opt/homebrew/opt/python@3.11/bin/python3.11)

# ── Phase 1: foundation ─────────────────────────────────────────────────────

sync:
	$(PIP) install -e ".[dev]"

lock:
	pip freeze > requirements.lock

doctor:
	$(PYTHON) scripts/doctor.py

test:
	$(PYTHON) -m pytest tests/ -q -m "not llm"

selftest:
	$(PYTHON) scripts/selftest.py

# ── Cleanup ──────────────────────────────────────────────────────────────────

clean: clean-cache clean-data
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	find . -name "*.egg-info" -type d -exec rm -rf {} + 2>/dev/null || true

clean-cache:
	rm -rf .pytest_cache .ruff_cache .mypy_cache
	rm -rf data/cache/

clean-data:
	rm -rf data/raw/ data/chroma/ data/compliance.db
	rm -rf logs/ results/

# ── Phase 2: ingestion ───────────────────────────────────────────────────────

ingest:
	$(PYTHON) scripts/02_ingest.py

ingest-selftest:
	$(PYTHON) scripts/02_ingest_selftest.py

# ── Phase 3: detection ───────────────────────────────────────────────────────

detect:
	$(PYTHON) scripts/03_detect.py

detect-selftest:
	$(PYTHON) scripts/03_detect_selftest.py

# ── Phase 4: intelligence layer ─────────────────────────────────────────────

process:
	$(PYTHON) scripts/04_process.py

process-selftest:
	$(PYTHON) scripts/04_process_selftest.py

eval:
	@echo "ERROR: 'make eval' is not implemented yet (Phase 7)." && exit 1

demo:
	@echo "ERROR: 'make demo' is not implemented yet (Phase 9)." && exit 1

serve:
	@echo "ERROR: 'make serve' is not implemented yet (Phase 6)." && exit 1
