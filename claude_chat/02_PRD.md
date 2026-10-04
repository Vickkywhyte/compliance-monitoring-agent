# Product Requirements Document — Compliance Monitoring Agent

> **READ THIS FIRST (for Claude Code):**
> This PRD defines *what* to build and *why*. It does not define *how* —
> that is `03_ARCHITECTURE.md` and `04_TECH_DECISIONS.md`. Every functional
> requirement has a stable ID (FR-*) referenced from the roadmap and tests.
> Do not add, remove, or renumber requirements without updating the roadmap.
>
> **Dependencies:** `00_DISCOVERY.md` (problem, scope, metrics) ·
> `01_LESSONS_APPLIED.md` (constraints)
> **Depended on by:** `03_ARCHITECTURE.md` · `04_TECH_DECISIONS.md` ·
> `08_ROADMAP.md` · `09_AGENT_DESIGN.md`

---

## 1. Product summary

A compliance monitoring agent for a synthetic EU financial services firm.
The agent ingests regulatory feeds (EU sanctions, EU AML), detects and
summarizes changes, maps them to the firm's documented business processes,
proposes structured action items, and routes them to the correct human
approver. Every proposal is traceable from source to approval. The system
costs $0 to run.

## 2. Goals

- **G1** — Detect 95%+ of relevant regulatory changes from configured sources.
- **G2** — Summarize changes with ≤ 5% hallucination rate and full citations.
- **G3** — Map changes to internal processes with ≥ 0.80 precision.
- **G4** — Generate action items that are accepted by humans 75%+ of the time.
- **G5** — Produce a complete, defensible audit trail for every proposal.
- **G6** — Run end-to-end with $0 in external costs.
- **G7** — Onboard a new engineer to the codebase in under 30 minutes.

## 3. Non-goals (v1)

See `00_DISCOVERY.md` §8 for the exhaustive list. Restated for the PRD:

- No auto-execution of approved actions
- No integration with real ticketing/screening systems
- No non-EU regulators
- No real customer data
- No multi-tenant support
- No mobile app
- No non-English sources

## 4. Personas (summary)

Full personas in `00_DISCOVERY.md` §3. Summary:

| Persona | Primary need | Success signal |
|---|---|---|
| Maya — Compliance Officer | Filtered, prioritized approval queue | She approves 80%+ without edits |
| Idris — MLRO | Auditable trail for regulator | Every proposal traceable to source |
| Sofia — Head of Reg Affairs | Weekly digest for leadership | She uses it in Monday meetings |

## 5. User stories

### US-1 — Ingest
*As the system, I pull updates from configured regulatory sources on a
schedule and normalize them to a common schema.*

**Acceptance:**
- Fetches from EUR-Lex, EU sanctions list, EBA website
- Normalizes to a common `RegulatoryDocument` schema
- Preserves source URL, fetch timestamp, content checksum
- Handles source failures gracefully (retries, then marks source as degraded)
- Runs on a configurable schedule (default: every 4 hours)

### US-2 — Detect change
*As the system, I identify what changed since the last fetch and assign a
stable change ID.*

**Acceptance:**
- Detects: new document, amended document, withdrawn document
- Uses stable identifiers (CELEX numbers, list entry IDs)
- Preserves before/after diff for amended items
- Assigns a deterministic change ID (hash of source + identifier + version)
- Idempotent: re-running on the same fetch produces no new changes

### US-3 — Summarize change
*As a compliance officer, I see a plain-language summary of what changed
and why it matters.*

**Acceptance:**
- Summary is ≤ 200 words
- Every factual claim is cited to a specific source paragraph
- No hallucinated facts (verified by eval harness)
- Written for a compliance professional, not a lawyer or developer

### US-4 — Map to processes
*As a compliance officer, I see which of our internal processes are
affected by a change, with confidence scores.*

**Acceptance:**
- Returns a ranked list of (process, impact_type, confidence, rationale)
- Every mapping cites the specific process document section
- Confidence is calibrated (see `06_EVAL_SPEC.md` §4)
- Empty mapping is a valid answer if no process is affected

### US-5 — Propose action items
*As a compliance officer, I see specific, structured action items that I
can approve, edit, or reject.*

