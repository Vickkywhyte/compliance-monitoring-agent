.PHONY: sync doctor test selftest clean clean-cache clean-data \
        ingest ingest-selftest detect detect-selftest \
        process process-selftest approve-selftest dashboard-selftest \
        eval eval-selftest golden-seed golden-validate demo serve lock

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

# ── Phase 5: proposals + routing + approval ──────────────────────────────────

approve-selftest:
	$(PYTHON) scripts/05_approve_selftest.py

# ── Phase 6: dashboard ────────────────────────────────────────────────────────

dashboard-selftest:
	$(PYTHON) scripts/dashboard_selftest.py

eval:
	$(PYTHON) scripts/07_eval.py --fixture-llm --skip-file-checks \
		--golden data/eval/golden.jsonl

eval-selftest:
	$(PYTHON) scripts/07_eval_selftest.py

# ── Phase 8: golden set curation ─────────────────────────────────────────────

golden-seed:
	$(PYTHON) scripts/08_seed_golden.py

golden-validate:
	$(PYTHON) scripts/08b_validate_golden.py

demo:
	python scripts/09_demo.py --reset

serve:
	streamlit run src/compliance_agent/dashboard/app.py \
		--server.port 8501 --server.address 0.0.0.0
