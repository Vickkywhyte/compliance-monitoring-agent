# Architecture — Compliance Monitoring Agent

> **READ THIS FIRST (for Claude Code):**
> This document defines *how* the system is structured. It is the highest-
> level technical artifact. Every module boundary, every data flow, and
> every concurrency decision lives here. Implementation details live in
> `04_TECH_DECISIONS.md` (ADRs) and `05_DATA_SPEC.md` (schemas).
> Do not add components without updating this document first.
>
> **Dependencies:** `00_DISCOVERY.md` · `01_LESSONS_APPLIED.md` ·
> `02_PRD.md`
> **Depended on by:** `04_TECH_DECISIONS.md` · `05_DATA_SPEC.md` ·
> `09_AGENT_DESIGN.md` · `08_ROADMAP.md`

---

## 1. System overview

```
┌───────────────────────────────────────────────────────────────────────┐
│                         EXTERNAL SOURCES                              │
│  EUR-Lex (XML)  │  EU Sanctions List (XML)  │  EBA Website (RSS/HTML)  │
└─────────┬────────────────────┬───────────────────────┬────────────────┘
          │                    │                       │
          └────────────────────┼───────────────────────┘
                               ▼
┌───────────────────────────────────────────────────────────────────────┐
│                       INGESTION LAYER                                 │
│   source adapters → fetch → normalize → RegulatoryDocument store     │
│   (concurrent per source, retry with backoff, raw cache retained)    │
└───────────────────────────────┬───────────────────────────────────────┘
                                ▼
┌───────────────────────────────────────────────────────────────────────┐
│                       DETECTION LAYER                                 │
│   stable IDs → version compare → diff → Change records              │
│   (idempotent, deterministic change IDs)                             │
└───────────────────────────────┬───────────────────────────────────────┘
                                ▼
┌───────────────────────────────────────────────────────────────────────┐
│                     INTELLIGENCE LAYER                                │
│                                                                       │
│   ┌──────────────┐   ┌──────────────┐   ┌──────────────────┐        │
│   │ Summarizer   │   │ Mapper       │   │ Proposal Engine  │        │
│   │ (LLM + cite) │──▶│ (retrieval + │──▶│ (LLM + rules)    │        │
│   │              │   │  LLM + score)│   │                  │        │
│   └──────────────┘   └──────────────┘   └──────────────────┘        │
│                                                                       │
│   All LLM calls: rate-limited queue + backoff + Ollama fallback      │
└───────────────────────────────┬───────────────────────────────────────┘
                                ▼
┌───────────────────────────────────────────────────────────────────────┐
│                       ROUTING LAYER                                   │
│   rules engine → assignee role → approval queue                     │
└───────────────────────────────┬───────────────────────────────────────┘
                                ▼
┌───────────────────────────────────────────────────────────────────────┐
│                    HUMAN-IN-THE-LOOP LAYER                            │
│   Dashboard: approve / edit+approve / reject                         │
│   Every action recorded; states immutable after decision             │
└───────────────────────────────┬───────────────────────────────────────┘
                                ▼
┌───────────────────────────────────────────────────────────────────────┐
│                       AUDIT LAYER                                     │
│   Append-only event log; full traceability; export as JSON/PDF       │
└───────────────────────────────────────────────────────────────────────┘

        ┌────────────────────────────────────────────────────┐
        │            PERSISTENCE (local, $0)                 │
        │  SQLite (events) · Filesystem (raw, KB) ·         │
        │  Chroma (vectors) · JSON logs                      │
        └────────────────────────────────────────────────────┘

        ┌────────────────────────────────────────────────────┐
        │            EVALUATION HARNESS (parallel)           │
        │  Runs against labeled golden set; produces metrics │
        │  Per-stage evaluation; not part of runtime path    │
        └────────────────────────────────────────────────────┘
```

## 2. Component responsibilities

