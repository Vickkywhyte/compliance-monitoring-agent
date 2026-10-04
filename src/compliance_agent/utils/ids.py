"""ID and timestamp helpers (05_DATA_SPEC §7, §9).

new_ulid()          — time-sortable, globally unique string ID
compute_change_id() — deterministic sha256-derived ID for Change records
now_utc()           — timezone-aware UTC datetime
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

import ulid as _ulid_lib


def new_ulid() -> str:
    """Generate a ULID string (time-sortable, URL-safe, globally unique)."""
    return str(_ulid_lib.new())


def now_utc() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def compute_change_id(source: str, stable_id: str, version: int) -> str:
    """Compute a deterministic 16-char hex change ID (05_DATA_SPEC §9).

    Same (source, stable_id, version) always produces the same ID.
    """
    payload = f"{source}|{stable_id}|{version}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


if __name__ == "__main__":
    print("=== utils/ids self-test ===")

    u1 = new_ulid()
    u2 = new_ulid()
    assert len(u1) == 26, f"unexpected ULID length: {len(u1)}"
    assert u1 != u2, "two consecutive ULIDs should differ"
    print(f"  new_ulid: {u1}")

    ts = now_utc()
    assert ts.tzinfo is not None, "datetime must be timezone-aware"
    print(f"  now_utc:  {ts.isoformat()}")

    cid = compute_change_id("eurlex", "32024R0001", 1)
    assert len(cid) == 16, f"change_id must be 16 chars, got {len(cid)}"
    assert cid == compute_change_id("eurlex", "32024R0001", 1), "change_id must be deterministic"
    print(f"  change_id: {cid}")

    print("PASS")
