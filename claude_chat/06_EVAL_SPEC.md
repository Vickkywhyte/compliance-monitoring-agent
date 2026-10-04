# Evaluation Specification — Compliance Monitoring Agent

> **READ THIS FIRST (for Claude Code):**
> This document defines every metric in the system. A metric is not real
> until it is (a) defined here with a formula, (b) implemented as a
> `Metric` subclass, (c) tested against hand-crafted fixtures, and (d)
> referenced from the eval report. Do not add a metric without updating
> this doc first. Do not change a formula without writing a new version
> and bumping the schema.
>
> **Dependencies:** `00_DISCOVERY.md` (§2, §6) · `02_PRD.md` (FR-12) ·
> `05_DATA_SPEC.md` (schemas) · `04_TECH_DECISIONS.md` (ADR-011, ADR-012)
> **Depended on by:** `08_ROADMAP.md` (Phase 7) · `09_AGENT_DESIGN.md`

---

## 1. Evaluation philosophy

The agent has six stages: **ingest, detect, summarize, map, propose,
route.** A failure in any stage propagates. A single end-to-end metric
would hide where things went wrong.

**Therefore:** every stage is measured independently. Additionally, we
measure the pipeline as a whole (proposal quality) to catch interaction
failures.

**Every metric maps to one of three questions** from `00_DISCOVERY.md` §2:

| Question | Metrics |
|---|---|
| Coverage — did we see everything? | detection_recall, detection_precision |
| Accuracy — did we interpret correctly? | summary_faithfulness, summary_hallucination_rate, mapping_precision, mapping_recall, confidence_brier |
| Action quality — did we propose correctly? | proposal_acceptance_rate, routing_accuracy, deadline_accuracy |

## 2. Golden set

### 2.1 Schema (per line, `data/eval/golden.jsonl`)

```json
{
  "id": "g001",
  "source": "sanctions",
  "source_url": "https://webgate.ec.europa.eu/...",
  "raw_content_path": "data/eval/raw/g001.xml",
  "change_type": "new",
  "previous_content_path": null,
  "expected_change_id_components": {
    "source": "sanctions",
    "stable_id": "EU.1234.56",
    "current_version": 1
  },
  "expected_summary_keywords": [
    "sanctions", "asset freeze", "entry into force"
  ],
  "expected_summary_rubric": "Must mention the entity name, the sanctions type, and the effective date. Must cite the official source.",
  "expected_mappings": [
    {"process_id": "sanctions_screening", "impact_type": "add_screening"},
    {"process_id": "transaction_monitoring", "impact_type": "modify_screening"}
  ],
  "expected_proposals": [
    {
      "assignee_role": "mlro",
      "category": "screening_update",
      "severity": "critical",
      "deadline_offset_days": 0,
      "rationale_keywords": ["immediate", "sanctions", "list update"]
    }
  ],
  "expected_deadline": "2024-06-01",
  "expected_severity": "critical",
  "annotator": "human",
  "annotated_at": "2026-10-04T12:00:00Z",
  "notes": "Sanctions addition for entity X, effective immediately"
}
```

### 2.2 Composition rules

| Category | Minimum | Purpose |
|---|---|---|
| `new` changes | 20 | Detect additions |
| `amended` changes | 20 | Detect modifications (harder) |
| `withdrawn` changes | 10 | Detect removals |
| **Total** | **≥ 50** | |

### 2.3 Curation process

1. Historical changes are selected from a 90-day window of real EUR-Lex
   and sanctions list activity.
2. For each, an annotator (human) records:
   - The change (type + diff)
   - An operational summary rubric (not verbatim; a checklist of what
     must be present)
   - Expected process mappings
   - Expected proposals
   - Expected deadline and severity
3. A second annotator reviews (or the same annotator after 24 hours).
4. The quality gate runs during curation, not after (Lesson 4).

### 2.4 Quality gate

Runs during curation and on every commit that touches `golden.jsonl`.
Fails on:

- Duplicate `id`s
- Missing required fields
- `expected_mappings` empty when `change_type != "withdrawn"` (every
  non-withdrawal should map to at least one process, even if only
  `no_impact`)
- `expected_proposals` empty when `expected_severity != "low"`
- References to non-existent process IDs
- `raw_content_path` missing or file not found
- Malformed JSON
- `expected_deadline` inconsistent with `deadline_offset_days`

**Committed golden set must pass the gate.** Any commit that breaks the
gate is rejected by CI.

## 3. Coverage metrics (Question 1)

### 3.1 Detection recall

```
recall = TP / (TP + FN)
```

Where:
- **TP** (true positive): a change in the golden set that the detector
  correctly identified
- **FN** (false negative): a change in the golden set that the detector
  missed

Matching is by `stable_id` + `change_type`.

**Target:** ≥ 0.95

### 3.2 Detection precision

