"""Session-private in-memory document stores and composite store for public demo mode."""

import hashlib
import logging
import os
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

import chromadb

from src.chunking import Chunk, chunk_units
from src.config import (
    DEFAULT_UPLOAD_VISIBILITY,
    DEMO_MAX_CHUNKS_PER_SESSION,
    DEMO_MAX_TOTAL_SESSION_CHUNKS,
    DEMO_MAX_UPLOAD_FILES_PER_SESSION,
    DEMO_MAX_UPLOAD_MB,
    SESSION_DOC_TTL_MINUTES,
    TOP_K,
)
from src.loaders import DocUnit
from src.vectorstore import StoreReadOnlyError, VectorStore, embed_texts

logger = logging.getLogger(__name__)


class SessionQuotaExceededError(ValueError):
    """Raised when an upload exceeds per-session or global limits."""
    pass


def resolve_source_name_collision(
    filename: str,
    existing_names: Set[str],
) -> str:
    """Resolve file name collisions with shared or existing session documents.

    Appends ' (yours)' or ' (yours N)' before the file extension if the name already exists.
    """
    if filename not in existing_names:
        return filename

    stem, ext = os.path.splitext(filename)
    candidate = f"{stem} (yours){ext}"
    if candidate not in existing_names:
        return candidate

    idx = 2
    while True:
        candidate = f"{stem} (yours {idx}){ext}"
        if candidate not in existing_names:
            return candidate
        idx += 1


resolve_name_collision = resolve_source_name_collision


