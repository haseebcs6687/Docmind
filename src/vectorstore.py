"""Vector database management, Gemini embedding integration, and semantic retrieval."""

import logging
import random
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import chromadb
from chromadb.api.models.Collection import Collection

from src.chunking import Chunk, chunk_units
from src.config import (
    CHROMA_DIR,
    EMBED_BATCH_SIZE,
    EMBED_BATCH_SLEEP_SECONDS,
    GEMINI_EMBED_MODEL,
    get_gemini_api_key,
)
from src.loaders import DocUnit

logger = logging.getLogger(__name__)


class EmbeddingError(Exception):
    """Raised when text embedding fails after retries or due to API/network errors."""
    pass


def embed_texts(
    texts: List[str],
    task_type: str = "RETRIEVAL_DOCUMENT",
    model: Optional[str] = None,
    client: Optional[Any] = None,
    batch_size: int = EMBED_BATCH_SIZE,
    sleep_seconds: float = EMBED_BATCH_SLEEP_SECONDS,
    max_retries: int = 5,
) -> List[List[float]]:
    """Embed a list of text strings using the official Gemini google-genai SDK.

    Args:
        texts: List of texts to generate embeddings for.
        task_type: Embedding task type ("RETRIEVAL_DOCUMENT" for chunks, "RETRIEVAL_QUERY" for queries).
        model: Model name (defaults to GEMINI_EMBED_MODEL or 'gemini-embedding-001').
        client: Optional pre-configured genai.Client instance.
        batch_size: Maximum texts per API call to conserve rate limits.
        sleep_seconds: Throttling pause between batches.
        max_retries: Number of retries on 429, 5xx, or network errors with exponential backoff.

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
            from google import genai
            api_key = get_gemini_api_key()
            client = genai.Client(api_key=api_key)
        except Exception as e:
            raise EmbeddingError(f"Failed to initialize Gemini client for embeddings: {e}")

    from google.genai import types

    all_embeddings: List[List[float]] = []

    # Process in batches
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        retries = 0
        backoff_delay = 2.0

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
                            raise EmbeddingError("Received malformed embedding object with missing vector values.")
                else:
                    raise EmbeddingError("Received empty response from Gemini embedding API.")
                break
            except Exception as e:
                err_str = str(e)
                status_code = getattr(e, "code", None) or getattr(e, "status_code", None)
                is_rate_limit = status_code == 429 or "429" in err_str or "RESOURCE_EXHAUSTED" in err_str
                is_server_error = (status_code and status_code >= 500) or "503" in err_str or "500" in err_str
                is_network = "ConnectError" in err_str or "Timeout" in err_str or "Network" in err_str

                if (is_rate_limit or is_server_error or is_network) and retries < max_retries:
                    retries += 1
                    jitter = random.uniform(0.1, 0.5)
                    wait_time = backoff_delay + jitter
                    logger.warning(
                        "Embedding API transient error (attempt %d/%d). Retrying in %.2fs. Error: %s",
                        retries,
                        max_retries,
                        wait_time,
                        err_str[:120],
                    )
                    time.sleep(wait_time)
                    backoff_delay *= 2
                else:
                    raise EmbeddingError(
                        f"Gemini embedding API failed after {retries} retries for model '{embed_model}': {err_str[:200]}"
                    )

        # Throttling between successive batches
        if i + batch_size < len(texts) and sleep_seconds > 0:
            time.sleep(sleep_seconds)

    return all_embeddings


class VectorStore:
    """Manages ChromaDB persistent vector storage, indexing, and semantic search."""

    def __init__(
        self,
        persist_directory: Optional[str] = None,
        collection_name: str = "docmind_collection",
        client: Optional[chromadb.ClientAPI] = None,
    ):
        self.persist_directory = persist_directory or CHROMA_DIR
        Path(self.persist_directory).mkdir(parents=True, exist_ok=True)
        self.client = client or chromadb.PersistentClient(path=self.persist_directory)
        self.collection_name = collection_name
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def count(self) -> int:
        """Return total number of chunks stored in the collection."""
        return self.collection.count()

    def reset(self) -> None:
        """Reset and recreate the vector collection."""
        try:
            self.client.delete_collection(self.collection_name)
        except Exception:
            pass
        self.collection = self.client.create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def delete_source(self, source_name: str) -> int:
        """Delete all chunks originating from a specific source file.

        Returns:
            Number of chunks removed (approximate based on count difference).
        """
        before_count = self.count()
        self.collection.delete(where={"source": source_name})
        after_count = self.count()
        return before_count - after_count

    def list_sources(self) -> List[Dict[str, Any]]:
        """List distinct sources indexed in the collection with chunk counts and file types."""
        if self.count() == 0:
            return []

        data = self.collection.get(include=["metadatas"])
        sources_map: Dict[str, Dict[str, Any]] = {}

        for meta in data["metadatas"]:
            src = meta.get("source", "unknown")
            ftype = meta.get("file_type", "")
            if src not in sources_map:
                sources_map[src] = {"name": src, "chunk_count": 0, "file_type": ftype}
            sources_map[src]["chunk_count"] += 1

        return sorted(sources_map.values(), key=lambda s: s["name"].lower())

    def index_units(
        self,
        units: List[DocUnit],
        file_hash_by_source: Dict[str, str],
        embed_fn: Optional[Callable[[List[str], str], List[List[float]]]] = None,
    ) -> Dict[str, Any]:
        """Index DocUnits into the vector store incrementally based on file hash.

        Args:
            units: List of DocUnits to index.
            file_hash_by_source: Mapping of source filename to its content hash.
            embed_fn: Optional custom embedding function for dependency injection / testing.

        Returns:
            Report detailing indexed files, skipped files, chunk counts, and embedding calls.
        """
        report: Dict[str, Any] = {
            "indexed_files": [],
            "skipped_files": [],
            "total_chunks_added": 0,
            "embedding_calls": 0,
        }

        # Group units by source filename
        units_by_source: Dict[str, List[DocUnit]] = {}
        for u in units:
            units_by_source.setdefault(u.source, []).append(u)

        for source_name, src_units in units_by_source.items():
            current_hash = file_hash_by_source.get(source_name, "")

            # Check if this source is already indexed in Chroma with identical hash
            existing = self.collection.get(where={"source": source_name}, limit=1, include=["metadatas"])
            if existing and existing["metadatas"]:
                stored_hash = existing["metadatas"][0].get("file_hash", "")
                if stored_hash == current_hash and current_hash:
                    # Unchanged: skip re-indexing completely
                    report["skipped_files"].append(source_name)
                    continue
                else:
                    # Hash changed: delete existing chunks for this source
                    self.collection.delete(where={"source": source_name})

        # Process sources requiring indexing
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

        # Generate embeddings
        if embed_fn is not None:
            embeddings = embed_fn(texts_to_embed, "RETRIEVAL_DOCUMENT")
            report["embedding_calls"] += 1
        else:
            embeddings = embed_texts(texts_to_embed, task_type="RETRIEVAL_DOCUMENT")
            report["embedding_calls"] += (len(texts_to_embed) + EMBED_BATCH_SIZE - 1) // EMBED_BATCH_SIZE

        # Prepare payload for Chroma
        ids: List[str] = []
        documents: List[str] = []
        metadatas: List[Dict[str, Any]] = []

        for c in all_new_chunks:
            ids.append(c.id)
            documents.append(c.text)
            metadatas.append({
                "source": c.source,
                "page": c.page if c.page is not None else 0,
                "section": c.section or "",
                "file_type": c.file_type,
                "citation": c.citation,
                "chunk_index": c.chunk_index,
                "file_hash": file_hash_by_source.get(c.source, ""),
            })

        # Add to Chroma collection in batches to stay within Chroma max batch limits
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
    ) -> List[Dict[str, Any]]:
        """Query the vector store with semantic search and return results with similarity scores.

        Similarity Score Calculation:
            Chroma uses cosine distance where distance = 1 - cosine_similarity.
            We convert this to a normalized similarity score:
                similarity = max(0.0, min(1.0, 1.0 - distance))
            A score of 1.0 indicates an identical vector direction, and 0.0 indicates orthogonal/unrelated.

        Args:
            question: Search query string.
            k: Number of nearest neighbors to retrieve.
            embed_fn: Optional custom embedding function for testing.

        Returns:
            List of matching chunk dictionaries: text, citation, source, page, section, score.
        """
        if self.count() == 0 or not question.strip():
            return []

        # Generate query embedding
        if embed_fn is not None:
            q_embeds = embed_fn([question.strip()], "RETRIEVAL_QUERY")
        else:
            q_embeds = embed_texts([question.strip()], task_type="RETRIEVAL_QUERY")

        if not q_embeds:
            return []

        query_vector = q_embeds[0]
        n_results = min(k, self.count())

        results = self.collection.query(
            query_embeddings=[query_vector],
            n_results=n_results,
            include=["documents", "metadatas", "distances"],
        )

        output: List[Dict[str, Any]] = []
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for doc_text, meta, dist in zip(docs, metas, distances):
            # Convert cosine distance (0 to 2) to similarity score (0.0 to 1.0)
            score = round(max(0.0, min(1.0, 1.0 - float(dist))), 4)
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
            })

        return output
