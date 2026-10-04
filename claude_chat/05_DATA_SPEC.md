# Data Specification — Compliance Monitoring Agent

> **READ THIS FIRST (for Claude Code):**
> Every schema in the system is defined here. Every store, every entity,
> every field. If code needs a new field, it is added here first, then
> in Pydantic models, then in code. Never add a field ad-hoc. Enums are
> locked; extending an enum requires updating this doc and any config
> that references it.
>
> **Dependencies:** `02_PRD.md` · `03_ARCHITECTURE.md` ·
> `04_TECH_DECISIONS.md` (ADR-002, ADR-006, ADR-008, ADR-015)
> **Depended on by:** `06_EVAL_SPEC.md` · `07_SECURITY_MODEL.md` ·
> `08_ROADMAP.md` · `09_AGENT_DESIGN.md`

---

## 1. Conventions

- **Pydantic v2** for every model crossing a module boundary.
- **Timestamps:** timezone-aware UTC (`datetime.now(timezone.utc)`).
- **IDs:** strings (ULIDs for new entities; hash-derived for deterministic entities).
- **Enums:** `Literal` types in Pydantic; validated against controlled vocabulary.
- **SQLite:** column names `snake_case`; row shape mirrors the Pydantic model.
- **`extra="forbid"`** on configs; **`extra="ignore"`** on I/O models.

## 2. Controlled vocabularies

These lists are canonical. Adding a value requires updating this spec,
any config that references the vocabulary, and the tests.

```python
SourceType = Literal["eurlex", "sanctions", "eba"]

ChangeType = Literal["new", "amended", "withdrawn"]

Severity = Literal["critical", "high", "medium", "low"]

ImpactType = Literal[
    "add_control", "modify_control",
    "add_screening", "modify_screening",
    "update_reporting", "no_impact",
]

ProposalCategory = Literal[
    "screening_update", "policy_update", "procedure_update",
    "reporting_update", "training_required", "customer_action",
    "no_action",
]

ProposalState = Literal["pending", "approved", "rejected"]

ApprovalAction = Literal["approve", "edit_approve", "reject"]

Role = Literal["analyst", "officer", "mlro"]

AuditEntityType = Literal[
    "regulatory_document", "change", "summary",
    "process_mapping", "proposal", "approval_action",
    "ingestion_run", "system",
]

Priority = Literal["p0", "p1", "p2", "p3"]
```

## 3. Core entities

### 3.1 RegulatoryDocument

```python
class RegulatoryDocument(BaseModel):
    model_config = {"extra": "ignore"}

    doc_id: str                       # ULID
    source: SourceType
    stable_id: str                    # CELEX / list entry ID / document URI
    title: str
    content: str                      # normalized text
    content_hash: str                 # sha256 of content
    source_url: str
    fetched_at: datetime
    effective_date: date | None
    metadata: dict[str, Any]          # source-specific extras
    version: int                      # incremented on amendment
```

**Persistence:** `regulatory_documents` table, primary key `doc_id`,
unique index on `(source, stable_id, version)`.

### 3.2 Change

```python
class Change(BaseModel):
    model_config = {"extra": "ignore"}

    change_id: str                    # sha256(source + stable_id + version)[:16]
    doc_id: str                       # FK to RegulatoryDocument
    source: SourceType
    stable_id: str
    change_type: ChangeType
    diff: str | None                  # unified diff for amended; None for new/withdrawn
    previous_version: int | None
    current_version: int
    detected_at: datetime
    effective_date: date | None
    metadata: dict[str, Any]
```

**Persistence:** `changes` table, primary key `change_id`.

### 3.3 Summary

```python
class Citation(BaseModel):
    model_config = {"extra": "forbid"}

    source_url: str
    span_start: int                   # char offset into document.content
    span_end: int
    quoted_text: str                  # the exact span (for verification)

class Summary(BaseModel):
    model_config = {"extra": "ignore"}

    summary_id: str                   # ULID
    change_id: str                    # FK to Change
    text: str                         # ≤ 200 words
    citations: list[Citation]         # ≥ 1
    prompt_version: str               # e.g., "summarize_v1"
    model: str                        # LLM model name
    confidence: float                 # 0.0–1.0
    low_confidence: bool              # true if hallucination gate failed
    generated_at: datetime
    tokens_in: int
    tokens_out: int
    cost_usd: float                   # 0.0 for free tier
```

