# Discovery — Compliance Monitoring Agent

> **READ THIS FIRST (for Claude Code):**
> This is the founding document. Every subsequent decision (ADR, schema,
> metric) derives from the problem statement, scope, and success metrics
> defined here. If a later document appears to contradict this one, stop
> and flag the contradiction — do not silently override.
>
> **Companion docs (locked, read in order):**
> `01_LESSONS_APPLIED.md` · `02_PRD.md` · `03_ARCHITECTURE.md` ·
> `04_TECH_DECISIONS.md` · `05_DATA_SPEC.md` · `06_EVAL_SPEC.md` ·
> `07_SECURITY_MODEL.md` · `08_ROADMAP.md` · `09_AGENT_DESIGN.md`

---

## 1. Problem statement

EU financial services firms are subject to a continuous stream of
regulatory change. Sanctions lists are updated weekly — sometimes daily —
by the EU Commission, OFAC, and the UN. AML directives, EBA guidance, and
national supervisory circulars arrive monthly. Each change implies a
specific obligation: screen new entities, update KYC procedures, amend
transaction-monitoring rules, notify the regulator, or document a decision.

Today, most mid-sized firms handle this manually. A compliance analyst
reads regulatory bulletins, mentally maps each change to internal
processes, and files action items in spreadsheets or ticketing systems.
The workflow is slow, inconsistent, and — critically — difficult to audit.
When a regulator asks "how did you respond to the 2024 update to the EU
sanctions list?", the answer is often assembled retroactively from email.

The gap is not detection. The EU publishes changes publicly and in
machine-readable form. The gap is **interpretation and translation** —
converting an external regulatory update into an internal, auditable,
assigned action item, in a form that a compliance officer can approve or
reject with full context.

This project builds that translator: an autonomous agent that monitors
regulatory feeds, detects and summarizes changes, maps them to the firm's
documented business processes, proposes specific action items, and routes
high-impact proposals to a human approver with full traceability. The
agent never executes on its own. It proposes; humans approve.

## 2. Why this exists

**The three questions this project answers:**

1. **Coverage** — Did we detect every relevant regulatory change?
2. **Accuracy** — Did we correctly interpret what changed and which
   internal processes are affected?
3. **Action quality** — Did we propose the right action, to the right
   person, at the right time, with the right evidence?

Everything downstream in this project — architecture, evaluation,
security — is a mechanism to measure and improve one of these three.

**The economic case:**

- A missed EU sanctions addition can cost a mid-sized firm €50k–€5M in
  fines plus reputational damage. Some violations are criminal.
- A compliance analyst at a mid-sized firm spends 40% of their time on
  regulatory triage that a well-designed agent can pre-digest.
- Regulators increasingly expect evidence of a *systematic* response to
  regulatory change, not just proof that someone noticed it.

**Why this is a hard problem (not a demo):**

- Source formats are heterogeneous: EUR-Lex HTML, EU list XML, PDFs of
  EBA guidance, and unstructured HTML from national regulators.
- Change detection requires stable identifiers, version tracking, and
  careful diffing — not just "is this URL new?"
- Mapping a change to internal processes requires a formal model of the
  firm, not just a text search.
- Action item generation must be conservative. A wrong action item at a
  regulated firm is worse than no action item at all.
- The system must be auditable end-to-end: any decision can be traced
  back to the specific regulatory change that triggered it.

## 3. Target users

### Primary persona — **Maya, Compliance Officer**

- 5–10 years in financial compliance, mid-sized EU bank or payments firm
- Reviews 20–50 regulatory changes per week
- Prioritizes based on gut feel and experience
- Needs: a *filtered, prioritized queue* of changes with clear action items
- Success for Maya: she trusts the queue and approves 80%+ of proposals
  without edits

### Secondary persona — **Idris, MLRO (Money Laundering Reporting Officer)**

- Ultimately responsible for AML compliance
- Signs off on high-impact actions
- Needs: an auditable trail for the regulator — "here's what we saw,
  here's what we did, here's who approved it"
- Success for Idris: the audit trail exists and is defensible

### Tertiary persona — **Sofia, Head of Regulatory Affairs**

- Strategic view across multiple regulators and jurisdictions
- Needs: a weekly digest of what's changed, what's coming, and where the
  firm is exposed
- Success for Sofia: she uses the dashboard in her Monday leadership
  meeting

**Non-user (explicit):** The system is *not* for external auditors, not
for end customers, and not for the firm's developers. It is a tool for
the compliance function itself.

## 4. The workflow — seven stages

Every regulatory change passes through seven stages. Each stage is a
distinct component with its own evaluation surface.