**Acceptance:**
- Each proposal is a structured object with: assignee role, deadline,
  severity, category, rationale, evidence links
- Deadline is derived from the regulation text when present; otherwise
  from heuristics with lower confidence
- Severity levels: critical, high, medium, low
- Every proposal cites the change that triggered it and the processes it
  affects

### US-6 — Route to approver
*As a compliance officer, I only see proposals routed to me.*

**Acceptance:**
- Routing rules: severity + category → role
- Critical/high severity → senior approver
- Role-based inbox view
- No proposal is auto-approved; all require explicit human action

### US-7 — Approve, edit, or reject
*As an approver, I can approve a proposal as-is, edit it and approve, or
reject it with a reason.*

**Acceptance:**
- Three actions: approve, edit+approve, reject
- Every action records: user, timestamp, action, edits (if any), reason
  (for reject)
- Approved proposals move to "approved" state; rejected to "rejected"
- Both states are immutable thereafter (audit requirement)

### US-8 — Audit trail
*As an MLRO, I can reconstruct the complete history of any proposal.*

**Acceptance:**
- Given a proposal ID, retrieve: source document, change diff, summary,
  process mappings, proposal details, all approver actions
- Given a change ID, retrieve all proposals derived from it
- Given a date range, list all changes and actions
- Export as JSON and PDF

### US-9 — Weekly digest
*As the Head of Regulatory Affairs, I get a weekly summary of activity.*

**Acceptance:**
- Generated every Monday at 8:00 AM (configurable)
- Contains: changes detected, proposals generated, actions taken,
  open items
- Delivered as a dashboard view (email delivery is v2)

### US-10 — Demo mode
*As a new evaluator, I can see the system work end-to-end in under
5 minutes with `make demo`.*

**Acceptance:**
- `make demo` seeds synthetic data, starts the app, opens the browser
- Demo simulates 5 pre-scripted changes flowing through the pipeline
- Every stage visible in the UI
- No network calls required (feeds are cached in the repo)

## 6. Functional requirements

### FR-1 Ingestion

- **FR-1.1** — Fetches from at least three source types: EUR-Lex (XML),
  EU sanctions list (XML), EBA website (RSS + HTML).
- **FR-1.2** — Normalizes all sources to a common schema (see `05_DATA_SPEC.md`).
- **FR-1.3** — Preserves source provenance: URL, fetch timestamp,
  content checksum, HTTP status.
- **FR-1.4** — Handles source failures with retry and exponential backoff.
- **FR-1.5** — Caches raw fetched content for offline reproducibility.
- **FR-1.6** — Runs on a configurable schedule; manual trigger available.
- **FR-1.7** — Idempotent: re-fetching identical content produces no
  duplicate records.

### FR-2 Change detection

- **FR-2.1** — Assigns stable identifiers to each regulatory document
  (CELEX for EUR-Lex, list entry ID for sanctions, document URI for EBA).
- **FR-2.2** — Detects: new, amended, withdrawn.
- **FR-2.3** — For amended items, produces a structured diff.
- **FR-2.4** — Change ID is deterministic: `sha256(source + identifier + version)[:16]`.
- **FR-2.5** — Idempotent: same input → same change ID → no duplicate.
- **FR-2.6** — Change record includes: type, effective date, source URL,
  diff, first-seen timestamp.

### FR-3 Summarization

- **FR-3.1** — Produces a plain-language summary ≤ 200 words.
- **FR-3.2** — Every factual claim is cited to a specific source paragraph
  using a stable citation format.
- **FR-3.3** — Summary is generated by an LLM with conservative prompting
  (see `09_AGENT_DESIGN.md`).
- **FR-3.4** — If the change is too ambiguous to summarize confidently,
  the summary is flagged as low-confidence rather than guessed.
- **FR-3.5** — Every summary passes the hallucination gate (≤ 0.05) before
  being stored.

### FR-4 Process mapping

- **FR-4.1** — Uses retrieval over the firm's knowledge base (6 process
  documents + 12 procedures + control matrix).
- **FR-4.2** — Returns ranked list of (process, impact_type, confidence,
  rationale, citation).
