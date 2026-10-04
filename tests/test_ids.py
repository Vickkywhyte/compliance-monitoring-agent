"""Tests for ID and timestamp utilities (05_DATA_SPEC §7, §9)."""
from __future__ import annotations

from datetime import timezone

from compliance_agent.utils.ids import compute_change_id, new_ulid, now_utc


def test_new_ulid_length():
    """ULIDs are 26 characters long."""
    assert len(new_ulid()) == 26


def test_new_ulid_uniqueness():
    """Two consecutive ULIDs are different."""
    assert new_ulid() != new_ulid()


def test_new_ulid_is_string():
    """new_ulid() returns a string."""
    assert isinstance(new_ulid(), str)


def test_now_utc_is_timezone_aware():
    """now_utc() returns a timezone-aware datetime in UTC."""
    ts = now_utc()
    assert ts.tzinfo is not None
    assert ts.tzinfo == timezone.utc or ts.utcoffset().total_seconds() == 0


def test_compute_change_id_length():
    """change_id is exactly 16 hex characters."""
    cid = compute_change_id("eurlex", "32024R0001", 1)
    assert len(cid) == 16


def test_compute_change_id_is_hex():
    """change_id contains only hex characters."""
    cid = compute_change_id("eurlex", "32024R0001", 1)
    int(cid, 16)  # raises ValueError if not hex


def test_compute_change_id_is_deterministic():
    """Same inputs always produce the same change_id."""
    cid1 = compute_change_id("sanctions", "EU-0012345", 3)
    cid2 = compute_change_id("sanctions", "EU-0012345", 3)
    assert cid1 == cid2


def test_compute_change_id_differs_by_source():
    """Different sources produce different change IDs."""
    cid_a = compute_change_id("eurlex", "DOC-001", 1)
    cid_b = compute_change_id("sanctions", "DOC-001", 1)
    assert cid_a != cid_b


def test_compute_change_id_differs_by_version():
    """Different versions produce different change IDs."""
    cid_v1 = compute_change_id("eba", "EBA-GL-2024-01", 1)
    cid_v2 = compute_change_id("eba", "EBA-GL-2024-01", 2)
    assert cid_v1 != cid_v2