**Persistence:** `summaries` table, primary key `summary_id`, foreign key
`change_id`.

### 3.4 ProcessMapping

```python
class ProcessMapping(BaseModel):
    model_config = {"extra": "ignore"}

    mapping_id: str                   # ULID
    change_id: str                    # FK to Change
    process_id: str                   # e.g., "customer_onboarding"
    process_section_id: str           # section within the process doc
    impact_type: ImpactType
    confidence: float                 # 0.0–1.0
    rationale: str                    # why this mapping
    citation_quote: str               # exact KB text supporting mapping
    prompt_version: str
    model: str
    generated_at: datetime
```

**Persistence:** `process_mappings` table, primary key `mapping_id`,
foreign key `change_id`.

**Note:** A change can produce zero mappings (if `no_impact` is confirmed)
or many (if multiple processes are affected).

### 3.5 Proposal

```python
class Evidence(BaseModel):
    model_config = {"extra": "forbid"}

    kind: Literal["citation", "mapping", "diff", "regulation_text"]
    ref_id: str                       # ID of the referenced entity
    excerpt: str                      # human-readable excerpt

class Proposal(BaseModel):
    model_config = {"extra": "ignore"}

    proposal_id: str                  # ULID
    change_id: str                    # FK to Change
    mapping_ids: list[str]            # FK to ProcessMapping(s)
    assignee_role: Role
    category: ProposalCategory
    severity: Severity
    title: str                        # ≤ 120 chars
    description: str                  # ≤ 500 chars
    deadline: date | None
    deadline_rationale: str           # why this deadline
    evidence: list[Evidence]          # ≥ 1
    prompt_version: str
    model: str
    generated_at: datetime
    state: ProposalState              # starts as "pending"
    version: int                      # for optimistic locking
```

**Persistence:** `proposals` table, primary key `proposal_id`,
foreign key `change_id`, index on `(state, assignee_role)`.

### 3.6 ApprovalAction

```python
class ApprovalAction(BaseModel):
    model_config = {"extra": "ignore"}

    action_id: str                    # ULID
    proposal_id: str                  # FK to Proposal
    actor_role: Role
    actor_id: str                     # synthetic user ID
    action: ApprovalAction
    edits: dict[str, Any] | None      # for edit_approve only
    reason: str | None                # for reject only
    acted_at: datetime
```

**Persistence:** `approval_actions` table, primary key `action_id`,
foreign key `proposal_id`.

**Note:** An approved or rejected proposal cannot receive further actions.
Enforced at the service layer via the proposal's `state` and `version`.

### 3.7 AuditEvent

```python
class AuditEvent(BaseModel):
    model_config = {"extra": "ignore"}

    event_id: str                     # ULID
    occurred_at: datetime
    actor: str                        # "system" or user ID
    action: str                       # e.g., "proposal_created"
    entity_type: AuditEntityType
    entity_id: str
    correlation_id: str               # for tracing
    payload: dict[str, Any]           # action-specific detail
```

**Persistence:** `audit_events` table, primary key `event_id`,
**append-only** (no UPDATE, no DELETE at the repository layer).

## 4. Knowledge base entities (file-based, not SQLite)

The firm's knowledge base lives as Markdown files under `data/kb/`:

```
data/kb/
├── processes/
│   ├── customer_onboarding.md
│   ├── kyc_refresh.md
│   ├── transaction_monitoring.md
│   ├── sanctions_screening.md
│   ├── regulatory_reporting.md
│   └── customer_offboarding.md
├── procedures/
│   ├── ... (12 files)
├── control_matrix.md
└── jurisdiction_map.md
```

Each process file has a frontmatter block:

```yaml
---
process_id: customer_onboarding
owner_role: officer
regulatory_refs:
  - "AMLD5 Article 13"
  - "EBA GL 2021/02"
---
```

Chunks are extracted from the body, tagged with `process_id` and a
generated `process_section_id`, and stored in Chroma.

## 5. Configuration schemas

### 5.1 `configs/sources.yaml`