**Stage 1 — Ingest**
Pull updates from configured regulatory sources on a schedule. Normalize
to a common schema. Store with full provenance (source URL, fetch time,
checksum).

**Stage 2 — Detect**
Identify what changed: new regulation, amended regulation, withdrawn
regulation, new sanctions entry. Assign a stable change ID. Preserve the
diff.

**Stage 3 — Summarize**
Generate a plain-language summary of the change. Not a legal summary —
an *operational* one: what does this mean for a firm that does X?
Every summary cites the source paragraph it derives from.

**Stage 4 — Map**
Determine which of the firm's documented business processes are affected.
Produce a scored list: process, impact type, confidence, rationale. Every
mapping cites the specific process document section it maps to.

**Stage 5 — Propose**
Generate specific, structured action items. Each proposal contains:
assignee role, deadline, severity, category, rationale, evidence links.

**Stage 6 — Approve**
Route proposals to the correct human approver based on severity and
category. High-severity proposals require explicit approval. Low-severity
proposals still require approval, but the queue is optimized for speed.

**Stage 7 — Record**
Every stage's output is persisted with full traceability. Given a change
ID, the system can reconstruct: what was ingested, what changed, what was
summarized, what processes were mapped, what was proposed, who approved,
what was edited, and when.

**The agent never executes Stage 5's proposals autonomously.** Execution
(ticketing, screening, procedure updates) is out of scope for v1. The
output is a proposal + approval + audit record.

## 5. Scope for v1

### In scope

**Regulatory domains:**
- EU sanctions list changes (consolidated list, additions/removals/amendments)
- EU AML regulatory updates (EBA guidance, 6AMLD amendments, delegated
  regulations)

**Regulatory sources:**
- EUR-Lex (structured XML/HTML)
- EU Consolidated Financial Sanctions List (XML)
- EBA website updates (RSS + HTML)

**The synthetic firm:**
- 50 synthetic customers across 8 EU jurisdictions
- 6 documented business processes: customer onboarding, KYC refresh,
  transaction monitoring, sanctions screening, regulatory reporting,
  customer offboarding
- 3 roles: compliance analyst, compliance officer, MLRO
- An internal knowledge base containing process documents, procedures,
  and control matrices

**The agent:**
- Change detection with stable identifiers
- Summarization with citations
- Process mapping with confidence scoring
- Action item proposals (structured objects)
- Human-in-the-loop approval queue
- Full audit trail

**The dashboard:**
- Real-time feed view
- Approval queue
- Change detail view with all evidence
- Audit trail view
- Weekly digest view

### Out of scope (v1)

- Non-EU regulators (OFAC, UN, UK FCA, etc.) — architecture allows, not built
- Healthcare, data privacy, or other non-AML compliance domains
- Auto-execution of approved actions (no ticket creation, no screening runs)
- Real customer data (all data is synthetic)
- Multi-tenant or multi-firm support
- Mobile app
- Real-time streaming (we use polling; architecture supports streaming later)
- Non-English regulatory text (all sources are English)
- Historical backfill beyond the last 90 days of changes

## 6. Success metrics

Every metric maps to one of the three questions in §2.

### Coverage (Question 1)

| Metric | Target | How measured |
|---|---|---|
| Change detection recall | ≥ 0.95 | Against a labeled set of 50 historical changes |
| Change detection precision | ≥ 0.90 | Same set; measures false positives |
| Ingestion lag (source → detected) | ≤ 4 hours | Timestamp diff on sandbox feeds |

### Accuracy (Question 2)

| Metric | Target | How measured |
|---|---|---|
| Summary faithfulness | ≥ 0.90 | Claim-level entailment against source |
| Summary hallucination rate | ≤ 0.05 | Unsupported claims / total claims |
| Process mapping precision | ≥ 0.80 | vs. expert-curated ground truth |
| Process mapping recall | ≥ 0.75 | Same set |
| Confidence calibration | Brier ≤ 0.15 | Predicted confidence vs. observed correctness |

### Action quality (Question 3)

| Metric | Target | How measured |
|---|---|---|
| Proposal acceptance rate | ≥ 0.75 | % of proposals approved without edit |
| Proposal edit rate | ≤ 0.20 | % approved with minor edits |
| Proposal rejection rate | ≤ 0.05 | % rejected outright |
| Routing accuracy | ≥ 0.90 | Correct role assigned to proposal |
| Deadline accuracy | ≥ 0.85 | Within ±1 day of expert-assigned deadline |

### Operational

| Metric | Target | How measured |
|---|---|---|
| End-to-end latency (change → proposal) | ≤ 60 seconds | Wall clock, p50 |
| Cost per 1,000 changes processed | $0.00 | Free-tier LLM usage |
| Audit completeness | 100% | Every proposal traceable to source |
| Human-in-the-loop bypass rate | 0% | No proposal executes without approval |