```
precision = TP / (TP + FP)
```

Where **FP** (false positive) is a change the detector emitted that is
not in the golden set.

**Target:** ≥ 0.90

**Note:** A high FP rate is not fatal (the human will reject spurious
proposals), but it erodes trust. We aim for both high precision and high
recall.

## 4. Accuracy metrics (Question 2)

### 4.1 Summary faithfulness

Reuses the hallucination methodology from the prior RAG project
(claim decomposition + per-claim entailment).

```
faithfulness = (# claims entailed by source content)
             / (# claims in summary)
```

**Method:**
1. Decompose the summary into atomic claims (LLM, temperature=0)
2. For each claim, ask an LLM judge: is this entailed by the source
   document?
3. `faithfulness` = entailed / total

**Target:** ≥ 0.90

### 4.2 Summary hallucination rate

```
hallucination_rate = (# claims NOT entailed by source content)
                   / (# claims in summary)
```

This is the complement of faithfulness with one difference: "partial"
verdicts count as 0.5 hallucinated.

**Target:** ≤ 0.05

**Gate:** summaries with hallucination_rate > 0.05 are flagged
`low_confidence=True` and do not block downstream processing, but are
routed to the compliance analyst regardless of severity.

### 4.3 Mapping precision

```
precision = (# mappings that match the golden set)
          / (# mappings emitted)
```

Matching rule: a mapping matches if both `process_id` AND `impact_type`
match a golden entry.

**Target:** ≥ 0.80

### 4.4 Mapping recall

```
recall = (# mappings that match the golden set)
       / (# mappings in the golden set)
```

**Target:** ≥ 0.75

**Note:** recall is intentionally lower than precision. It is better to
miss a mapping than to produce a spurious one, because the human can add
a missed mapping but has limited time to remove spurious ones.

### 4.5 Confidence calibration (Brier score)

```
Brier = mean((confidence - correctness)^2)
```

Where `correctness` is 1 if the mapping matched, 0 otherwise.

**Target:** ≤ 0.15

Lower is better. Brier < 0.15 means the model's confidence roughly
matches reality.

### 4.6 Summary rubric adherence

An LLM judge evaluates whether the summary satisfies the rubric in the
golden entry.

```
rubric_score = mean(judge_score) / 5     # normalized to [0, 1]
```

Judge prompt asks: "Does the summary contain [rubric elements]? Score
1–5."

**Target:** ≥ 0.80

## 5. Action quality metrics (Question 3)

### 5.1 Proposal acceptance rate

Measured against the golden set with simulated human reviewers (or via
a scripted approval process for evaluation runs only).

```
acceptance_rate = (# proposals approved without edit)
                / (# proposals in the golden set)
```

**Target:** ≥ 0.75

### 5.2 Proposal edit rate

```
edit_rate = (# proposals approved with edit)
          / (# proposals)
```

**Target:** ≤ 0.20

### 5.3 Proposal rejection rate

```
rejection_rate = (# proposals rejected)
               / (# proposals)
```

**Target:** ≤ 0.05

### 5.4 Routing accuracy

```
routing_accuracy = (# proposals routed to the correct role)
                 / (# proposals)
```

Correct role comes from the golden set's expected `assignee_role`.

**Target:** ≥ 0.90

### 5.5 Deadline accuracy

```
deadline_accuracy = (# proposals whose deadline is within ±1 day of golden)
                  / (# proposals with a golden deadline)
```

**Target:** ≥ 0.85

### 5.6 Severity accuracy

```
severity_accuracy = (# proposals with correct severity)
                  / (# proposals)
```

**Target:** ≥ 0.85

## 6. Operational metrics

| Metric | Definition | Target |
|---|---|---|
| `e2e_latency_p50_ms` | Median time from change detection to proposal stored | ≤ 60,000 |
| `e2e_latency_p95_ms` | 95th percentile | ≤ 120,000 |
| `cost_per_1k_changes_usd` | Extrapolated cost of LLM calls per 1,000 changes | 0.00 |
| `llm_fallback_rate` | Fraction of LLM calls falling back to Ollama | ≤ 0.20 |
| `llm_rate_limit_hits` | Count of HTTP 429 responses | tracked |
| `audit_completeness` | Fraction of proposals with a complete audit chain | 1.00 |
| `approval_bypass_rate` | Fraction of proposals executing without approval (must be 0) | 0.00 |

## 7. Aggregate reporting

Every evaluation run produces `results/evals/{timestamp}.json` containing:

