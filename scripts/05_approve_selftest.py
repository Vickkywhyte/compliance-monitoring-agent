"""Phase 5 self-test: approval service end-to-end (Lesson 2).

Creates a Proposal in storage, runs approve/reject/double-approve scenarios,
verifies audit chain completeness. Exits non-zero on any assertion failure.
"""
from __future__ import annotations

import sys
import tempfile
from datetime import date
from pathlib import Path

# Make src importable
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from compliance_agent.approval.service import ApprovalService
from compliance_agent.exceptions import ApprovalError, ConcurrentModificationError
from compliance_agent.storage.approvals import ApprovalActionRepository
from compliance_agent.storage.audit import AuditRepository
from compliance_agent.storage.db import get_connection, migrate
from compliance_agent.storage.models import Evidence, Proposal
from compliance_agent.storage.proposals import ProposalRepository
from compliance_agent.utils.ids import new_ulid, now_utc


def _make_proposal(change_id: str = "selftest_change_001") -> Proposal:
    return Proposal(
        proposal_id=new_ulid(),
        change_id=change_id,
        mapping_ids=["mapping_selftest_001"],
        assignee_role="officer",
        category="policy_update",
        severity="medium",
        title="Selftest: Update AML policy",
        description="Verify approval service end-to-end in Phase 5 selftest.",
        deadline=date(2027, 3, 1),
        deadline_rationale="Selftest deadline",
        evidence=[
            Evidence(
                kind="regulation_text",
                ref_id="selftest_change_001",
                excerpt="Selftest regulation excerpt",
            )
        ],
        prompt_version="propose_v1",
        model="fake",
        generated_at=now_utc(),
        state="pending",
        version=1,
    )


def run_selftest() -> None:
    print("=== Phase 5 approval selftest ===")

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "selftest.db"
        conn = get_connection(db_path)
        migrate(conn)
        conn.execute("PRAGMA foreign_keys=OFF")

        proposal_repo = ProposalRepository(conn)
        action_repo = ApprovalActionRepository(conn)
        audit_repo = AuditRepository(conn)

        # ── Test 1: Insert proposal ───────────────────────────────────────────
        proposal = _make_proposal()
        inserted = proposal_repo.insert(proposal)
        assert inserted, "insert() must return True on first insert"
        fetched = proposal_repo.get_by_id(proposal.proposal_id)
        assert fetched is not None
        assert fetched.state == "pending"
        assert fetched.version == 1
        print("  [1] insert + read-back: OK")

        # ── Test 2: Approve via ApprovalService ───────────────────────────────
        service = ApprovalService(conn)
        action = service.approve(proposal.proposal_id, "officer", "selftest_actor")
        assert action.action == "approve"
        assert action.proposal_id == proposal.proposal_id

        # Verify state changed
        updated = proposal_repo.get_by_id(proposal.proposal_id)
        assert updated is not None
        assert updated.state == "approved", f"Expected approved, got {updated.state}"
        assert updated.version == 2, f"Expected version=2, got {updated.version}"
        print("  [2] approve: state=approved, version=2: OK")

        # ── Test 3: Approval action persisted ─────────────────────────────────
        actions = action_repo.get_by_proposal(proposal.proposal_id)
        assert len(actions) == 1
        assert actions[0].action == "approve"
        print("  [3] approval_action persisted: OK")

        # ── Test 4: Audit chain complete ──────────────────────────────────────
        audit_events = audit_repo.query(entity_id=action.action_id)
        assert len(audit_events) >= 1, "Audit event must exist for the approval action"
        print("  [4] audit chain complete: OK")

        # ── Test 5: Second approval raises ApprovalError ──────────────────────
        raised = False
        try:
            service.approve(proposal.proposal_id, "officer", "selftest_actor_2")
        except ApprovalError:
            raised = True
        assert raised, "Second approve must raise ApprovalError"
        print("  [5] double-approve raises ApprovalError: OK")

        # ── Test 6: Reject a fresh proposal ───────────────────────────────────
        proposal2 = _make_proposal(change_id="selftest_change_002")
        proposal_repo.insert(proposal2)
        rej_action = service.reject(
            proposal2.proposal_id, "mlro", "selftest_mlro", "Insufficient controls"
        )
        assert rej_action.action == "reject"
        rejected = proposal_repo.get_by_id(proposal2.proposal_id)
        assert rejected is not None
        assert rejected.state == "rejected"
        print("  [6] reject: state=rejected: OK")

        # ── Test 7: Approve after reject raises ───────────────────────────────
        raised2 = False
        try:
            service.approve(proposal2.proposal_id, "officer", "selftest_actor_late")
        except ApprovalError:
            raised2 = True
        assert raised2, "Approve-after-reject must raise ApprovalError"
        print("  [7] approve-after-reject raises ApprovalError: OK")

    print("\nPASS: all 7 assertions passed")


if __name__ == "__main__":
    try:
        run_selftest()
    except Exception as exc:
        print(f"\nFAIL: {exc}", file=sys.stderr)
        sys.exit(1)