class SessionDocStore:
    """In-memory VectorStore isolated to a single browser session."""

    def __init__(self, session_id: Optional[str] = None):
        self.session_id = session_id or uuid.uuid4().hex
        self.created_at = time.time()
        self.last_seen = time.time()
        self.uploaded_files: Set[str] = set()
        self.uploaded_bytes: int = 0

        # Isolated in-memory Chroma client
        self.client = chromadb.EphemeralClient()
        self.collection_name = f"sess_{self.session_id}"
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        self.read_only = False

    def touch(self) -> None:
        """Update last_seen timestamp."""
        self.last_seen = time.time()

    def count(self) -> int:
        """Return count of chunks in this session collection."""
        self.touch()
        return self.collection.count()

    def get_fingerprint(self) -> str:
        """Return fingerprint for session chunks."""
        cnt = self.count()
        if cnt == 0:
            return f"sess_{self.session_id}_empty"
        data = self.collection.get(include=["metadatas"])
        hash_entries = []
        for meta in data.get("metadatas", []):
            src = meta.get("source", "")
            fhash = meta.get("file_hash", "")
            hash_entries.append(f"{src}:{fhash}")
        hash_entries.sort()
        summary = f"{cnt}|" + ";".join(hash_entries)
        return hashlib.sha256(summary.encode("utf-8")).hexdigest()[:16]

    def list_sources(
        self,
        allowed_visibility: Optional[Union[Set[str], List[str]]] = None,
        practice_areas: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """List distinct sources uploaded in this session with origin='yours'."""
        self.touch()
        if self.count() == 0:
            return []

        data = self.collection.get(include=["metadatas"])
        sources_map: Dict[str, Dict[str, Any]] = {}

        for meta in data["metadatas"]:
            src = meta.get("source", "unknown")
            ftype = meta.get("file_type", "")
            vis = meta.get("visibility", DEFAULT_UPLOAD_VISIBILITY)
            pa = meta.get("practice_area", "General")
            if src not in sources_map:
                sources_map[src] = {
                    "name": src,
                    "chunk_count": 0,
                    "file_type": ftype,
                    "visibility": vis,
                    "practice_area": pa,
                    "origin": "yours",
                }
            sources_map[src]["chunk_count"] += 1

        allowed_vis_set = set(allowed_visibility) if allowed_visibility is not None else None
        pa_set = set(practice_areas) if practice_areas is not None and len(practice_areas) > 0 else None

        filtered = []
        for s in sources_map.values():
            if allowed_vis_set is not None and s["visibility"] not in allowed_vis_set:
                continue
            if pa_set is not None and s["practice_area"] not in pa_set:
                continue
            filtered.append(s)

        return sorted(filtered, key=lambda s: s["name"].lower())

    def delete_source(self, source_name: str) -> int:
        """Delete all chunks originating from a session-uploaded file."""
        self.touch()
        before_count = self.count()
        self.collection.delete(where={"source": source_name})
        after_count = self.count()
        self.uploaded_files.discard(source_name)
        return before_count - after_count

    def set_source_metadata(self, name: str, visibility: str, practice_area: str) -> int:
        """Update visibility and practice area metadata for a session-uploaded source."""
        self.touch()
        res = self.collection.get(where={"source": name}, include=["metadatas"])
        if not res or not res.get("ids"):
            return 0
        ids = res["ids"]
        old_metas = res["metadatas"]
        new_metas = []
        for m in old_metas:
            updated = dict(m)
            updated["visibility"] = visibility
            updated["practice_area"] = practice_area
            new_metas.append(updated)
        self.collection.update(ids=ids, metadatas=new_metas)
        return len(ids)

    def get_source_units(
        self,
        name: str,
        allowed_visibility: Optional[Union[Set[str], List[str]]] = None,
    ) -> List[DocUnit]:
        """Retrieve DocUnits for a session source."""
        self.touch()
        if self.count() == 0 or not name:
            return []

        res = self.collection.get(where={"source": name}, include=["documents", "metadatas"])
        docs = res.get("documents", [])
        metas = res.get("metadatas", [])
        if not docs or not metas:
            return []

        allowed_set = set(allowed_visibility) if allowed_visibility is not None else None
        items: List[Tuple[int, DocUnit]] = []
        for doc_text, meta in zip(docs, metas):
            vis = meta.get("visibility", DEFAULT_UPLOAD_VISIBILITY)
            if allowed_set is not None and vis not in allowed_set:
                return []
            chunk_idx = meta.get("chunk_index", 0)
            unit = DocUnit(
                text=doc_text,
                source=name,
                page=meta.get("page"),
                section=meta.get("section"),
                file_type=meta.get("file_type", ""),
            )
            items.append((chunk_idx, unit))

        items.sort(key=lambda x: x[0])
        return [unit for _, unit in items]

    def query_by_vector(
        self,
        query_vector: List[float],
        k: int = TOP_K,
        allowed_visibility: Optional[Union[Set[str], List[str]]] = None,
        practice_areas: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Query session collection by vector with origin='yours' on results."""
        self.touch()
        if self.count() == 0 or not query_vector:
            return []

        n_results = min(k, self.count())

        where_clauses: List[Dict[str, Any]] = []
        if allowed_visibility is not None:
            vis_list = list(allowed_visibility)
            if len(vis_list) == 1:
                where_clauses.append({"visibility": vis_list[0]})
            elif len(vis_list) > 1:
                where_clauses.append({"visibility": {"$in": vis_list}})

        if practice_areas is not None and len(practice_areas) > 0:
            pa_list = list(practice_areas)
            if len(pa_list) == 1:
                where_clauses.append({"practice_area": pa_list[0]})
            elif len(pa_list) > 1:
                where_clauses.append({"practice_area": {"$in": pa_list}})

        where_filter: Optional[Dict[str, Any]] = None
        if len(where_clauses) == 1:
            where_filter = where_clauses[0]
        elif len(where_clauses) > 1:
            where_filter = {"$and": where_clauses}

        results = self.collection.query(
            query_embeddings=[query_vector],
            n_results=n_results,
            where=where_filter,
            include=["documents", "metadatas", "distances"],
        )

        output: List[Dict[str, Any]] = []
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for doc_text, meta, dist in zip(docs, metas, distances):
            score = max(0.0, min(1.0, 1.0 - float(dist)))
            page_val = meta.get("page")
            page_clean = int(page_val) if page_val and page_val > 0 else None
            section_clean = meta.get("section") or None

            output.append({
                "text": doc_text,
                "citation": meta.get("citation", meta.get("source", "")),
                "source": meta.get("source", ""),
                "page": page_clean,
                "section": section_clean,
                "score": score,
                "visibility": meta.get("visibility", DEFAULT_UPLOAD_VISIBILITY),
                "practice_area": meta.get("practice_area", "General"),
                "origin": "yours",
            })

        return sorted(output, key=lambda x: x["score"], reverse=True)

    def query(
        self,
        question: str,
        k: int = TOP_K,
        embed_fn: Optional[Callable[[List[str], str], List[List[float]]]] = None,
        allowed_visibility: Optional[Union[Set[str], List[str]]] = None,
        practice_areas: Optional[List[str]] = None,
        return_vector: bool = False,
    ) -> Union[List[Dict[str, Any]], Tuple[List[Dict[str, Any]], Optional[List[float]]]]:
        """Semantic query for session store."""
        if self.count() == 0 or not question.strip():
            return ([], None) if return_vector else []

        if embed_fn is not None:
            q_embeds = embed_fn([question.strip()], "RETRIEVAL_QUERY")
        else:
            q_embeds = embed_texts([question.strip()], task_type="RETRIEVAL_QUERY")

        if not q_embeds:
            return ([], None) if return_vector else []

        query_vector = q_embeds[0]
        output = self.query_by_vector(
            query_vector=query_vector,
            k=k,
            allowed_visibility=allowed_visibility,
            practice_areas=practice_areas,
        )
        if return_vector:
            return output, query_vector
        return output

    def index_units(
        self,
        units: List[DocUnit],
        file_hash_by_source: Dict[str, str],
        embed_fn: Optional[Callable[[List[str], str], List[List[float]]]] = None,
        metadata_by_source: Optional[Dict[str, Dict[str, str]]] = None,
        file_bytes_by_source: Optional[Dict[str, int]] = None,
    ) -> Dict[str, Any]:
        """Index DocUnits into session store enforcing demo session quota limits."""
        self.touch()
        report: Dict[str, Any] = {
            "indexed_files": [],
            "skipped_files": [],
            "total_chunks_added": 0,
            "embedding_calls": 0,
        }

        # Validate caps
        units_by_source: Dict[str, List[DocUnit]] = {}
        for u in units:
            units_by_source.setdefault(u.source, []).append(u)

        new_files_count = len([s for s in units_by_source.keys() if s not in self.uploaded_files])
        if len(self.uploaded_files) + new_files_count > DEMO_MAX_UPLOAD_FILES_PER_SESSION:
            raise SessionQuotaExceededError(
                f"Session file limit reached: maximum {DEMO_MAX_UPLOAD_FILES_PER_SESSION} files allowed per session."
            )

        # Chunk units
        chunks_by_source: Dict[str, List[Chunk]] = {}
        total_new_chunks = 0
        for src, u_list in units_by_source.items():
            ch = chunk_units(u_list)
            chunks_by_source[src] = ch
            total_new_chunks += len(ch)

        current_chunks = self.count()
        if current_chunks + total_new_chunks > DEMO_MAX_CHUNKS_PER_SESSION:
            raise SessionQuotaExceededError(
                f"Session chunk limit exceeded: maximum {DEMO_MAX_CHUNKS_PER_SESSION} chunks per session "
                f"(current: {current_chunks}, new: {total_new_chunks})."
            )

        # Global session chunk cap
        global_chunks = get_global_session_chunks()
        if global_chunks + total_new_chunks > DEMO_MAX_TOTAL_SESSION_CHUNKS:
            raise SessionQuotaExceededError(
                f"Global demo capacity reached: maximum {DEMO_MAX_TOTAL_SESSION_CHUNKS} total session chunks."
            )

        # File size check
        if file_bytes_by_source:
            for src, b_count in file_bytes_by_source.items():
                if b_count > DEMO_MAX_UPLOAD_MB * 1024 * 1024:
                    raise SessionQuotaExceededError(
                        f"File '{src}' exceeds the maximum allowed size of {DEMO_MAX_UPLOAD_MB} MB."
                    )
                self.uploaded_bytes += b_count

        all_new_chunks: List[Chunk] = []
        for src, ch in chunks_by_source.items():
            all_new_chunks.extend(ch)
            self.uploaded_files.add(src)
            report["indexed_files"].append(src)

        if not all_new_chunks:
            return report

        texts_to_embed = [c.text for c in all_new_chunks]
        if embed_fn is not None:
            embeddings = embed_fn(texts_to_embed, "RETRIEVAL_DOCUMENT")
            report["embedding_calls"] += 1
        else:
            embeddings = embed_texts(texts_to_embed, task_type="RETRIEVAL_DOCUMENT")
            report["embedding_calls"] += (len(texts_to_embed) + 19) // 20

        ids: List[str] = []
        documents: List[str] = []
        metadatas: List[Dict[str, Any]] = []

        for c in all_new_chunks:
            ids.append(c.id)
            documents.append(c.text)
            src_meta = (metadata_by_source or {}).get(c.source, {})
            vis = src_meta.get("visibility", DEFAULT_UPLOAD_VISIBILITY)
            pa = src_meta.get("practice_area", "General")
            metadatas.append({
                "source": c.source,
                "citation": c.citation,
                "page": c.page if c.page is not None else 0,
                "section": c.section or "",
                "file_type": c.file_type,
                "file_hash": file_hash_by_source.get(c.source, ""),
                "visibility": vis,
                "practice_area": pa,
                "chunk_index": c.chunk_index,
            })

        self.collection.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=embeddings,
        )
        report["total_chunks_added"] = len(ids)
        return report


# Registry for session stores
_SESSION_REGISTRY: Dict[str, SessionDocStore] = {}


def get_global_session_chunks() -> int:
    """Return total chunk count across all active session collections."""
    total = 0
    for s in _SESSION_REGISTRY.values():
        try:
            total += s.collection.count()
        except Exception:
            pass
    return total


def get_session_store(session_id: str) -> SessionDocStore:
    """Retrieve or create an isolated SessionDocStore for a browser session."""
    cleanup_expired()
    if session_id not in _SESSION_REGISTRY:
        _SESSION_REGISTRY[session_id] = SessionDocStore(session_id)
    store = _SESSION_REGISTRY[session_id]
    store.touch()
    return store


def cleanup_expired(ttl_minutes: int = SESSION_DOC_TTL_MINUTES) -> int:
    """Free memory and delete collections for expired browser sessions."""
    now = time.time()
    cutoff = now - (ttl_minutes * 60)
    expired_ids = [sid for sid, s in _SESSION_REGISTRY.items() if s.last_seen < cutoff]
    for sid in expired_ids:
        s = _SESSION_REGISTRY.pop(sid, None)
        if s:
            try:
                s.client.delete_collection(s.collection_name)
            except Exception:
                pass
    if expired_ids:
        logger.info("Cleaned up %d expired demo session store(s).", len(expired_ids))
    return len(expired_ids)


def clear_all_sessions() -> None:
    """Clear all session stores (used for testing)."""
    for sid, s in list(_SESSION_REGISTRY.items()):
        try:
            s.client.delete_collection(s.collection_name)
        except Exception:
            pass
    _SESSION_REGISTRY.clear()


class CompositeStore:
    """Unified store facade composing the read-only shared VectorStore and session-private SessionDocStore."""

    def __init__(self, shared: VectorStore, session: Optional[SessionDocStore] = None):
        self.shared = shared
        self.session = session

    def count(self) -> int:
        """Return total chunks accessible across shared and session stores."""
        sh_cnt = self.shared.count()
        sess_cnt = self.session.count() if self.session else 0
        return sh_cnt + sess_cnt

    def get_fingerprint(self) -> str:
        """Combine shared and session fingerprints to isolate answer caches."""
        sh_fp = self.shared.get_fingerprint()
        sess_fp = self.session.get_fingerprint() if self.session else "none"
        combined = f"{sh_fp}:{sess_fp}"
        return hashlib.sha256(combined.encode("utf-8")).hexdigest()[:16]

    def list_sources(
        self,
        allowed_visibility: Optional[Union[Set[str], List[str]]] = None,
        practice_areas: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """List sources from both shared and session stores, tagged with origin ('sample' or 'yours')."""
        sources = []
        # Shared sample sources
        for s in self.shared.list_sources(allowed_visibility=allowed_visibility, practice_areas=practice_areas):
            item = dict(s)
            item["origin"] = "sample"
            sources.append(item)

        # Session-private sources
        if self.session:
            for s in self.session.list_sources(allowed_visibility=allowed_visibility, practice_areas=practice_areas):
                item = dict(s)
                item["origin"] = "yours"
                sources.append(item)

        return sorted(sources, key=lambda s: s["name"].lower())

    def query_by_vector(
        self,
        query_vector: List[float],
        k: int = TOP_K,
        allowed_visibility: Optional[Union[Set[str], List[str]]] = None,
        practice_areas: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Query both stores using a precomputed vector, merge results by score, and apply filters."""
        candidates = []
        # Query shared store
        sh_res = self.shared.query_by_vector(
            query_vector,
            k=k,
            allowed_visibility=allowed_visibility,
            practice_areas=practice_areas,
        )
        for r in sh_res:
            item = dict(r)
            item["origin"] = "sample"
            candidates.append(item)

        # Query session store
        if self.session and self.session.count() > 0:
            sess_res = self.session.query_by_vector(
                query_vector,
                k=k,
                allowed_visibility=allowed_visibility,
                practice_areas=practice_areas,
            )
            for r in sess_res:
                item = dict(r)
                item["origin"] = "yours"
                candidates.append(item)

        # Sort combined results descending by score
        candidates.sort(key=lambda x: x["score"], reverse=True)
        return candidates[:k]

    def query(
        self,
        question: str,
        k: int = TOP_K,
        embed_fn: Optional[Callable[[List[str], str], List[List[float]]]] = None,
        allowed_visibility: Optional[Union[Set[str], List[str]]] = None,
        practice_areas: Optional[List[str]] = None,
        return_vector: bool = False,
    ) -> Union[List[Dict[str, Any]], Tuple[List[Dict[str, Any]], Optional[List[float]]]]:
        """Embed question ONCE and query both stores, returning top k merged results."""
        if not question.strip() or self.count() == 0:
            return ([], None) if return_vector else []

        if embed_fn is not None:
            q_embeds = embed_fn([question.strip()], "RETRIEVAL_QUERY")
        else:
            q_embeds = embed_texts([question.strip()], task_type="RETRIEVAL_QUERY")

        if not q_embeds:
            return ([], None) if return_vector else []

        query_vector = q_embeds[0]
        results = self.query_by_vector(
            query_vector=query_vector,
            k=k,
            allowed_visibility=allowed_visibility,
            practice_areas=practice_areas,
        )

        if return_vector:
            return results, query_vector
        return results

    def get_source_units(
        self,
        name: str,
        allowed_visibility: Optional[Union[Set[str], List[str]]] = None,
    ) -> List[DocUnit]:
        """Retrieve DocUnits for a source from whichever store owns it."""
        if self.session and name in self.session.uploaded_files:
            return self.session.get_source_units(name, allowed_visibility)
        return self.shared.get_source_units(name, allowed_visibility)

    def delete_source(self, source_name: str) -> int:
        """Delete source from session store. Refuses deletions from shared store."""
        if self.session and source_name in self.session.uploaded_files:
            return self.session.delete_source(source_name)
        raise StoreReadOnlyError("Shared sample documents cannot be deleted.")

    def set_source_metadata(self, name: str, visibility: str, practice_area: str) -> int:
        """Edit metadata on session store. Refuses modifications to shared store."""
        if self.session and name in self.session.uploaded_files:
            return self.session.set_source_metadata(name, visibility, practice_area)
        raise StoreReadOnlyError("Shared sample documents cannot be modified.")

    def index_units(
        self,
        units: List[DocUnit],
        file_hash_by_source: Dict[str, str],
        embed_fn: Optional[Callable[[List[str], str], List[List[float]]]] = None,
        metadata_by_source: Optional[Dict[str, Dict[str, str]]] = None,
        file_bytes_by_source: Optional[Dict[str, int]] = None,
    ) -> Dict[str, Any]:
        """Index uploaded units into session store."""
        if not self.session:
            raise StoreReadOnlyError("No session store available for upload.")
        return self.session.index_units(
            units=units,
            file_hash_by_source=file_hash_by_source,
            embed_fn=embed_fn,
            metadata_by_source=metadata_by_source,
            file_bytes_by_source=file_bytes_by_source,
        )

    def reset(self) -> None:
        """Refuse reset on composite store because shared corpus is read-only."""
        raise StoreReadOnlyError("Cannot reset store: shared corpus is read-only in demo mode.")

    def migrate_metadata_from_manifest(self, *args: Any, **kwargs: Any) -> int:
        """Refuse metadata migration on composite store because shared corpus is read-only."""
        raise StoreReadOnlyError("Cannot migrate metadata: shared corpus is read-only in demo mode.")

    def resolve_upload_name(self, filename: str) -> str:
        """Resolve file name collision against both shared and session documents."""
        existing = {s["name"] for s in self.list_sources()}
        return resolve_name_collision(filename, existing)
