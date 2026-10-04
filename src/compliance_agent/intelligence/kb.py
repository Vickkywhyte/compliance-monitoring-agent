"""Knowledge base indexing for the process mapper (ADR-003, ADR-005).

Loads Markdown process documents from a directory, splits them into
overlapping chunks, and upserts them into a Chroma collection using
sentence-transformers embeddings.
"""
from __future__ import annotations

from pathlib import Path

import structlog

log = structlog.get_logger(__name__)

_CHUNK_SIZE = 500
_CHUNK_OVERLAP = 50


def index_knowledge_base(kb_dir: Path, collection) -> int:
    """Load .md files from kb_dir, chunk them, and upsert into collection.

    Returns the total number of chunks indexed.
    """
    doc_paths = sorted(kb_dir.glob("*.md"))
    if not doc_paths:
        log.warning("kb_no_documents", kb_dir=str(kb_dir))
        return 0

    total = 0
    for doc_path in doc_paths:
        text = doc_path.read_text(encoding="utf-8")
        chunks = _chunk_text(text, _CHUNK_SIZE, _CHUNK_OVERLAP)
        for i, chunk in enumerate(chunks):
            chunk_id = f"{doc_path.stem}:{i}"
            collection.upsert(
                ids=[chunk_id],
                documents=[chunk],
                metadatas=[{"source": doc_path.name, "chunk_index": i}],
            )
            total += 1

    log.info("kb_indexed", docs=len(doc_paths), chunks=total, kb_dir=str(kb_dir))
    return total


def _chunk_text(text: str, size: int, overlap: int) -> list[str]:
    """Split text into overlapping fixed-size character chunks."""
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start += size - overlap
    return chunks
