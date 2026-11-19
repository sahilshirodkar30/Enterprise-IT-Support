import hashlib
from dataclasses import replace
from pathlib import Path

import logfire

from app.cache.semantic_cache import cache_clear
from app.config import get_settings
from app.guardrails.patterns import redact_cards
from app.rag.chunking.splitter import chunk_blocks
from app.rag.loader.loader import SUPPORTED, read_blocks
from services.embedding import embed_passages
from services.pinecone_store import get_index

UPSERT_BATCH = 100
DELETE_BATCH = 1000
# Refuse to prune if more than this share of indexed files would disappear.
MAX_PRUNE_RATIO = 0.5
MIN_FILES_FOR_PRUNE_GUARD = 4


def _discover(root: Path) -> list[Path]:
    return sorted(
        p for p in root.rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED
    )


def _file_hash(path: Path, model_name: str) -> str:
    # Include the model name so switching embedding models forces a full re-embed.
    h = hashlib.sha256(model_name.encode())
    h.update(path.read_bytes())
    return h.hexdigest()


def _embed_text(chunk) -> str:
    return f"{chunk.section}\n{chunk.text}" if chunk.section else chunk.text


def _vector_id(item) -> str:
    return item if isinstance(item, str) else item.id


def _page_ids(page) -> list[str]:
    items = getattr(page, "vectors", page)
    return [_vector_id(item) for item in items]


def _ids_by_file(index, namespace: str) -> dict[str, set[str]]:
    """Map each source path to the vector IDs currently stored for it."""
    by_file: dict[str, set[str]] = {}
    for page in index.list(namespace=namespace):
        for vid in _page_ids(page):
            source = vid.rsplit("#", 1)[0]
            by_file.setdefault(source, set()).add(vid)
    return by_file


def _is_unchanged(index, ns: str, rel: str, file_hash: str) -> bool:
    """Compare the stored hash on chunk 0 with the file's current hash."""
    first_id = f"{rel}#0"
    res = index.fetch(ids=[first_id], namespace=ns)
    vec = (getattr(res, "vectors", None) or {}).get(first_id)
    if vec is None:
        return False
    return (vec.metadata or {}).get("file_hash") == file_hash


def _delete_ids(index, ids, ns: str) -> int:
    ids = list(ids)
    for i in range(0, len(ids), DELETE_BATCH):
        index.delete(ids=ids[i:i + DELETE_BATCH], namespace=ns)
    return len(ids)