- **FR-4.3** — Impact types: `add_control`, `modify_control`,
  `add_screening`, `modify_screening`, `update_reporting`, `no_impact`.
- **FR-4.4** — Returns `no_impact` explicitly when no process is affected
  (with confidence).
- **FR-4.5** — Confidence is calibrated against ground truth (see
  `06_EVAL_SPEC.md` §4).

### FR-5 Action item proposal

- **FR-5.1** — Produces structured action items with: assignee role,
  deadline, severity, category, rationale, evidence links.
- **FR-5.2** — Deadline derived from regulation text when present.
- **FR-5.3** — Severity: critical, high, medium, low.
- **FR-5.4** — Category from controlled vocabulary: `screening_update`,
  `policy_update`, `procedure_update`, `reporting_update`,
  `training_required`, `customer_action`, `no_action`.
- **FR-5.5** — Every proposal cites: the change ID, the affected process(es),
  and the specific source passages informing the proposal.
- **FR-5.6** — Multiple proposals can derive from one change (e.g., a
  sanctions addition may propose both a screening update and a customer
  notification).

### FR-6 Routing

- **FR-6.1** — Routing rules defined in `configs/routing.yaml`.
- **FR-6.2** — Route by (severity, category) → role.
- **FR-6.3** — Default rules: critical/high → MLRO; medium → Compliance
  Officer; low → Compliance Analyst.
- **FR-6.4** — Routing decisions are logged with the rule that matched.
- **FR-6.5** — Unmatched proposals route to a default inbox and are flagged.

### FR-7 Human approval

- **FR-7.1** — Three actions: approve as-is, edit+approve, reject with reason.
- **FR-7.2** — All actions record: user ID, timestamp, action type, edits
  (for edit+approve), reason (for reject).
- **FR-7.3** — Approved and rejected states are immutable.
- **FR-7.4** — No proposal executes an action; approval is terminal.
- **FR-7.5** — Concurrent approval attempts are prevented (optimistic
  locking).

### FR-8 Audit trail

- **FR-8.1** — Every stage output is persisted with timestamp and actor.
- **FR-8.2** — Given a proposal ID, the full chain is retrievable.
- **FR-8.3** — Given a change ID, all derived proposals are retrievable.
- **FR-8.4** — Audit records are append-only; no modification or deletion.
- **FR-8.5** — Export available as JSON (machine) and PDF (regulator).

### FR-9 Weekly digest

- **FR-9.1** — Generated on a configurable schedule (default: Monday 8 AM).
- **FR-9.2** — Contains: changes detected, proposals generated, proposals
  approved/rejected, open items, top-severity items.
- **FR-9.3** — Rendered in the dashboard; delivery via email is v2.

### FR-10 Dashboard

- **FR-10.1** — Views: Live feed, Approval queue, Change detail, Audit
  trail, Weekly digest.
- **FR-10.2** — All views are server-rendered (Streamlit).
- **FR-10.3** — Change detail view shows: summary, citations, process
  mappings, proposals, action history.
- **FR-10.4** — Approval queue is filterable by severity, category,
  assignee.
- **FR-10.5** — All views render in ≤ 2 seconds for 500 items.

### FR-11 Demo mode

- **FR-11.1** — `make demo` seeds synthetic data and opens the dashboard.
- **FR-11.2** — Pre-scripted 5 changes flow through the pipeline visibly.
- **FR-11.3** — No network calls required (feeds cached in repo).
- **FR-11.4** — Runs in ≤ 5 minutes from a fresh clone.

### FR-12 Evaluation

- **FR-12.1** — A golden set of ≥ 50 labeled regulatory changes exists
  (see `06_EVAL_SPEC.md` §2).
- **FR-12.2** — All metrics in `00_DISCOVERY.md` §6 are computed by
  `make eval`.
- **FR-12.3** — Evaluation runs end-to-end without manual intervention.
- **FR-12.4** — Results are written to `results/evals/{timestamp}.json`.

## 7. Non-functional requirements