| Component | Responsibility | Interface |
|---|---|---|
| **Sources** | Adapter per source type; fetch + parse | `Source.fetch() -> list[RawDocument]` |
| **Ingestion** | Orchestrate fetches; normalize; persist | `ingest(sources) -> IngestReport` |
| **Detector** | Compare new vs. stored; emit changes | `detect(docs) -> list[Change]` |
| **Summarizer** | LLM summary with citations | `summarize(change) -> Summary` |
| **Mapper** | Retrieve processes; score impact | `map(change, kb) -> list[ProcessMapping]` |
| **Proposer** | Generate structured action items | `propose(change, mappings) -> list[Proposal]` |
| **Router** | Assign proposals to roles | `route(proposal) -> RouteDecision` |
| **Approval** | Handle human actions | `approve() / edit() / reject()` |
| **Audit** | Append-only event log | `record(event)`, `retrieve(proposal_id)` |
| **Dashboard** | Streamlit UI | Server-rendered views |
| **Evaluator** | Offline metric computation | `evaluate(golden_set) -> EvalReport` |
| **LLM Gateway** | Rate-limited, retried, fallback LLM access | `complete(prompt) -> str` |

## 3. Data flows

### 3.1 Ingestion flow

```
scheduler (every 4h)
    │
    ▼
for each source (parallel, semaphore-capped):
    ├── fetch (HTTP + retry/backoff)
    ├── cache raw content on disk
    ├── parse to RawDocument
    ├── normalize to RegulatoryDocument
    └── upsert to store (dedup by content hash)

    ▼
IngestReport { source, fetched, new, unchanged, failed }
```

### 3.2 Detection flow

```
ingest_report
    │
    ▼
for each RegulatoryDocument:
    ├── extract stable_id (CELEX / list entry ID / document URI)
    ├── lookup previous version by stable_id
    ├── if new: emit Change(type="new")
    ├── if hash differs: emit Change(type="amended", diff=...)
    ├── if previous exists and current absent: emit Change(type="withdrawn")
    └── assign change_id = sha256(source + stable_id + version)[:16]
    ▼
list[Change] persisted
```

### 3.3 Intelligence flow (per change)

```
Change
  │
  ▼
Summarizer (LLM, conservative prompt)
  ├── generate summary with inline citations
  ├── validate: every citation resolves to a real source span
  ├── validate: hallucination gate (see 06_EVAL_SPEC.md)
  └── if fails gate: mark low-confidence, alert
  ▼
Summary
  │
  ▼
Mapper (retrieval + LLM ranking)
  ├── retrieve top-K relevant process sections from KB
  ├── LLM ranks (process, impact_type, confidence, rationale)
  ├── validate: every mapping cites a real KB section
  └── explicit no_impact allowed
  ▼
list[ProcessMapping]
  │
  ▼
Proposer (LLM + rules)
  ├── derive proposals from mappings
  ├── rule layer: severity from regulation text + heuristics
  ├── rule layer: deadline from regulation text + fallback
  ├── LLM layer: rationale, category
  └── validate: every proposal cites change + mappings + sources
  ▼
list[Proposal]
  │
  ▼
Router (rules only)
  ├── match (severity, category) → role from configs/routing.yaml
  ├── log matched rule
  └── default fallback if no match
  ▼
Proposal with assigned_role
```

### 3.4 Human-in-the-loop flow

```
Proposal in queue (state=pending)
    │
    ▼
Approver views detail (change, summary, mappings, evidence)
    │
    ▼
Approver takes action:
    ├── approve → state=approved, record event
    ├── edit+approve → state=approved, record event with edits
    └── reject+reason → state=rejected, record event with reason

All state transitions use optimistic locking (proposal.version)
```

### 3.5 Audit flow

```
Every stage emits AuditEvent:
    { timestamp, actor, action, entity_type, entity_id, payload }

AuditEvent store is append-only (no update, no delete)

Retrieval:
    get_audit_chain(proposal_id) -> ordered list of events
    get_proposals_for_change(change_id) -> list of proposals
    export_audit(filter) -> JSON or PDF
```