```yaml
sources:
  - name: eurlex
    type: eurlex
    url: "https://eur-lex.europa.eu/..."
    schedule_cron: "0 */4 * * *"
    enabled: true

  - name: eu_sanctions
    type: sanctions
    url: "https://webgate.ec.europa.eu/fsd/fsf/public/files/xmlFullSanctionsList_1_1/content"
    schedule_cron: "0 */2 * * *"
    enabled: true

  - name: eba
    type: eba
    url: "https://www.eba.europa.eu/rss.xml"
    schedule_cron: "0 */6 * * *"
    enabled: true
```

### 5.2 `configs/agent.yaml`

```yaml
llm:
  primary_model: "meta-llama/llama-3.1-8b-instruct:free"
  fallback_model: "llama3.1:8b"       # Ollama
  temperature: 0.0
  max_tokens: 1024
  timeout_seconds: 30

gateway:
  max_concurrent: 4
  queue_max_size: 100
  backoff_initial_ms: 500
  backoff_max_ms: 30000
  fallback_after_consecutive_429: 3

summarizer:
  max_words: 200
  min_citations: 1
  hallucination_gate: 0.05

mapper:
  top_k: 8                            # KB chunks retrieved
  min_confidence: 0.30                # below this, mapping not emitted

proposer:
  max_proposals_per_change: 5
```

### 5.3 `configs/routing.yaml`

```yaml
rules:
  - priority: 1
    when: {severity: critical}
    assign_to: mlro
  - priority: 2
    when: {severity: high}
    assign_to: mlro
  - priority: 3
    when: {severity: medium, category: policy_update}
    assign_to: officer
  - priority: 4
    when: {severity: medium}
    assign_to: officer
  - priority: 5
    when: {severity: low}
    assign_to: analyst

default:
  assign_to: officer
  flag_unmatched: true
```

### 5.4 `configs/eval.yaml`

```yaml
golden_set_path: "data/eval/golden.jsonl"
metrics:
  coverage:
    - detection_recall
    - detection_precision
  accuracy:
    - summary_faithfulness
    - summary_hallucination_rate
    - mapping_precision
    - mapping_recall
    - confidence_brier
  action_quality:
    - proposal_acceptance_rate
    - routing_accuracy
    - deadline_accuracy
bootstrap_samples: 1000
seed: 0
```

## 6. On-disk formats

| Artifact | Format | Path |
|---|---|---|
| Raw fetched content | XML/HTML | `data/raw/{source}/{YYYYMMDD-HHMMSS}.xml` |
| Regulatory documents | SQLite | `data/compliance.db` (`regulatory_documents` table) |
| Changes | SQLite | `data/compliance.db` (`changes`) |
| Summaries | SQLite | `data/compliance.db` (`summaries`) |
| Process mappings | SQLite | `data/compliance.db` (`process_mappings`) |
| Proposals | SQLite | `data/compliance.db` (`proposals`) |
| Approval actions | SQLite | `data/compliance.db` (`approval_actions`) |
| Audit events | SQLite | `data/compliance.db` (`audit_events`) |
| Knowledge base | Markdown | `data/kb/**/*.md` |
| KB embeddings | Chroma | `data/chroma/kb/` |
| LLM cache | JSON | `data/cache/llm/{hash}.json` |
| Prompt files | Text | `src/compliance_agent/intelligence/prompts/*_v*.txt` |
| Golden set | JSONL | `data/eval/golden.jsonl` |
| Eval results | JSON | `results/evals/{timestamp}.json` |
| Application logs | JSONL | `logs/app.jsonl` |

## 7. ID conventions

| Entity | Format | Derivation |
|---|---|---|
| `doc_id` | ULID | generated on insert |
| `stable_id` | source-specific | CELEX (eurlex) / entry ID (sanctions) / URI (eba) |
| `change_id` | hex(16) | `sha256(source + stable_id + current_version)[:16]` |
| `summary_id` | ULID | generated |
| `mapping_id` | ULID | generated |
| `proposal_id` | ULID | generated |
| `action_id` | ULID | generated |
| `event_id` | ULID | generated |
| `correlation_id` | ULID | generated per ingestion run |

**Why ULIDs:** sortable by time, globally unique, URL-safe.

## 8. SQLite schema (DDL)

