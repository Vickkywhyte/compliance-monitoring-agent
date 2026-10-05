# Demo Data

Pre-scripted regulatory changes for the Phase 9 end-to-end demo. Six entries
cover every change type and source combination so the full pipeline is
exercised without live network calls.

## Contents

| File | Source | Type | Description |
|------|--------|------|-------------|
| `demo_001.json` | eurlex | new | EU AML Regulation 2024/811 — customer due diligence |
| `demo_002.json` | sanctions | new | Synthetix Trading Corp — Ukraine asset freeze |
| `demo_003.json` | eurlex | amended | Transaction monitoring thresholds cut (32023R0956) |
| `demo_004.json` | eba | amended | CDD risk factors with crypto section (EBA/GL/2022/11) |
| `demo_005.json` | sanctions | withdrawn | Dmitri Volkov — delisted, asset freeze lifted |
| `demo_006.json` | eba | new | Beneficial ownership register RTS (EBA/RTS/2024/03) — low-confidence edge case |

## Usage

```bash
# Seed demo data manually
python data/demo/seed.py

# Run the full demo pipeline (seeds + runs + opens dashboard)
python scripts/09_demo.py --reset

# Skip Streamlit, just run the pipeline
python scripts/09_demo.py --reset --no-serve
```

## Schema

Each JSON file contains:
- `id` — unique demo identifier
- `source` — one of `eurlex`, `sanctions`, `eba`
- `stable_id` — document stable identifier
- `change_type` — `new`, `amended`, or `withdrawn`
- `raw_content` — raw XML or HTML content fed to the pipeline
- `previous_raw_content` — prior version content (amended entries only)
- `expected_summary_keywords` — used in integration tests
- `expected_mappings` — expected process mappings