## 4. Concurrency model

Concurrency is a first-class design concern (see Lesson 6 in
`01_LESSONS_APPLIED.md`).

| Stage | Concurrency | Rationale |
|---|---|---|
| Ingestion | Per-source parallel, semaphore = 3 | 3 sources fetch simultaneously |
| Detection | Sequential per document | Cheap CPU-bound; no benefit to parallel |
| Summarization | Pool of 4 concurrent LLM calls | Rate-limit-aware |
| Mapping | Pool of 4 concurrent LLM calls | Shares pool with Summarizer |
| Proposal | Sequential per change | Cheap |
| Routing | Sequential | Trivial |
| Dashboard | Async per request | Streamlit handles |

**Global LLM semaphore:** max 4 in-flight requests. Queue holds waiting
requests. Backoff on 429/503 with exponential + jitter.

**Fallback chain:** OpenRouter free → Ollama (local) → error with
retry-later.

## 5. Persistence

| Concern | Store | Rationale |
|---|---|---|
| Regulatory documents | SQLite | Structured, queryable, small |
| Raw fetched content | Filesystem (`data/raw/{source}/{date}.xml`) | Audit; reproduce |
| Changes | SQLite | Structured, versioned |
| Summaries, mappings, proposals | SQLite | Structured |
| Knowledge base (processes) | Filesystem (Markdown) + Chroma (embeddings) | Human-editable, machine-retrievable |
| Vectors for KB retrieval | Chroma (local) | Simple, no server |
| Audit events | SQLite (append-only, WAL mode) | Transactional, queryable |
| Application logs | Filesystem (`logs/app.jsonl`) | Structured JSON |

**Why SQLite over Postgres:** $0, single file, sufficient for 6 months of
synthetic data. Migration path to Postgres is documented but not needed.

## 6. Module structure

```
src/compliance_agent/
├── __init__.py
├── config/                    # Pydantic config loaders (one per concern)
│   ├── loader.py
│   ├── sources.py
│   ├── processes.py
│   ├── agent.py
│   ├── routing.py
│   └── eval.py
├── storage/                   # Persistence layer
│   ├── db.py                  # SQLite connection, migrations
│   ├── models.py              # Pydantic models (also SQLite schemas)
│   ├── documents.py           # RegulatoryDocument repo
│   ├── changes.py             # Change repo
│   ├── proposals.py           # Proposal repo
│   └── audit.py               # Append-only audit repo
├── sources/                   # Source adapters (one per regulator)
│   ├── base.py                # Source ABC
│   ├── eurlex.py
│   ├── sanctions.py
│   ├── eba.py
│   └── registry.py
├── ingestion/
│   ├── fetch.py               # HTTP + retry
│   ├── normalize.py           # Raw → RegulatoryDocument
│   └── orchestrator.py        # Parallel fetch, persist
├── detection/
│   ├── stable_id.py           # Extract identifiers per source
│   ├── diff.py                # Structural diff
│   └── detector.py            # Orchestration
├── intelligence/
│   ├── summarizer.py
│   ├── mapper.py
│   ├── proposer.py
│   └── prompts/               # Versioned prompt files
├── routing/
│   ├── rules.py               # YAML-driven rule engine
│   └── router.py
├── approval/
│   ├── service.py             # Approve/edit/reject with optimistic locking
│   └── state.py               # State machine
├── audit/
│   ├── recorder.py
│   └── exporter.py            # JSON + PDF
├── llm/
│   ├── gateway.py             # Rate-limited, retried, fallback
│   ├── openrouter.py          # Hosted client
│   ├── ollama.py              # Local fallback client
│   └── prompts.py             # Prompt versioning + cache
├── evaluation/
│   ├── metrics/               # Per-stage metrics
│   ├── runner.py
│   └── report.py
├── dashboard/                 # Streamlit views
│   ├── app.py
│   ├── views/
│   └── components/
├── utils/
│   ├── logging.py
│   ├── cache.py
│   ├── ratelimit.py
│   └── ids.py
└── exceptions.py
```

