# 60-Second Demo Script

This is the walkthrough for a live demo of the compliance monitoring agent.

## Prerequisites

```bash
make demo    # resets DB, seeds 6 pre-scripted changes, runs pipeline, opens dashboard
```

## The script (60 seconds)

**0:00 — The pitch.**
> "EU financial services firms miss regulatory changes not because they can't detect them — it's because they can't interpret them fast enough. This agent does that automatically, with a full audit trail."

**0:10 — The dashboard loads.**
Open `http://localhost:8501`. Point to the approval queue: 6 changes processed, 6 proposals waiting for review.

**0:20 — Show a proposal.**
Click any proposal in the queue. Point to:
- The change summary (with source citation)
- The mapped processes (with confidence scores)
- The proposed action (assignee role, deadline, severity)
- The evidence chain

> "Every field is traceable. Click the citation and you get the exact paragraph from the EUR-Lex document that triggered this."

**0:35 — Approve one.**
Click Approve on a medium-severity proposal.

> "The state changes from pending to approved. That action writes an immutable audit event — it cannot be edited or deleted. This is what regulators want to see."

**0:45 — Show the audit trail.**
Switch to the Audit Trail view. Show the approved event with timestamp, actor, and change ID.

> "Given any change ID, we can reconstruct: what was ingested, what changed, what was summarized, what processes were mapped, what was proposed, who approved it, and when."

**0:55 — The evaluation angle.**
> "And uniquely — this is evaluatable. There's a labeled golden set, 20 metrics across 6 stages, bootstrap confidence intervals. Detection recall: 100%. Audit completeness: 100%. Approval bypass rate: 0. That's the differentiator."

## Key numbers to cite

| Metric | Value |
|---|---|
| Tests passing | 211 |
| Security controls | 39 |
| Security tests | 53 |
| Evaluation metrics | 20 |
| Runtime cost | $0 |
| Onboarding time | < 5 minutes |

## Common questions

**"Is it connected to real regulators?"**
The architecture supports it. V1 runs against representative synthetic content to avoid real regulatory data in a demo environment. The source adapters (EUR-Lex, EU sanctions XML, EBA RSS) are production-ready.

**"What happens if the LLM is wrong?"**
The proposal goes into the queue and a human reviews it. A wrong proposal costs a minute of review time. A wrong auto-action in a regulated firm costs millions. Human-in-the-loop is the design, not a limitation.

**"How does it handle the free-tier rate limits?"**
There's a bounded queue (max 100 pending), exponential backoff with jitter, and automatic fallback to a local Ollama instance. The system never blocks on quota exhaustion.

**"What's the approval bypass rate?"**
0.00. Tested with 5 concurrent threads racing to approve the same proposal. Exactly one wins. The others get `ConcurrentModificationError`. This is enforced by optimistic locking at the database level.