```sql
CREATE TABLE regulatory_documents (
    doc_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    stable_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    title TEXT,
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    source_url TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    effective_date TEXT,
    metadata TEXT,                    -- JSON blob
    UNIQUE(source, stable_id, version)
);

CREATE TABLE changes (
    change_id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL,
    source TEXT NOT NULL,
    stable_id TEXT NOT NULL,
    change_type TEXT NOT NULL,
    diff TEXT,
    previous_version INTEGER,
    current_version INTEGER NOT NULL,
    detected_at TEXT NOT NULL,
    effective_date TEXT,
    metadata TEXT,
    FOREIGN KEY (doc_id) REFERENCES regulatory_documents(doc_id)
);

CREATE TABLE summaries (
    summary_id TEXT PRIMARY KEY,
    change_id TEXT NOT NULL,
    text TEXT NOT NULL,
    citations TEXT NOT NULL,          -- JSON array
    prompt_version TEXT NOT NULL,
    model TEXT NOT NULL,
    confidence REAL NOT NULL,
    low_confidence INTEGER NOT NULL,
    generated_at TEXT NOT NULL,
    tokens_in INTEGER,
    tokens_out INTEGER,
    cost_usd REAL,
    FOREIGN KEY (change_id) REFERENCES changes(change_id)
);

CREATE TABLE process_mappings (
    mapping_id TEXT PRIMARY KEY,
    change_id TEXT NOT NULL,
    process_id TEXT NOT NULL,
    process_section_id TEXT NOT NULL,
    impact_type TEXT NOT NULL,
    confidence REAL NOT NULL,
    rationale TEXT,
    citation_quote TEXT,
    prompt_version TEXT NOT NULL,
    model TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    FOREIGN KEY (change_id) REFERENCES changes(change_id)
);

CREATE TABLE proposals (
    proposal_id TEXT PRIMARY KEY,
    change_id TEXT NOT NULL,
    mapping_ids TEXT NOT NULL,        -- JSON array
    assignee_role TEXT NOT NULL,
    category TEXT NOT NULL,
    severity TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    deadline TEXT,
    deadline_rationale TEXT,
    evidence TEXT NOT NULL,           -- JSON array
    prompt_version TEXT NOT NULL,
    model TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'pending',
    version INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (change_id) REFERENCES changes(change_id)
);
CREATE INDEX idx_proposals_state_role ON proposals(state, assignee_role);

CREATE TABLE approval_actions (
    action_id TEXT PRIMARY KEY,
    proposal_id TEXT NOT NULL,
    actor_role TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    action TEXT NOT NULL,
    edits TEXT,                       -- JSON, nullable
    reason TEXT,                      -- nullable
    acted_at TEXT NOT NULL,
    FOREIGN KEY (proposal_id) REFERENCES proposals(proposal_id)
);

CREATE TABLE audit_events (
    event_id TEXT PRIMARY KEY,
    occurred_at TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    payload TEXT NOT NULL             -- JSON blob
);
CREATE INDEX idx_audit_entity ON audit_events(entity_type, entity_id);
CREATE INDEX idx_audit_correlation ON audit_events(correlation_id);
```

**Append-only enforcement:** the repository for `audit_events` exposes
only `append()` and `query()`. No `update()` or `delete()` methods.
Additionally, tests assert that no SQL executed by the app contains
`UPDATE audit_events` or `DELETE FROM audit_events`.

## 9. ID and timestamp helpers

```python
def new_ulid() -> str:
    """Generate a ULID string."""
    ...

def now_utc() -> datetime:
    """Timezone-aware UTC now."""
    return datetime.now(timezone.utc)

def compute_change_id(source: str, stable_id: str, version: int) -> str:
    """Deterministic change ID."""
    payload = f"{source}|{stable_id}|{version}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
```

## 10. Migration policy

- SQLite schema changes are additive (add columns with defaults).
- Column removal requires a two-phase migration (deprecate → drop in v2).
- `audit_events` never loses columns.
- Migrations live in `src/compliance_agent/storage/migrations/` as
  numbered SQL files, applied by `migrate.py`.

## 11. What is NOT in this spec (yet)

- User authentication schema (v1 uses synthetic users)
- Ticketing integration schema (v2)
- Multi-firm isolation (v2)
- Email digest schema (v2)