"""Vector database management, Gemini embedding integration, and semantic retrieval."""

import hashlib
import json
import logging
import random
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

import chromadb
from chromadb.api.models.Collection import Collection

from src.chunking import Chunk, chunk_units
from src.config import (
    CHROMA_DIR,
    DEFAULT_UPLOAD_VISIBILITY,
    DEMO_MODE,
    EMBED_BATCH_SIZE,
    EMBED_BATCH_SLEEP_SECONDS,
    GEMINI_EMBED_MODEL,
    GEN_MAX_RETRIES,
    TOP_K,
)
from src.gemini_client import (
    EmbeddingError,
    ErrorCategory,
    _sanitize_error_message,
    classify_error,
    create_gemini_client,
)
from src.loaders import DocUnit

logger = logging.getLogger(__name__)


def embed_texts(
    texts: List[str],
    task_type: str = "RETRIEVAL_DOCUMENT",
    model: Optional[str] = None,
    client: Optional[Any] = None,
    batch_size: int = EMBED_BATCH_SIZE,
    sleep_seconds: float = EMBED_BATCH_SLEEP_SECONDS,
    max_retries: int = GEN_MAX_RETRIES,
) -> List[List[float]]:
    """Embed a list of text strings using the official Gemini google-genai SDK.

    Args:
        texts: List of texts to generate embeddings for.
        task_type: Embedding task type ("RETRIEVAL_DOCUMENT" for chunks, "RETRIEVAL_QUERY" for queries).
        model: Model name (defaults to GEMINI_EMBED_MODEL or 'gemini-embedding-001').
        client: Optional pre-configured genai.Client instance.
        batch_size: Maximum texts per API call to conserve rate limits.
        sleep_seconds: Throttling pause between batches.
        max_retries: Number of retries on transient errors with exponential backoff.

    Returns:
        List of embedding vectors (list of floats).

    Raises:
        EmbeddingError: If embedding fails permanently without exposing API keys.
    """
    if not texts:
        return []

    embed_model = model or GEMINI_EMBED_MODEL or "gemini-embedding-001"

    if client is None:
        try:
            client = create_gemini_client()
        except Exception as e:
            cat = classify_error(e)
            raise EmbeddingError(cat, f"Failed to initialize Gemini client for embeddings: {e}")

    from google.genai import types

    all_embeddings: List[List[float]] = []

    # Process in batches
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        retries = 0
        backoff_delay = 1.0

        if DEMO_MODE:
            from src.demo_limits import check_and_count_embed
            allowed, limit_msg = check_and_count_embed(request_count=1)
            if not allowed:
                raise EmbeddingError(
                    ErrorCategory.QUOTA_DAILY,
                    limit_msg or "Today's free demo capacity has been used up. Please come back tomorrow.",
                )

        while True:
            try:
                response = client.models.embed_content(
                    model=embed_model,
                    contents=batch,
                    config=types.EmbedContentConfig(task_type=task_type),
                )
                if hasattr(response, "embeddings") and response.embeddings:
                    for emb in response.embeddings:
                        if hasattr(emb, "values") and emb.values is not None:
                            all_embeddings.append(list(emb.values))
                        else:
                            raise EmbeddingError(
                                ErrorCategory.UNKNOWN,
                                "Received malformed embedding object with missing vector values."
                            )
                else:
                    raise EmbeddingError(
                        ErrorCategory.UNKNOWN,
                        "Received empty response from Gemini embedding API."
                    )
                break
            except Exception as e:
                cat = classify_error(e)

                # Never retry daily quota or auth or bad request
                if cat in (ErrorCategory.QUOTA_DAILY, ErrorCategory.AUTH, ErrorCategory.BAD_REQUEST, ErrorCategory.MODEL_UNAVAILABLE):
                    raise EmbeddingError(cat, str(e), original_error=e)

                is_retryable = cat in (
                    ErrorCategory.RATE_LIMIT_MINUTE,
                    ErrorCategory.SERVER_BUSY,
                    ErrorCategory.TIMEOUT,
                    ErrorCategory.NETWORK,
                )

                if is_retryable and retries < max_retries:
                    retries += 1
                    jitter = random.uniform(0.1, 0.5)
                    wait_time = backoff_delay + jitter
                    logger.warning(
                        "[Retry] attempt %d/%d, wait %.2fs, error %s",
                        retries,
                        max_retries,
                        wait_time,
                        type(e).__name__,
                    )
                    time.sleep(wait_time)
                    backoff_delay *= 2.0
                else:
                    sanitized = _sanitize_error_message(e)
                    err_msg = f"Gemini embedding API failed after {retries} retries: {sanitized}"
                    raise EmbeddingError(cat, err_msg, original_error=e)

        # Throttling between successive batches
        if i + batch_size < len(texts) and sleep_seconds > 0:
            time.sleep(sleep_seconds)

    return all_embeddings