Every module has:
- Module docstring
- Public classes/functions typed and documented
- `if __name__ == "__main__"` self-test entry point

## 7. Extension points

| Add a... | Do this |
|---|---|
| New regulatory source | Subclass `Source`, register in `sources/registry.py`, add config entry |
| New LLM provider | Subclass `LLMBackend`, register in `llm/gateway.py` |
| New metric | Subclass `Metric` in `evaluation/metrics/`, register, add to `06_EVAL_SPEC.md` |
| New proposal category | Add to controlled vocabulary in `configs/agent.yaml`, update routing rules |
| New dashboard view | Add module under `dashboard/views/`, register in `app.py` |

## 8. Cross-cutting concerns

### 8.1 Logging
- `structlog` JSON to stdout + `logs/app.jsonl` (rotating).
- Every log line: `ts, level, event, correlation_id, component, ...`.
- **Verified by read-back** (Lesson 5).

### 8.2 Correlation IDs
- Every ingestion run, every change, every proposal has a correlation ID.
- All log lines and audit events reference it.
- Enables end-to-end tracing.

### 8.3 Error handling
- Typed exceptions in `exceptions.py`.
- Fail loud in dev, fail soft in prod (log + continue where safe).
- No bare `except:` clauses.

### 8.4 Configuration
- Pydantic models for every config file.
- Loaded once at startup; immutable at runtime.
- Environment variables only via `config/loader.py` (Lesson 8).

### 8.5 Security (see `07_SECURITY_MODEL.md`)
- All fetched content treated as untrusted data.
- No `eval`, no `exec`, no shell=True.
- Prompt injection defense: content is fenced and labeled.
- Secrets only via `.env`, never logged.

## 9. Non-choices (explicit)

- No message queue (Kafka, RabbitMQ) — overkill for v1
- No microservices — monolith with clean module boundaries
- No Kubernetes — Docker Compose only
- No managed vector DB — Chroma local
- No agent framework (LangGraph, CrewAI) — custom, minimal, auditable
- No real-time streaming — polling on a schedule
- No multi-tenant — single firm, single deployment

## 10. Extension path (v2 and beyond)

Documented, not built:

- **v2.1** — Real-time streaming ingestion (SSE from EUR-Lex feeds)
- **v2.2** — Additional sources (OFAC, UN, UK FCA, national regulators)
- **v2.3** — Ticketing integration (Jira, ServiceNow)
- **v2.4** — Multi-firm support
- **v2.5** — Non-English sources
- **v2.6** — Historical backfill

## 11. Deployment topology

```
┌────────────────────────────────────────────────┐
│  Docker Compose (single host)                  │
│                                                │
│  ┌──────────────┐        ┌──────────────────┐ │
│  │  app         │        │  scheduler       │ │
│  │  (FastAPI +  │        │  (periodic       │ │
│  │  Streamlit)  │        │  ingestion +     │ │
│  │  :8000/:8501 │        │  processing)     │ │
│  └──────┬───────┘        └────────┬─────────┘ │
│         │                         │           │
│         └────────────┬────────────┘           │
│                      ▼                        │
│         ┌────────────────────────┐            │
│         │  Volumes:              │            │
│         │  ./data  (SQLite, raw) │            │
│         │  ./logs                │            │
│         │  ./results             │            │
│         │  ./models (Ollama)     │            │
│         └────────────────────────┘            │
│                                                │
└────────────────────────────────────────────────┘
```

**Ollama** runs as a sidecar container (optional; fallback only).

## 12. Architecture decision summary

Every architectural choice here is defended in `04_TECH_DECISIONS.md`
as an ADR. This document describes *what*; the ADRs describe *why*.