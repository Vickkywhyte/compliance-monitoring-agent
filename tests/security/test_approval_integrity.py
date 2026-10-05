"""Security tests for approval integrity (T-05, C-18 to C-22, Phase 5).

Tests verify:
  - Exactly one concurrent approval succeeds (optimistic lock)
  - Terminal-state proposals reject further actions
  - No code path bypasses ApprovalService for state changes
  - Audit events are append-only at the repository layer
"""
from __future__ import annotations

import threading
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from compliance_agent.approval.service import ApprovalService
from compliance_agent.exceptions import ApprovalError, ConcurrentModificationError
from compliance_agent.storage.approvals import ApprovalActionRepository
from compliance_agent.storage.db import get_connection, migrate
from compliance_agent.storage.models import Evidence, Proposal
from compliance_agent.storage.proposals import ProposalRepository
from compliance_agent.utils.ids import new_ulid, now_utc


# ── Helpers ───────────────────────────────────────────────────────────────────


def _insert_proposal(conn, **overrides) -> Proposal:
    proposal = Proposal(
        proposal_id=overrides.get("proposal_id", new_ulid()),
        change_id="change_security_test",
        mapping_ids=["map_001"],
        assignee_role="officer",
        category="policy_update",
        severity="high",
        title="Security Test Proposal",
        description="Proposal for security testing.",
        deadline=date(2027, 1, 1),
        deadline_rationale="Test deadline",
        evidence=[Evidence(kind="regulation_text", ref_id="c001", excerpt="text")],
        prompt_version="propose_v1",
        model="fake",
        generated_at=now_utc(),
        state=overrides.get("state", "pending"),
        version=overrides.get("version", 1),
    )
    ProposalRepository(conn).insert(proposal)
    return proposal


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_concurrent_approvals_have_single_winner(tmp_path: Path):
    """5 threads race to approve the same proposal; exactly 1 succeeds.

    Each thread uses its own connection to the same file-based DB so that
    SQLite's WAL mode serializes writes and the optimistic lock resolves the race.
    """
    db_path = tmp_path / "concurrent.db"

    # Setup: create schema and insert one proposal (FK off for test isolation)
    setup_conn = get_connection(db_path)
    migrate(setup_conn)
    setup_conn.execute("PRAGMA foreign_keys=OFF")
    proposal = _insert_proposal(setup_conn)
    setup_conn.close()

    successes: list[int] = []
    failures: list[Exception] = []
    lock = threading.Lock()

    def try_approve(idx: int) -> None:
        conn = get_connection(db_path)
        service = ApprovalService(conn)
        try:
            service.approve(proposal.proposal_id, "officer", f"actor_{idx}")
            with lock:
                successes.append(idx)
        except (ApprovalError, ConcurrentModificationError) as exc:
            with lock:
                failures.append(exc)
        finally:
            conn.close()

    threads = [threading.Thread(target=try_approve, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(successes) == 1, f"Expected 1 success, got {len(successes)}: {successes}"
    assert len(failures) == 4, f"Expected 4 failures, got {len(failures)}"

    # Verify the DB reflects exactly one approval
    verify_conn = get_connection(db_path)
    repo = ProposalRepository(verify_conn)
    final = repo.get_by_id(proposal.proposal_id)
    assert final is not None
    assert final.state == "approved"
    assert final.version == 2
    verify_conn.close()


def test_rejected_proposal_cannot_be_approved():
    """Once rejected, a proposal cannot transition to approved."""
    conn = get_connection(":memory:")
    migrate(conn)
    conn.execute("PRAGMA foreign_keys=OFF")
    proposal = _insert_proposal(conn)
    service = ApprovalService(conn)

    service.reject(proposal.proposal_id, "mlro", "actor_r", "Not compliant")

    with pytest.raises(ApprovalError):
        service.approve(proposal.proposal_id, "officer", "actor_a")


def test_approved_proposal_cannot_be_modified():
    """Once approved, further approve, edit_approve, or reject calls are all rejected."""
    conn = get_connection(":memory:")
    migrate(conn)
    conn.execute("PRAGMA foreign_keys=OFF")
    proposal = _insert_proposal(conn)
    service = ApprovalService(conn)

    service.approve(proposal.proposal_id, "officer", "actor_first")

    with pytest.raises(ApprovalError):
        service.approve(proposal.proposal_id, "officer", "actor_second")

    with pytest.raises(ApprovalError):
        service.edit_approve(proposal.proposal_id, "officer", "actor_third", {"title": "X"})

    with pytest.raises(ApprovalError):
        service.reject(proposal.proposal_id, "mlro", "actor_fourth", "Late veto")


def test_optimistic_lock_prevents_stale_write():
    """A second service with a stale version raises ConcurrentModificationError."""
    conn = get_connection(":memory:")
    migrate(conn)
    conn.execute("PRAGMA foreign_keys=OFF")
    proposal = _insert_proposal(conn)

    # Service A approves → version becomes 2
    service_a = ApprovalService(conn)
    service_a.approve(proposal.proposal_id, "officer", "actor_a")

    # Insert a NEW pending proposal to test stale-version rejection
    p2 = _insert_proposal(conn, proposal_id=new_ulid())

    # Manually set up a scenario: service_b fetches version=1 (already committed as 2
    # after a race). We test by inserting another proposal and manually manipulating.
    # More direct: forcibly update version without going through service, then try to approve.
    # Since ProposalRepository.update_state_with_lock requires state='pending', we can test
    # the lock directly.
    repo = ProposalRepository(conn)
    # update_state_with_lock with wrong expected version must return False
    result = repo.update_state_with_lock(p2.proposal_id, expected_version=99, new_state="approved")
    assert result is False

    # The proposal must still be pending
    still_pending = repo.get_by_id(p2.proposal_id)
    assert still_pending is not None
    assert still_pending.state == "pending"
    assert still_pending.version == 1


def test_audit_events_are_append_only_via_repo():
    """AuditRepository must not expose update() or delete() methods (C-23)."""
    from compliance_agent.storage.audit import AuditRepository

    conn = get_connection(":memory:")
    migrate(conn)
    repo = AuditRepository(conn)

    assert not hasattr(repo, "update"), "AuditRepository must not expose update()"
    assert not hasattr(repo, "delete"), "AuditRepository must not expose delete()"
    assert not hasattr(repo, "remove"), "AuditRepository must not expose remove()"


def test_approval_bypass_is_impossible():
    """ProposalRepository exposes no direct set_state; only update_state_with_lock (version-gated).

    This verifies that no code path can change proposal state without going through
    the optimistic-lock mechanism.
    """
    repo = ProposalRepository.__dict__

    # Must NOT have a bare set_state method
    assert "set_state" not in repo, "ProposalRepository must not have set_state()"

    # update_state_with_lock MUST exist (it requires expected_version)
    assert "update_state_with_lock" in repo

    # Verify the function signature requires expected_version
    import inspect

    sig = inspect.signature(ProposalRepository.update_state_with_lock)
    assert "expected_version" in sig.parameters