## 7. The synthetic firm

To evaluate the system we need a firm whose processes we fully understand.
We build a synthetic EU financial services firm with the following assets
(all stored as documents in the repo):

**Customers (50 records):**
- Name, jurisdiction (DE/FR/IT/ES/NL/BE/IE/AT), entity type, risk tier
  (low/medium/high), relationship start date, current KYC status
- Distributed so that some changes affect 1 customer, some affect 20

**Processes (6 documented processes):**
Each has a formal document describing:
- Objective
- Trigger conditions
- Steps
- Controls
- Owner role
- Regulatory references (which regulations the process derives from)

The six processes:
1. **Customer onboarding** — initial KYC, screening, risk rating
2. **KYC refresh** — periodic re-verification (annual/biennial)
3. **Transaction monitoring** — rule-based screening of payments
4. **Sanctions screening** — pre-payment and batch screening
5. **Regulatory reporting** — SAR/STR filing, quarterly reports
6. **Customer offboarding** — closure, exit screening, records retention

**The knowledge base:**
- 6 process documents (as markdown)
- 12 procedure documents (sub-steps)
- A control matrix mapping processes to regulatory obligations
- A jurisdiction map (which regulations apply where)

**Why this matters:** the mapping stage (Stage 4 of the workflow) is only
meaningful if the firm is well-defined. This synthetic firm gives us a
consistent ground truth for evaluating whether the agent correctly maps
regulatory changes to the right internal processes.

## 8. Non-goals

Explicit statements of what we are *not* building, so they aren't proposed
later:

- We are not building a general-purpose regulatory change platform.
- We are not integrating with real Jira, ServiceNow, or ticketing systems.
- We are not handling real customer data — ever.
- We are not making legal determinations. The agent proposes; humans decide.
- We are not building a sanctions screening engine. We detect changes to
  the sanctions list; we do not run screening against customers.
- We are not optimizing for scale. 100 changes/day is the ceiling for v1.

## 9. Cost model

| Component | Approach | Monthly cost |
|---|---|---|
| LLM (summarization, mapping, proposal) | OpenRouter free tier | $0 |
| LLM fallback | Ollama (local, Llama 3.1 8B) | $0 |
| Embeddings | sentence-transformers (local, MiniLM) | $0 |
| Vector store | Chroma (local) | $0 |
| Application server | Docker on laptop | $0 |
| Storage | Local filesystem | $0 |
| **Total** | | **$0** |

**Rate-limit awareness is a first-class design concern.** Every LLM call
is queued, retried with exponential backoff, and falls back to local
inference if the hosted tier is exhausted.

## 10. The three questions, restated

> **Coverage:** Did we detect every relevant regulatory change?
> **Accuracy:** Did we correctly interpret what changed and what it affects?
> **Action quality:** Did we propose the right action, to the right person,
> at the right time?

Every metric in `06_EVAL_SPEC.md` maps to exactly one of these three.
Every architectural decision in `03_ARCHITECTURE.md` exists to make one of
these three measurable.

## 11. What "done" means for v1

The project is done when:

- [ ] The agent ingests from all three source types (EUR-Lex, sanctions
  list, EBA) without manual intervention
- [ ] Change detection runs on a schedule and produces structured diffs
- [ ] Summaries include citations and pass the hallucination gate (≤ 0.05)
- [ ] Process mapping achieves ≥ 0.80 precision on the golden set
- [ ] Proposals are routed to the correct role with ≥ 0.90 accuracy
- [ ] Every proposal has a complete audit trail from source to approval
- [ ] The dashboard renders the approval queue, change detail, and audit
  trail views
- [ ] All success metrics in §6 are measured and reported
- [ ] The system runs end-to-end with $0 in LLM costs
- [ ] A stranger can clone the repo, run `make demo`, and see the workflow
  in under 5 minutes

## 12. Founding commitments

These are non-negotiable principles. Any future decision that violates one
requires explicit re-approval.

1. **Human-in-the-loop is the product.** The agent proposes; humans decide.
2. **Every action is auditable.** No proposal without traceable evidence.
3. **Conservative by default.** When in doubt, propose less, not more.
4. **Zero cost to run.** Free tier LLM + local models; rate-limit-aware.
5. **Evaluation is first-class.** Coverage, accuracy, and action quality
   are measured continuously, not at the end.
6. **Security is structural.** The threat model (see `07_SECURITY_MODEL.md`)
   is written before code and enforced from Phase 1.
7. **Lessons applied.** Every failure from the prior RAG project (see
   `01_LESSONS_APPLIED.md`) has an explicit prevention mechanism here.