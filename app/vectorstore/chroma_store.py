from __future__ import annotations

import os
import re
from pathlib import Path
from threading import RLock
from typing import Any

from app.embeddings import SemanticEmbeddings


class ChromaUnavailableError(RuntimeError):
    """Raised when the Chroma dependency is not installed or cannot start."""


class ChromaVectorStore:
    """Persistent Chroma adapter with CRUD, filtering, and thread-safe access."""

    def __init__(
        self,
        *,
        collection_name: str,
        embeddings: SemanticEmbeddings,
        persist_directory: str | Path | None = None,
    ):
        self.collection_name = self._safe_collection_name(collection_name)
        self.embeddings = embeddings
        self.persist_directory = (
            Path(persist_directory)
            if persist_directory
            else self._default_directory()
        )
        self._client = None
        self._collection = None
        self._lock = RLock()

    @property
    def available(self) -> bool:
        try:
            self._ensure_collection()
            return True
        except Exception:
            return False

    @property
    def collection(self):
        return self._ensure_collection()

    def upsert(
        self,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, Any]] | None = None,
    ) -> None:
        if not ids:
            return
        vectors = self.embeddings.embed_documents(documents)
        with self._lock:
            self.collection.upsert(
                ids=[str(item) for item in ids],
                documents=[str(item) for item in documents],
                embeddings=vectors,
                metadatas=metadatas,
            )

    def add(
        self,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, Any]] | None = None,
    ) -> None:
        self.upsert(ids, documents, metadatas)

    def query(
        self,
        query: str,
        *,
        n_results: int = 5,
        where: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        if n_results <= 0:
            return []
        query_vector = self.embeddings.embed_query(query)
        with self._lock:
            result = self.collection.query(
                query_embeddings=[query_vector],
                n_results=max(1, n_results),
                where=where,
                include=["documents", "metadatas", "distances"],
            )
        ids = (result.get("ids") or [[]])[0]
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        return [
            {
                "id": ids[index],
                "document": documents[index] if index < len(documents) else "",
                "metadata": metadatas[index] if index < len(metadatas) else {},
                "distance": distances[index] if index < len(distances) else None,
            }
            for index in range(len(ids))
        ]

    def get(
        self,
        *,
        ids: list[str] | None = None,
        where: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            return self.collection.get(ids=ids, where=where, include=["documents", "metadatas"])

    def delete(
        self,
        *,
        ids: list[str] | None = None,
        where: dict[str, Any] | None = None,
    ) -> None:
        with self._lock:
            self.collection.delete(ids=ids, where=where)

    def count(self) -> int:
        with self._lock:
            return int(self.collection.count())

    def reset(self) -> None:
        with self._lock:
            self._client.delete_collection(self.collection_name)
            self._collection = None

    def _ensure_collection(self):
        if self._collection is not None:
            return self._collection
        try:
            import chromadb
        except ImportError as exc:
            raise ChromaUnavailableError(
                "Chroma is not installed. Install chromadb>=0.5."
            ) from exc
        with self._lock:
            if self._collection is not None:
                return self._collection
            if self.persist_directory is None:
                self._client = chromadb.EphemeralClient()
            else:
                self.persist_directory.mkdir(parents=True, exist_ok=True)
                self._client = chromadb.PersistentClient(path=str(self.persist_directory))
            self._collection = self._client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            return self._collection

    def _default_directory(self) -> Path:
        configured = os.getenv("CHROMA_PERSIST_DIRECTORY")
        if configured:
            return Path(configured)
        return Path(__file__).resolve().parents[2] / "data" / "chroma"

    def _safe_collection_name(self, name: str) -> str:
        cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(name)).strip("-_")
        return (cleaned or "fitness")[:63]