| ID | Requirement | Target |
|---|---|---|
| NFR-1 | End-to-end latency (change → proposal) | ≤ 60 sec, p50 |
| NFR-2 | Dashboard view render | ≤ 2 sec for 500 items |
| NFR-3 | Ingestion throughput | ≥ 100 changes/hour |
| NFR-4 | Concurrent approvals | Prevent double-write (optimistic lock) |
| NFR-5 | Storage growth | ≤ 100 MB for 6 months of synthetic data |
| NFR-6 | Cost to run | $0 (free LLM tier + local models) |
| NFR-7 | Recovery from LLM rate limit | Automatic backoff + local fallback |
| NFR-8 | Audit completeness | 100% of proposals traceable to source |
| NFR-9 | Test coverage (core modules) | ≥ 85% |
| NFR-10 | Documentation completeness | Every module has a docstring + README section |
| NFR-11 | Security controls | Per `07_SECURITY_MODEL.md`, all P0 controls implemented |
| NFR-12 | Onboarding time | A new engineer runs `make demo` in ≤ 5 min |

## 8. Interfaces

### CLI commands (via Makefile)

| Command | Purpose |
|---|---|
| `make sync` | Install/update dependencies in the active venv |
| `make doctor` | Verify all imports resolve |
| `make ingest` | Run one ingestion cycle |
| `make detect` | Run change detection on ingested data |
| `make process` | Run the full pipeline (summarize → map → propose) |
| `make eval` | Run the evaluation harness |
| `make demo` | Seed data + start app + open browser |
| `make serve` | Start the API + dashboard |
| `make test` | Run the test suite |
| `make verify` | Run all self-tests and phase verifications |

### HTTP API (minimal, v1)

| Endpoint | Method | Purpose |
|---|---|---|
| `/health` | GET | Liveness + version |
| `/changes` | GET | List changes (paginated, filterable) |
| `/changes/{id}` | GET | Change detail |
| `/proposals` | GET | List proposals |
| `/proposals/{id}` | GET | Proposal detail |
| `/proposals/{id}/approve` | POST | Approve |
| `/proposals/{id}/edit` | POST | Edit + approve |
| `/proposals/{id}/reject` | POST | Reject with reason |
| `/audit/{proposal_id}` | GET | Full audit chain |
| `/audit/export` | GET | Export audit trail (JSON) |

The dashboard is the primary interface; the API exists for scripting and
future integrations.

### Dashboard (Streamlit)

| View | Purpose |
|---|---|
| Live feed | Chronological list of changes |
| Approval queue | Proposals awaiting human action |
| Change detail | Full context for a change |
| Audit trail | Chronological record of all actions |
| Weekly digest | Summary view for leadership |

## 9. Data model summary

Full schema in `05_DATA_SPEC.md`. Top-level entities:

- **RegulatoryDocument** — a source document (regulation, sanctions list entry)
- **Change** — a detected modification
- **Summary** — LLM-generated summary with citations
- **ProcessMapping** — (process, impact_type, confidence, rationale)
- **Proposal** — structured action item
- **ApprovalAction** — human action on a proposal
- **AuditEvent** — append-only log of system + human actions

## 10. Success criteria (DoD)

See `00_DISCOVERY.md` §11. Restated for the PRD:

- [ ] All FR-* and NFR-* requirements implemented
- [ ] All success metrics in `00_DISCOVERY.md` §6 measured and within target
- [ ] `make demo` works from a fresh clone in ≤ 5 minutes
- [ ] All `01_LESSONS_APPLIED.md` prevention mechanisms verified
- [ ] `07_SECURITY_MODEL.md` P0 controls implemented
- [ ] Full audit trail demonstrated end-to-end

## 11. Open questions

Tracked here until resolved. Each resolution updates this doc and, if
significant, adds an ADR.

- **OQ-1** — Which specific EBA source URLs to use? (resolve in Phase 2)
- **OQ-2** — Golden set composition: how many changes per severity
  category? (resolve in Phase 7 with eval spec)
- **OQ-3** — Should approved proposals be exportable as Jira-compatible
  JSON even though we don't integrate? (resolve in Phase 10)
- **OQ-4** — Rate-limit strategy: what backoff parameters for OpenRouter
  free tier? (resolve in Phase 4)