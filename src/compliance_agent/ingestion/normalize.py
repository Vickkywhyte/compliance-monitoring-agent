"""Normalization: RawDocument → RegulatoryDocument.

Assigns a ULID doc_id, computes content_hash, and wraps parsed fields
into a RegulatoryDocument. Version management is delegated to the
DocumentRepository.upsert() method.
"""
from __future__ import annotations

import hashlib

from compliance_agent.sources.base import RawDocument
from compliance_agent.storage.models import RegulatoryDocument
from compliance_agent.utils.ids import new_ulid


def normalize(raw: RawDocument) -> RegulatoryDocument:
    """Convert a RawDocument into a RegulatoryDocument ready for storage.

    doc_id is a new ULID (unique per call).
    content_hash is sha256 of the UTF-8 content string.
    version defaults to 1; DocumentRepository.upsert() manages the actual version.
    """
    content_hash = hashlib.sha256(raw.content.encode("utf-8", errors="replace")).hexdigest()

    return RegulatoryDocument(
        doc_id=new_ulid(),
        source=raw.source_type,
        stable_id=raw.stable_id,
        title=raw.title,
        content=raw.content,
        content_hash=content_hash,
        source_url=raw.source_url,
        fetched_at=raw.fetched_at,
        effective_date=raw.effective_date,
        metadata=raw.metadata,
        version=1,
    )