```json
{
  "eval_id": "20261004T140000_eval",
  "golden_set_hash": "abc123...",
  "run_at": "2026-10-04T14:00:00Z",
  "n_golden_entries": 50,
  "metrics": {
    "detection_recall": 0.96,
    "detection_precision": 0.92,
    "summary_faithfulness": 0.93,
    "summary_hallucination_rate": 0.04,
    "mapping_precision": 0.82,
    "mapping_recall": 0.77,
    "confidence_brier": 0.13,
    "summary_rubric_score": 0.84,
    "proposal_acceptance_rate": 0.78,
    "proposal_edit_rate": 0.17,
    "proposal_rejection_rate": 0.05,
    "routing_accuracy": 0.91,
    "deadline_accuracy": 0.87,
    "severity_accuracy": 0.88,
    "e2e_latency_p50_ms": 34210,
    "e2e_latency_p95_ms": 78902,
    "cost_per_1k_changes_usd": 0.0,
    "llm_fallback_rate": 0.11,
    "llm_rate_limit_hits": 34,
    "audit_completeness": 1.0,
    "approval_bypass_rate": 0.0
  },
  "per_entry": [
    {
      "golden_id": "g001",
      "detected": true,
      "summary_faithfulness": 0.95,
      "mappings_matched": 2,
      "mappings_expected": 2,
      "proposals_generated": 1,
      "proposal_accepted": true,
      "routing_correct": true,
      "deadline_accurate": true
    }
  ],
  "aggregate_ci": {
    "detection_recall": [0.92, 0.99],
    "mapping_precision": [0.76, 0.88]
  }
}
```

## 8. Statistical hygiene

- **Confidence intervals:** bootstrap 1,000 samples, 95% interval. Reported
  on all aggregate metrics where n ≥ 20.
- **Determinism:** all judge calls at temperature=0; LLM cache applied;
  seed fixed.
- **Judge versioning:** judge prompt recorded in every run; versioned as
  `judge_*_v{N}.txt`.
- **No claims below CI width:** if two metrics differ by less than the CI
  half-width, we do not claim one is better.

## 9. Test fixtures

`tests/test_metrics.py` must contain these fixtures. Each asserts a metric
value within tolerance:

| Fixture | Setup | Expected |
|---|---|---|
| `perfect_detection` | 5/5 golden detected, 0 FPs | recall=1.0, precision=1.0 |
| `one_missed` | 4/5 detected | recall=0.8 |
| `one_false_positive` | 5/5 detected, 1 FP | precision=0.833 |
| `perfect_summary` | All claims entailed | faithfulness=1.0 |
| `one_hallucination` | 1/5 claims unsupported | hallucination=0.2 |
| `perfect_mappings` | All map to golden | precision=1.0, recall=1.0 |
| `spurious_mapping` | 1 extra mapping | precision<1.0 |
| `missed_mapping` | 1 golden missed | recall<1.0 |
| `calibrated_confidence` | Predicted 0.9, correct 90% of time | Brier ≤ 0.02 |
| `overconfident` | Predicted 0.9, correct 50% | Brier ≥ 0.10 |
| `perfect_routing` | All correct | routing_accuracy=1.0 |
| `all_approved` | All approved without edit | acceptance=1.0 |
| `audit_complete` | Full chain for all proposals | audit_completeness=1.0 |
| `audit_broken` | Missing event | audit_completeness<1.0 |

Any metric shipped without fixtures is a **blocker**.

## 10. Evaluation run

```bash
make eval
```

Steps:
1. Verify golden set integrity (quality gate)
2. Reset evaluation database (separate from production db)
3. For each golden entry:
   - Run ingestion on the raw content
   - Run detection
   - Run summarization
   - Run mapping
   - Run proposal generation
   - Run routing
   - Simulate human review (scripted for eval only)
4. Compute metrics
5. Bootstrap CIs
6. Write `results/evals/{timestamp}.json`
7. Print a summary table

Wall clock estimate: 20–40 minutes for 50 entries (dominated by LLM calls).

Cost: $0 (free tier + Ollama fallback).

## 11. Regression policy

- Every PR that touches `intelligence/`, `detection/`, or `routing/` must
  run `make eval` and include the diff in the PR description.
- Metrics that drop more than the CI half-width are flagged and must be
  justified.
- The golden set is versioned; changing it requires a new eval baseline.

## 12. What this spec does NOT do

- Does not measure end-user satisfaction (no real users in v1)
- Does not evaluate tone, style, or readability
- Does not measure security (that's `07_SECURITY_MODEL.md`)
- Does not replace human review — evaluation runs use *simulated*
  approvers, not real ones
- Does not measure long-term drift (single-shot evaluation only)

## 13. Sign-off checklist for Phase 7 (eval implementation)

- [ ] All metrics implemented as `Metric` subclasses
- [ ] All §9 fixtures pass at the stated tolerance
- [ ] Golden set passes the quality gate
- [ ] `make eval` produces a complete report
- [ ] Bootstrap CIs computed and stored
- [ ] Report rendered in a human-readable summary table
- [ ] Judge prompts pinned and versioned
- [ ] LLM cache working (second run is faster and cheaper)
- [ ] Any deviation from this spec captured as a new ADR