def ingest_docs(folder: str | Path | None = None) -> dict:
    s = get_settings()
    root = Path(folder) if folder else s.INGEST_PATH
    ns = s.PINECONE_NAMESPACE

    if not root.is_dir():
        raise FileNotFoundError(f"ingest folder not found: {root}")

    paths = _discover(root)
    if not paths:
        raise RuntimeError("no supported files found; refusing to run")

    index = get_index()
    live = {p.relative_to(root).as_posix() for p in paths}
    existing = _ids_by_file(index, ns)

    report = {
        "files": 0,
        "skipped_unchanged": 0,
        "chunks": 0,
        "stale_chunks_removed": 0,
        "pruned_files": 0,
        "errors": [],
        "quarantined": [],
        "cache_cleared": False,
    }
    changed = False
    logfire.info("ingestion started", files=len(paths), existing_sources=len(existing))

    for path in paths:
        rel = path.relative_to(root).as_posix()
        with logfire.span("ingest.file", file=rel):
            file_hash = _file_hash(path, s.EMBEDDING_MODEL_NAME)

            # 0. Skip files whose content and embedding model haven't changed.
            try:
                if _is_unchanged(index, ns, rel, file_hash):
                    report["skipped_unchanged"] += 1
                    continue
            except Exception as exc:
                # If the check fails, re-ingest the file rather than skip it.
                logfire.warn("unchanged check failed", file=rel, error_type=type(exc).__name__)

            # 1. Read and chunk. On failure, keep the file's old vectors.
            try:
                blocks = [replace(b, text=redact_cards(b.text)) for b in read_blocks(path)]
                chunks = chunk_blocks(blocks)
            except Exception as exc:
                report["errors"].append(f"{rel}: {exc}")
                logfire.error("file skipped", file=rel, error_type=type(exc).__name__)
                continue

            # 2. Empty file: remove its old vectors so they can't be retrieved.
            if not chunks:
                try:
                    removed = _delete_ids(index, existing.get(rel, set()), ns)
                except Exception as exc:
                    report["errors"].append(f"{rel}: delete failed: {exc}")
                    logfire.error("quarantine delete failed", file=rel)
                    continue
                report["stale_chunks_removed"] += removed
                report["quarantined"].append(rel)
                changed = changed or removed > 0
                logfire.warn("file quarantined: no chunks", file=rel, removed=removed)
                continue

            # 3. Embed and check dimensions before writing anything.
            try:
                vectors = embed_passages([_embed_text(c) for c in chunks])
                if any(len(v) != s.EMBEDDING_MODEL_DIMENSION for v in vectors):
                    raise RuntimeError(
                        f"embedding dimension mismatch, expected {s.EMBEDDING_MODEL_DIMENSION}"
                    )
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
                    "file_hash": file_hash,
                }
                if c.section:
                    meta["section"] = c.section
                if c.page is not None:
                    meta["page"] = c.page
                records.append({"id": f"{rel}#{c.index}", "values": vec, "metadata": meta})

            # 4. Upsert first, so the file is never missing from the index.
            try:
                for i in range(0, len(records), UPSERT_BATCH):
                    index.upsert(vectors=records[i:i + UPSERT_BATCH], namespace=ns)
            except Exception as exc:
                # Stop here: no deletes. A re-run completes the upsert.
                report["errors"].append(f"{rel}: upsert failed: {exc}")
                logfire.error("upsert failed", file=rel, error_type=type(exc).__name__)
                continue

            # 5. Delete only the old chunks the new set no longer has.
            new_ids = {r["id"] for r in records}
            stale = existing.get(rel, set()) - new_ids
            try:
                removed = _delete_ids(index, stale, ns)
            except Exception as exc:
                report["errors"].append(f"{rel}: stale delete failed: {exc}")
                logfire.error("stale delete failed", file=rel, error_type=type(exc).__name__)
                removed = 0

            report["files"] += 1
            report["chunks"] += len(records)
            report["stale_chunks_removed"] += removed
            changed = True
            logfire.info("file ingested", file=rel, chunks=len(records), stale_removed=removed)

    # 6. Prune vectors for files that left the folder, with a safety check.
    to_prune = [src for src in existing if src not in live]
    if (
        len(existing) >= MIN_FILES_FOR_PRUNE_GUARD
        and len(to_prune) / len(existing) > MAX_PRUNE_RATIO
    ):
        raise RuntimeError(
            f"refusing to prune {len(to_prune)} of {len(existing)} indexed files; "
            "check that the ingest folder is fully mounted"
        )

    for source in to_prune:
        try:
            _delete_ids(index, existing[source], ns)
        except Exception as exc:
            report["errors"].append(f"{source}: prune failed: {exc}")
            continue
        report["pruned_files"] += 1
        changed = True
        logfire.info("pruned removed file", file=source, vectors=len(existing[source]))

    # 7. Any corpus change makes cached answers potentially stale.
    if changed:
        try:
            cache_clear()
            report["cache_cleared"] = True
        except Exception:
            logfire.exception("cache clear failed; cached answers may be stale")
            report["errors"].append("cache clear failed")

    logfire.info(
        "ingestion finished",
        files=report["files"],
        skipped_unchanged=report["skipped_unchanged"],
        chunks=report["chunks"],
        stale_chunks_removed=report["stale_chunks_removed"],
        pruned_files=report["pruned_files"],
        errors=len(report["errors"]),
        quarantined=len(report["quarantined"]),
        cache_cleared=report["cache_cleared"],
    )
    return report