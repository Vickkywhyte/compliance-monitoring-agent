# Compliance Monitoring Agent

> An autonomous agent that watches EU regulatory feeds (sanctions, AML),
> detects changes, maps them to internal business processes, and proposes
> action items to human approvers — with a multi-stage evaluation
> framework, a full security threat model, and a complete audit trail.
> **$0 to run.**

[![CI](https://github.com/Vickkywhyte/compliance-monitoring-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/Vickkywhyte/compliance-monitoring-agent/actions/workflows/ci.yml)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue)]()
[![License: MIT](https://img.shields.io/badge/license-MIT-green)]()

---

## TL;DR

Most compliance AI is a black box. This one isn't.

It ingests regulatory feeds from EUR-Lex, the EU sanctions list, and the
EBA. It detects what changed, summarizes it in plain language with
citations, maps it to the firm's documented business processes, and
proposes structured action items to a human approver. Every proposal is
traceable from the source document to the approval action.

**Three differentiators:**

1. **Six-stage evaluation** — coverage, accuracy, and action quality
   measured at every stage, not just end-to-end.
2. **Full audit trail** — append-only, database-enforced immutability.
3. **$0 to run** — free-tier LLM + Ollama fallback. No paid services.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│           EXTERNAL SOURCES                                  │
│  EUR-Lex · EU Sanctions List · EBA                          │
└──────────────────────┬──────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ INGESTION  →  DETECTION  →  INTELLIGENCE                    │
│                                                             │
│  fetch        diff         summarize (LLM + cite)           │
│  normalize    stable ID    map (retrieval + LLM)            │
│  persist      emit change  propose (rules + LLM)            │
└──────────────────────┬──────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ ROUTING  →  HUMAN-IN-THE-LOOP  →  AUDIT                     │
│                                                             │
│  rules     approve / edit+approve / reject                 │
│            every action recorded, append-only               │
└─────────────────────────────────────────────────────────────┘

       ┌──────────────────────────────────────┐
       │  PERSISTENCE (local, $0)             │
       │  SQLite · Chroma · Filesystem        │
       └──────────────────────────────────────┘

       ┌──────────────────────────────────────┐
       │  EVALUATION HARNESS (parallel)       │
       │  6 stages · 14 metrics · bootstrap CI│
       └──────────────────────────────────────┘
```

Full architecture in [`claude_chat/03_ARCHITECTURE.md`](claude_chat/03_ARCHITECTURE.md).

## The agent in three steps

**Step 1 — Summarize.** A regulatory change becomes a ≤ 200-word plain-
language summary. Every factual claim is cited to a specific span of the
source document.

**Step 2 — Map.** The summary and change are used to retrieve relevant
sections of the firm's knowledge base. The LLM ranks each (process,
impact_type, confidence, rationale). Every mapping cites the specific KB
section it derives from.

**Step 3 — Propose.** Rules (severity, deadline, routing) and LLM
(title, description, rationale) combine to produce structured action
items. Each proposal cites the change and the mappings it derives from.

The LLM never decides severity, deadline, or routing — those come from
rules. This keeps the highest-impact decisions auditable.

The agent never executes an action. A human always approves.

## Evaluation — the differentiator

The pipeline has **six stages** (ingest, detect, summarize, map, propose,
route). A failure in any one propagates. We measure every stage
independently.

| Metric group | Metrics |
|---|---|
| **Coverage** | detection_recall, detection_precision |
| **Accuracy** | summary_faithfulness, summary_hallucination_rate, mapping_precision, mapping_recall, confidence_brier |
| **Action quality** | proposal_acceptance_rate, routing_accuracy, deadline_accuracy, severity_accuracy |
| **Operational** | e2e_latency, cost, llm_fallback_rate, audit_completeness, approval_bypass_rate |

Every metric has a target, a formula, and a hand-crafted test fixture.
Bootstrap 95% CIs are computed on all aggregates.

Full spec in [`claude_chat/06_EVAL_SPEC.md`](claude_chat/06_EVAL_SPEC.md).

## Security

A full STRIDE threat model with **39 controls** (P0 and P1). Highlights:

- **Prompt injection defense** — untrusted content is fenced and labeled;
  all outputs are validated against a controlled vocabulary.
- **Secret scrubbing** — a logger processor redacts anything matching
  secret patterns before it hits disk.
- **Append-only audit** — enforced at the repository *and* the SQLite
  level (UPDATE/DELETE rejected by triggers).
- **Approval integrity** — optimistic locking prevents double-approval;
  rejected proposals cannot be re-approved.
- **Rate-limit defense** — bounded queue, exponential backoff, automatic
  fallback to local inference.

Full spec in [`claude_chat/07_SECURITY_MODEL.md`](claude_chat/07_SECURITY_MODEL.md).

## Results

*Populated after `make eval` runs against the golden set. Placeholder
format:*

| Metric | Value | Target |
|---|---|---|
| Detection recall | — | ≥ 0.95 |
| Detection precision | — | ≥ 0.90 |
| Summary faithfulness | — | ≥ 0.90 |
| Summary hallucination rate | — | ≤ 0.05 |
| Mapping precision | — | ≥ 0.80 |
| Mapping recall | — | ≥ 0.75 |
| Proposal acceptance rate | — | ≥ 0.75 |
| Routing accuracy | — | ≥ 0.90 |
| Deadline accuracy | — | ≥ 0.85 |
| Audit completeness | 1.00 | 1.00 |
| Approval bypass rate | 0.00 | 0.00 |
| Cost per 1,000 changes | $0.00 | $0.00 |

## Quick start

```bash
git clone https://github.com/Vickkywhyte/compliance-monitoring-agent.git
cd compliance-monitoring-agent
cp .env.example .env       # no secrets required in v1 (free tier + local)
make sync doctor           # install deps, verify imports
make demo                  # seed data + run pipeline + open dashboard
```

Open `http://localhost:8501`.

**Requirements:**
- Python 3.11
- Optional: [Ollama](https://ollama.com/) with `llama3.1:8b` for local
  LLM fallback (recommended for offline use)
- Optional: Docker (for the compose-based flow)

**Or with Docker:**

```bash
docker compose up -d
# Dashboard: http://localhost:8501
# API:       http://localhost:8000/docs
```

## Repository structure

```
compliance-monitoring-agent/
├── claude_chat/              # 13 planning docs (source of truth)
├── configs/                  # YAML configs
├── data/
│   ├── kb/                   # firm knowledge base (committed)
│   ├── eval/                 # golden set (committed)
│   └── demo/                 # demo data (committed)
├── src/compliance_agent/     # library
│   ├── sources/              # regulatory feed adapters
│   ├── ingestion/            # fetch, normalize, orchestrate
│   ├── detection/            # change detection
│   ├── intelligence/         # summarize, map, propose
│   ├── routing/              # rules engine
│   ├── approval/             # human-in-the-loop
│   ├── audit/                # append-only event log
│   ├── llm/                  # rate-limited gateway
│   ├── evaluation/           # metrics + runner
│   ├── dashboard/            # Streamlit views
│   └── storage/              # SQLite repositories
├── scripts/                  # numbered entry points
├── api/                      # FastAPI routes
├── tests/
│   ├── security/             # security tests
│   └── fixtures/             # test data
├── Dockerfile
├── docker-compose.yml
└── Makefile
```

## The 30-second pitch

> "I built a compliance monitoring agent for EU financial services. It
> ingests regulatory feeds — sanctions updates, AML guidance — detects
> changes, summarizes them, maps them to the firm's business processes,
> and proposes action items to a human approver. Every proposal is
> traceable from source to approval, with a complete audit trail. It has
> a six-stage evaluation framework: coverage, accuracy, and action
> quality measured independently at each stage. It costs $0 to run —
> free-tier LLM with local fallback. And it's got a full threat model
> with 39 security controls, all enforced from Phase 1."

## Design decisions

- **Why SQLite?** Single file, $0, ACID, adequate for 10k–100k records.
  Migration path to Postgres documented.
- **Why no agent framework?** Three sequenced reasoning steps don't need
  LangGraph. Directness and auditability matter more than composability.
- **Why rules for routing?** Routing must be deterministic and auditable.
  The LLM decides content; rules decide destination.
- **Why human-in-the-loop?** Regulatory decisions cannot be delegated to
  autonomous systems. The agent proposes; humans decide.

Full ADR list in [`claude_chat/04_TECH_DECISIONS.md`](claude_chat/04_TECH_DECISIONS.md).

## Screenshots

*Added after Phase 10. Planned views: live feed, approval queue, change
detail with audit trail.*

## Documentation

Full planning docs live in [`claude_chat/`](claude_chat/). Reading order:

1. [`00_START_HERE.md`](claude_chat/00_START_HERE.md)
2. [`00_DISCOVERY.md`](claude_chat/00_DISCOVERY.md)
3. [`01_LESSONS_APPLIED.md`](claude_chat/01_LESSONS_APPLIED.md)
4. [`02_PRD.md`](claude_chat/02_PRD.md)
5. [`03_ARCHITECTURE.md`](claude_chat/03_ARCHITECTURE.md)
6. [`04_TECH_DECISIONS.md`](claude_chat/04_TECH_DECISIONS.md)
7. [`05_DATA_SPEC.md`](claude_chat/05_DATA_SPEC.md)
8. [`06_EVAL_SPEC.md`](claude_chat/06_EVAL_SPEC.md) ← the differentiator
9. [`07_SECURITY_MODEL.md`](claude_chat/07_SECURITY_MODEL.md)
10. [`08_ROADMAP.md`](claude_chat/08_ROADMAP.md)
11. [`09_AGENT_DESIGN.md`](claude_chat/09_AGENT_DESIGN.md)

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md).

## License

MIT — see [`LICENSE`](LICENSE).