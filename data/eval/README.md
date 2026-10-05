# Evaluation Golden Set — Curation Rules

## Overview

`golden.jsonl` is the human-curated reference dataset for evaluating the compliance monitoring
agent. Each line is a JSON object conforming to the `GoldenEntry` Pydantic model defined in
`src/compliance_agent/evaluation/golden.py`.

## Composition targets (ADR-011)

| change_type | Target count | Minimum |
|-------------|-------------|---------|
| new         | 20          | 18      |
| amended     | 20          | 18      |
| withdrawn   | 10          | 8       |
| **total**   | **50**      | **46**  |

## Field definitions

| Field | Required | Notes |
|-------|----------|-------|
| `id` | Yes | Stable unique identifier, format `g{NNN}` (e.g. `g001`). Never reuse. |
| `source` | Yes | One of `eurlex`, `sanctions`, `eba`. |
| `source_url` | Yes | Canonical URL for the source document. |
| `raw_content_path` | Yes | Relative path from repo root to the raw fixture file under `data/eval/raw/`. |
| `change_type` | Yes | One of `new`, `amended`, `withdrawn`. |
| `previous_content_path` | No | Required for `amended` entries; path to the prior-version fixture. |
| `expected_change_id_components` | Yes | Dict with `source`, `stable_id`, `current_version`. |
| `expected_summary_keywords` | Yes | List of strings that must appear (case-insensitive) in a correct summary. |
| `expected_summary_rubric` | Yes | Free-text grading criteria for LLM-as-judge evaluation. |
| `expected_mappings` | Yes | Empty list is valid for `withdrawn`; otherwise must have ≥ 1 entry. Each entry has `process_id` and `impact_type`. |
| `expected_proposals` | Yes | Empty list is valid for `withdrawn` or `no_impact` cases. |
| `expected_deadline` | No | ISO 8601 date (`YYYY-MM-DD`). Derived from `deadline_offset_days` in the proposal. |
| `expected_severity` | Yes | One of `critical`, `high`, `medium`, `low`. |
| `annotator` | Yes | `"human"` for hand-curated entries; `"synthetic"` for seeded candidates pending review. |
| `annotated_at` | Yes | ISO 8601 datetime. |
| `notes` | No | Curator notes. Not evaluated. |

## Controlled vocabularies

### process_id (valid values)
- `aml`
- `customer_due_diligence`
- `kyc`
- `regulatory_reporting`
- `sanctions_screening`
- `transaction_monitoring`

### impact_type (valid values)
- `add_control`
- `modify_control`
- `add_screening`
- `modify_screening`
- `update_reporting`
- `no_impact`

### severity (valid values)
- `critical` — immediate action required (same-day / next-day deadline)
- `high` — action required within 1–21 days
- `medium` — action required within 22–60 days
- `low` — action required within 61+ days or no action required

## Quality gate rules (validate_golden)

All rules must pass before a golden set is accepted for evaluation runs:

1. **No duplicate IDs** — every `id` must be unique.
2. **No missing required fields** — `id`, `source`, `source_url`, `raw_content_path`, `change_type`.
3. **Non-empty mappings for non-withdrawn** — `expected_mappings` must have ≥ 1 entry unless `change_type == "withdrawn"`.
4. **Non-empty proposals for non-low severity** — if `expected_severity != "low"` and `change_type != "withdrawn"`, `expected_proposals` must have ≥ 1 entry.
5. **Valid process IDs** — every `process_id` in `expected_mappings` must be in the controlled vocabulary.
6. **Raw content paths exist** — each `raw_content_path` (and `previous_content_path`) must resolve to a real file (checked when `check_files=True`).
7. **No malformed JSON** — enforced at load time by Pydantic.
8. **Deadline consistency** — if `expected_deadline` is set and any proposal has `deadline_offset_days`, the deadline must equal `annotated_at.date() + offset_days` (±1 day tolerance for edge cases).

## Raw fixture naming convention

```
data/eval/raw/{source}_{stable_id}_{version}.{ext}
```

Examples:
- `data/eval/raw/eurlex_32024R0811_v1.xml`
- `data/eval/raw/sanctions_EST-2024-0042_v1.xml`
- `data/eval/raw/eba_GL-2024-07_v1.html`

For amended pairs, both versions are present:
- `data/eval/raw/eurlex_32023R0956_v1.xml` — original
- `data/eval/raw/eurlex_32023R0956_v2.xml` — amended

## Adding new entries

1. Place the raw fixture under `data/eval/raw/` following the naming convention.
2. Append a JSON line to `golden.jsonl` with `annotator: "synthetic"`.
3. Run `python scripts/08b_validate_golden.py` to check quality gate.
4. Human reviewer promotes `annotator` to `"human"` after verification.
5. Run `make golden-validate` before any evaluation run.

## Seeding candidates

`scripts/08_seed_golden.py` generates synthetic candidate entries from templates for the
existing raw fixtures. Candidates have `annotator: "synthetic"` and must be reviewed before
use in official evaluation runs.

## Makefile targets

| Target | Action |
|--------|--------|
| `make golden-seed` | Generate synthetic candidates via `08_seed_golden.py` |
| `make golden-validate` | Run quality gate via `08b_validate_golden.py` |
| `make eval` | Run full evaluation (requires validated golden set) |
| `make eval-selftest` | Quick smoke-test with 5-entry mini golden set |