class StoreReadOnlyError(RuntimeError):
    """Raised when an attempt is made to mutate a read-only VectorStore."""
    pass


class VectorStore:
    """Manages ChromaDB persistent vector storage, indexing, and semantic search."""

    def __init__(
        self,
        persist_directory: Optional[str] = None,
        collection_name: str = "docmind_collection",
        client: Optional[chromadb.ClientAPI] = None,
        read_only: bool = False,
    ):
        self.persist_directory = persist_directory or CHROMA_DIR
        Path(self.persist_directory).mkdir(parents=True, exist_ok=True)
        self.client = client or chromadb.PersistentClient(path=self.persist_directory)
        self.collection_name = collection_name
        self.read_only = read_only
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def count(self) -> int:
        """Return total number of chunks stored in the collection."""
        return self.collection.count()

    def reset(self) -> None:
        """Reset and recreate the vector collection."""
        if self.read_only:
            raise StoreReadOnlyError("Shared sample document store is read-only in demo mode.")
        try:
            self.client.delete_collection(self.collection_name)
        except Exception:
            pass
        self.collection = self.client.create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def delete_source(self, source_name: str) -> int:
        """Delete all chunks originating from a specific source file."""
        if self.read_only:
            raise StoreReadOnlyError("Shared sample document store is read-only in demo mode.")
        before_count = self.count()
        self.collection.delete(where={"source": source_name})
        after_count = self.count()
        return before_count - after_count

    def list_sources(
        self,
        allowed_visibility: Optional[Union[Set[str], List[str]]] = None,
        practice_areas: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """List distinct sources indexed in the collection with chunk counts, file types, and access metadata."""
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

    def get_fingerprint(self) -> str:
        """Generate a SHA-256 fingerprint of the current vector store state to invalidate caches."""
        cnt = self.count()
        if cnt == 0:
            return "empty"
        data = self.collection.get(include=["metadatas"])
        hash_entries = []
        for meta in data.get("metadatas", []):
            src = meta.get("source", "")
            fhash = meta.get("file_hash", "")
            vis = meta.get("visibility", DEFAULT_UPLOAD_VISIBILITY)
            pa = meta.get("practice_area", "General")
            hash_entries.append(f"{src}:{fhash}:{vis}:{pa}")
        hash_entries.sort()
        summary = f"{cnt}|" + ";".join(hash_entries)
        return hashlib.sha256(summary.encode("utf-8")).hexdigest()[:16]

    def set_source_metadata(self, name: str, visibility: str, practice_area: str) -> int:
        """Update visibility and practice area metadata for all chunks of a source without re-embedding.

        Returns:
            Number of chunks updated (0 embedding calls).
        """
        if self.read_only:
            raise StoreReadOnlyError("Shared sample document store is read-only in demo mode.")
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

    def migrate_metadata_from_manifest(
        self,
        manifest: Optional[Dict[str, Dict[str, str]]] = None,
    ) -> Dict[str, int]:
        """Ensure all indexed sources have visibility and practice area applied from manifest without re-embedding.

        Returns:
            Dict mapping source name to count of updated chunks (0 embedding calls).
        """
        if self.read_only:
            raise StoreReadOnlyError("Shared sample document store is read-only in demo mode.")
        if manifest is None:
            manifest_path = Path(__file__).resolve().parent.parent / "data" / "sample_docs" / "manifest.json"
            if manifest_path.exists():
                try:
                    with open(manifest_path, "r", encoding="utf-8") as f:
                        manifest = json.load(f)
                except Exception as e:
                    logger.warning("Failed loading manifest from %s: %s", manifest_path, e)
                    manifest = {}
            else:
                manifest = {}

        report: Dict[str, int] = {}
        sources = self.list_sources()
        for s in sources:
            src_name = s["name"]
            cfg = manifest.get(src_name, {"visibility": DEFAULT_UPLOAD_VISIBILITY, "practice_area": "General"})
            target_vis = cfg.get("visibility", DEFAULT_UPLOAD_VISIBILITY)
            target_pa = cfg.get("practice_area", "General")

            current_vis = s.get("visibility")
            current_pa = s.get("practice_area")

            if current_vis != target_vis or current_pa != target_pa:
                cnt = self.set_source_metadata(src_name, target_vis, target_pa)
                report[src_name] = cnt

        return report

    def index_units(
        self,
        units: List[DocUnit],
        file_hash_by_source: Dict[str, str],
        embed_fn: Optional[Callable[[List[str], str], List[List[float]]]] = None,
        metadata_by_source: Optional[Dict[str, Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """Index DocUnits into the vector store incrementally based on file hash."""
        if self.read_only:
            raise StoreReadOnlyError("Shared sample document store is read-only in demo mode.")
        report: Dict[str, Any] = {
            "indexed_files": [],
            "skipped_files": [],
            "total_chunks_added": 0,
            "embedding_calls": 0,
        }

        units_by_source: Dict[str, List[DocUnit]] = {}
        for u in units:
            units_by_source.setdefault(u.source, []).append(u)

        for source_name, src_units in units_by_source.items():
            current_hash = file_hash_by_source.get(source_name, "")

            existing = self.collection.get(where={"source": source_name}, limit=1, include=["metadatas"])
            if existing and existing["metadatas"]:
                stored_hash = existing["metadatas"][0].get("file_hash", "")
                if stored_hash == current_hash and current_hash:
                    report["skipped_files"].append(source_name)
                    continue
                else:
                    self.collection.delete(where={"source": source_name})

        sources_to_index = [s for s in units_by_source.keys() if s not in report["skipped_files"]]
        if not sources_to_index:
            return report

        all_new_chunks: List[Chunk] = []
        for src in sources_to_index:
            chunks = chunk_units(units_by_source[src])
            all_new_chunks.extend(chunks)

        if not all_new_chunks:
            return report

        texts_to_embed = [c.text for c in all_new_chunks]

        if embed_fn is not None:
            embeddings = embed_fn(texts_to_embed, "RETRIEVAL_DOCUMENT")
            report["embedding_calls"] += 1
        else:
            embeddings = embed_texts(texts_to_embed, task_type="RETRIEVAL_DOCUMENT")
            report["embedding_calls"] += (len(texts_to_embed) + EMBED_BATCH_SIZE - 1) // EMBED_BATCH_SIZE

        ids: List[str] = []
        documents: List[str] = []
        metadatas: List[Dict[str, Any]] = []

        for c in all_new_chunks:
            ids.append(c.id)
            documents.append(c.text)
            source_meta = (metadata_by_source or {}).get(c.source, {})
            vis = source_meta.get("visibility", DEFAULT_UPLOAD_VISIBILITY)
            pa = source_meta.get("practice_area", "General")
            metadatas.append({
                "source": c.source,
                "page": c.page if c.page is not None else 0,
                "section": c.section or "",
                "file_type": c.file_type,
                "citation": c.citation,
                "chunk_index": c.chunk_index,
                "file_hash": file_hash_by_source.get(c.source, ""),
                "visibility": vis,
                "practice_area": pa,
            })

        chroma_batch_size = 100
        for b_start in range(0, len(ids), chroma_batch_size):
            b_end = b_start + chroma_batch_size
            self.collection.add(
                ids=ids[b_start:b_end],
                embeddings=embeddings[b_start:b_end],
                documents=documents[b_start:b_end],
                metadatas=metadatas[b_start:b_end],
            )

        report["indexed_files"].extend(sources_to_index)
        report["total_chunks_added"] = len(all_new_chunks)
        return report

    def query(
        self,
        question: str,
        k: int = 5,
        embed_fn: Optional[Callable[[List[str], str], List[List[float]]]] = None,
        allowed_visibility: Optional[Union[Set[str], List[str]]] = None,
        practice_areas: Optional[List[str]] = None,
        return_vector: bool = False,
    ) -> Union[List[Dict[str, Any]], Tuple[List[Dict[str, Any]], Optional[List[float]]]]:
        """Query the vector store with semantic search and return results with similarity scores.

        Similarity Score Calculation:
            Chroma uses cosine distance where distance = 1 - cosine_similarity.
            We convert this to a normalized similarity score:
                similarity = max(0.0, min(1.0, 1.0 - distance))

        Args:
            question: Natural language question to search.
            k: Number of nearest neighbors to retrieve.
            embed_fn: Optional embedding callable for testing.
            allowed_visibility: Set or list of visibility tags permitted ("client", "staff").
            practice_areas: Optional list of practice areas to filter by.
            return_vector: If True, returns (results, query_vector). Otherwise returns results.
        """
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

    def query_by_vector(
        self,
        query_vector: List[float],
        k: int = TOP_K,
        allowed_visibility: Optional[Union[Set[str], List[str]]] = None,
        practice_areas: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Query vector store directly with precomputed query vector (0 embedding API calls)."""
        if self.count() == 0 or not query_vector:
            return []

        n_results = min(k, self.count())

        # Construct ChromaDB where filter
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
            src_name = meta.get("source", "")
            ftype = meta.get("file_type", "")
            is_txt = (ftype.lower() == "txt") or src_name.lower().endswith(".txt")
            page_val = meta.get("page")
            page_clean = int(page_val) if page_val and page_val > 0 and not is_txt else None
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
            })

        return sorted(output, key=lambda x: x["score"], reverse=True)

    def get_source_units(
        self,
        name: str,
        allowed_visibility: Optional[Union[Set[str], List[str]]] = None,
    ) -> List[DocUnit]:
        """Retrieve the document text units/chunks for a given source document name.

        Respects allowed_visibility: if allowed_visibility is provided and any chunk
        in the document has visibility outside allowed_visibility, returns an empty list.
        """
        if self.count() == 0 or not name:
            return []

        res = self.collection.get(
            where={"source": name},
            include=["documents", "metadatas"],
        )
        docs = res.get("documents", [])
        metas = res.get("metadatas", [])

        if not docs or not metas:
            return []

        allowed_set = set(allowed_visibility) if allowed_visibility is not None else None

        items: List[Tuple[int, DocUnit]] = []
        for doc_text, meta in zip(docs, metas):
            vis = meta.get("visibility", DEFAULT_UPLOAD_VISIBILITY)
            if allowed_set is not None and vis not in allowed_set:
                logger.warning(
                    "get_source_units: document '%s' has visibility '%s' not in allowed %s",
                    name,
                    vis,
                    allowed_set,
                )
                return []

            chunk_idx = meta.get("chunk_index", 0)
            page_val = meta.get("page")
            page_clean = int(page_val) if page_val and page_val > 0 else None
            section_clean = meta.get("section") or None
            file_type = meta.get("file_type", "")

            items.append((
                chunk_idx,
                DocUnit(
                    text=doc_text,
                    source=name,
                    page=page_clean,
                    section=section_clean,
                    file_type=file_type,
                ),
            ))

        def _doc_sort_key(item: Tuple[int, DocUnit]) -> Tuple[int, int, int]:
            chunk_idx, unit = item
            page = unit.page or 0
            sec_num = 0
            if unit.section:
                m = re.match(r"^(\d+)", unit.section)
                if m:
                    sec_num = int(m.group(1))
                elif "overview" in unit.section.lower() or "preamble" in unit.section.lower():
                    sec_num = 0
                else:
                    sec_num = 999
            return (page, sec_num, chunk_idx)

        items.sort(key=_doc_sort_key)
        return [unit for _, unit in items]

