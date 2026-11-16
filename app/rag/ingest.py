from dataclasses import replace
from pathlib import Path

import logfire

from app.config import get_settings
from app.guardrails.patterns import redact_cards
from app.rag.chunking.splitter import chunk_blocks
from app.rag.loader.loader import SUPPORTED, read_blocks
from services.embedding import embed_passages
from services.pinecone_store import get_index

UPSERT_BATCH = 100
DELETE_BATCH = 1000


def _discover(root: Path) -> list[Path]:
    return sorted(
        p for p in root.rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED
    )


def _embed_text(chunk) -> str:
    # The section title helps retrieval match on topic. Stored text stays clean.
    return f"{chunk.section}\n{chunk.text}" if chunk.section else chunk.text


def _vector_id(item) -> str:
    # Newer Pinecone SDKs return ListItem objects with an .id attribute.
    # Older SDKs return plain strings.
    return item if isinstance(item, str) else item.id


def _page_ids(page) -> list[str]:
    # A page is either a list of items or an object with a .vectors list.
    items = getattr(page, "vectors", page)
    return [_vector_id(item) for item in items]


def _ids_by_file(index, namespace: str) -> dict[str, set[str]]:
    """Map each source path to the vector IDs currently stored for it."""
    by_file: dict[str, set[str]] = {}
    for page in index.list(namespace=namespace):
        for vid in _page_ids(page):
            # IDs look like "relative/path.md#3". The chunk index follows the last '#'.
            source = vid.rsplit("#", 1)[0]
            by_file.setdefault(source, set()).add(vid)
    return by_file


def _delete_ids(index, ids, namespace: str) -> int:
    ids = list(ids)
    for i in range(0, len(ids), DELETE_BATCH):
        index.delete(ids=ids[i:i + DELETE_BATCH], namespace=namespace)
    return len(ids)


def ingest_docs(folder: str | Path | None = None) -> dict:
    s = get_settings()
    root = Path(folder) if folder else s.INGEST_PATH
    ns = s.PINECONE_NAMESPACE

    if not root.is_dir():
        raise FileNotFoundError(f"ingest folder not found: {root}")

    paths = _discover(root)
    if not paths:
        # Guard against an unmounted or empty folder pruning the whole index.
        raise RuntimeError("no supported files found; refusing to run")

    index = get_index()
    live = {p.relative_to(root).as_posix() for p in paths}
    existing = _ids_by_file(index, ns)

    report = {
        "files": 0,
        "chunks": 0,
        "stale_chunks_removed": 0,
        "pruned_files": 0,
        "errors": [],
        "quarantined": [],
    }
    logfire.info("ingestion started", files=len(paths), existing_sources=len(existing))

    for path in paths:
        rel = path.relative_to(root).as_posix()
        with logfire.span("ingest.file", file=rel):

            # 1. Read and chunk. On failure, keep the file's old vectors.
            try:
                blocks = [replace(b, text=redact_cards(b.text)) for b in read_blocks(path)]
                chunks = chunk_blocks(blocks)
            except Exception as exc:
                report["errors"].append(f"{rel}: {exc}")
                logfire.error("file skipped", file=rel, error_type=type(exc).__name__)
                continue

            # 2. The file is now empty. Remove its old vectors so they can't be retrieved.
            if not chunks:
                removed = _delete_ids(index, existing.get(rel, set()), ns)
                report["stale_chunks_removed"] += removed
                report["quarantined"].append(rel)
                logfire.warn("file quarantined: no chunks", file=rel, removed=removed)
                continue

            # 3. Embed before writing. On failure, keep the file's old vectors.
            try:
                vectors = embed_passages([_embed_text(c) for c in chunks])
            except Exception as exc:
                report["errors"].append(f"{rel}: {exc}")
                logfire.error("embedding failed", file=rel, error_type=type(exc).__name__)
                continue

            mtime = path.stat().st_mtime
            records = []
            for c, vec in zip(chunks, vectors):
                meta = {
                    "text": c.text,
                    "source": rel,
                    "file_name": path.name,
                    "file_type": path.suffix.lower(),
                    "chunk_index": c.index,
                    "updated_at": mtime,
                }
                if c.section:
                    meta["section"] = c.section
                if c.page is not None:
                    meta["page"] = c.page
                records.append({
                    "id": f"{rel}#{c.index}",
                    "values": vec,
                    "metadata": meta,
                })

            # 4. Upsert first, so the file is never missing from the index.
            for i in range(0, len(records), UPSERT_BATCH):
                index.upsert(vectors=records[i:i + UPSERT_BATCH], namespace=ns)

            # 5. Delete only the old chunks that the new set no longer has.
            new_ids = {r["id"] for r in records}
            stale = existing.get(rel, set()) - new_ids
            report["stale_chunks_removed"] += _delete_ids(index, stale, ns)

            report["files"] += 1
            report["chunks"] += len(records)
            logfire.info("file ingested", file=rel, chunks=len(records), stale_removed=len(stale))

    # 6. Remove vectors from files that no longer exist in the folder.
    # Files that failed above are still in `live`, so their vectors are kept.
    for source, ids in existing.items():
        if source not in live:
            _delete_ids(index, ids, ns)
            report["pruned_files"] += 1
            logfire.info("pruned removed file", file=source, vectors=len(ids))

    logfire.info(
        "ingestion finished",
        files=report["files"],
        chunks=report["chunks"],
        stale_chunks_removed=report["stale_chunks_removed"],
        pruned_files=report["pruned_files"],
        errors=len(report["errors"]),
        quarantined=len(report["quarantined"]),
    )
    return report