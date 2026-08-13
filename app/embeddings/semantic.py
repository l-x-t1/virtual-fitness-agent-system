from __future__ import annotations

import math
import os
import re
from typing import Any

from langchain_core.embeddings import Embeddings


class EmbeddingConfigurationError(RuntimeError):
    """Raised when the configured semantic embedding backend cannot be loaded."""


class _LexicalSemanticFallback:
    """Offline fallback used only when the local model is unavailable."""

    _CONCEPTS = (
        ("\u6df1\u8e72", "\u4e0b\u80a2 \u817f \u81c0 \u819d \u52a8\u4f5c"),
        ("\u5e73\u677f\u652f\u6491", "\u6838\u5fc3 \u8179\u90e8 \u7a33\u5b9a \u4fef\u5367\u6491"),
        ("\u819d\u76d6", "\u819d \u5173\u8282 \u75bc\u75db \u4f4e\u51b2\u51fb \u4fdd\u62a4"),
        ("\u8170\u90e8", "\u8170 \u8170\u75db \u8170\u690e \u4fdd\u62a4"),
        ("\u80a9\u90e8", "\u80a9 \u80a9\u5173\u8282 \u4e0a\u80a2"),
        ("\u4f4e\u51b2\u51fb", "\u4f4e\u51b2\u51fb \u4e0d\u8df3 \u5feb\u8d70 \u9a91\u884c"),
        ("\u6709\u6c27", "\u5fc3\u80ba \u8010\u529b \u8dd1\u6b65 \u9a91\u884c \u6e38\u6cf3"),
        ("\u7a7a\u6c14", "\u7a7a\u6c14 \u96fe\u973e \u5ba4\u5916 \u7a7a\u6c14\u8d28\u91cf \u4e0d\u597d"),
        ("\u5ba4\u5185", "\u5ba4\u5185 \u4e0b\u96e8 \u96e8\u5929 \u5bbf\u820d \u5c45\u5bb6"),
        ("\u529b\u91cf", "\u529b\u91cf \u589e\u808c \u6297\u963b \u54d1\u94c3"),
        ("\u51cf\u8102", "\u51cf\u8102 \u51cf\u80a5 \u4f53\u91cd \u80fd\u91cf"),
        ("\u62c9\u4f38", "\u67d4\u97e7 \u62c9\u4f38 \u653e\u677e \u6d3b\u52a8\u5ea6"),
        ("\u70ed\u8eab", "\u70ed\u8eab \u51c6\u5907 \u52a8\u6001"),
        ("\u4f11\u606f", "\u6062\u590d \u7761\u7720 \u75b2\u52b3 \u4f11\u606f"),
        ("\u5668\u68b0", "\u54d1\u94c3 \u6760\u94c3 \u5065\u8eab\u623f \u5668\u6750"),
        ("\u5c45\u5bb6", "\u5bb6\u5ead \u5c45\u5bb6 \u5c0f\u7a7a\u95f4 \u65e0\u5668\u68b0"),
        ("\u9acb\u90e8", "\u9acb \u9acb\u90e8 \u4e45\u5750 \u7d27\u5f20 \u9acb\u5c48\u808c \u7075\u6d3b\u6027 \u6d3b\u52a8\u5ea6"),
        ("\u521d\u5b66\u8005", "\u521d\u5b66\u8005 \u65b0\u624b \u5165\u95e8"),
        ("\u8bad\u7ec3\u8ba1\u5212", "\u8ba1\u5212 \u5b89\u6392 \u5468\u671f \u8bad\u7ec3"),
        ("\u8bad\u7ec3\u9891\u7387", "\u9891\u7387 \u591a\u4e45 \u4e00\u6b21 \u4e00\u5468 \u5468\u8bad\u7ec3 \u9694\u5929 \u6062\u590d"),
    )

    def __init__(self, dimension: int = 64):
        self.dimension = max(dimension, len(self._CONCEPTS) + 1)

    def encode(self, texts: list[str]) -> list[list[float]]:
        return [self._encode(text) for text in texts]

    def _encode(self, text: str) -> list[float]:
        normalized = str(text or "").lower()
        vector = [0.0] * self.dimension
        for index, (_, aliases) in enumerate(self._CONCEPTS):
            hits = sum(1 for token in aliases.split() if token and token in normalized)
            vector[index] = float(hits)
        if self.dimension > len(self._CONCEPTS):
            words = re.findall(r"[a-z0-9]+", normalized)
            vector[len(self._CONCEPTS)] = min(1.0, len(words) / 10.0)
        norm = math.sqrt(sum(value * value for value in vector))
        return vector if norm == 0 else [value / norm for value in vector]


class SemanticEmbeddings(Embeddings):
    """LangChain embedding adapter backed by ``BAAI/bge-small-zh-v1.5``.

    The model is loaded lazily so importing the FastAPI application does not
    download a model.  Pass a fake ``model`` in unit tests to avoid network or
    GPU requirements.
    """

    DEFAULT_MODEL = "BAAI/bge-small-zh-v1.5"

    def __init__(
        self,
        model_name: str | None = None,
        *,
        model: Any | None = None,
        device: str | None = None,
        batch_size: int | None = None,
        normalize_embeddings: bool = True,
        allow_fallback: bool | None = None,
        allow_download: bool | None = None,
    ):
        self.model_name = model_name or os.getenv("EMBEDDING_MODEL", self.DEFAULT_MODEL)
        self.device = device or os.getenv("EMBEDDING_DEVICE", "cpu")
        self.batch_size = int(batch_size or os.getenv("EMBEDDING_BATCH_SIZE", "32"))
        self.normalize_embeddings = normalize_embeddings
        self.allow_fallback = (
            allow_fallback
            if allow_fallback is not None
            else os.getenv("EMBEDDING_ALLOW_FALLBACK", "true").lower() in {"1", "true", "yes"}
        )
        self.allow_download = (
            allow_download
            if allow_download is not None
            else os.getenv("EMBEDDING_ALLOW_DOWNLOAD", "false").lower() in {"1", "true", "yes"}
        )
        self._model = model
        self._fallback = _LexicalSemanticFallback(
            int(os.getenv("EMBEDDING_FALLBACK_DIMENSION", "64"))
        )
        self.backend = "injected" if model is not None else "uninitialized"

    @property
    def is_real_model(self) -> bool:
        return self.backend in {"sentence-transformers", "injected"}

    @property
    def dimension(self) -> int:
        if self._model is None and self.backend == "uninitialized":
            return self._fallback.dimension
        model = self._ensure_model()
        dimension = getattr(model, "get_sentence_embedding_dimension", None)
        if callable(dimension):
            return int(dimension())
        sample = self._encode([""])[0]
        return len(sample)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._encode([str(text or "") for text in texts])

    def embed_query(self, text: str) -> list[float]:
        return self._encode([str(text or "")])[0]

    def _ensure_model(self) -> Any:
        if self._model is not None:
            return self._model
        try:
            from sentence_transformers import SentenceTransformer

            if self.allow_download:
                self._model = SentenceTransformer(self.model_name, device=self.device)
            else:
                self._model = SentenceTransformer(
                    self.model_name,
                    device=self.device,
                    local_files_only=True,
                )
            self.backend = "sentence-transformers"
            return self._model
        except Exception as exc:
            if not self.allow_fallback:
                raise EmbeddingConfigurationError(
                    f"Unable to load embedding model '{self.model_name}'. "
                    "Install sentence-transformers and download the model."
                ) from exc
            self.backend = "offline-lexical"
            return self._fallback

    def _encode(self, texts: list[str]) -> list[list[float]]:
        model = self._ensure_model()
        if model is self._fallback:
            return model.encode(texts)
        try:
            vectors = model.encode(
                texts,
                batch_size=self.batch_size,
                normalize_embeddings=self.normalize_embeddings,
                show_progress_bar=False,
            )
        except TypeError:
            vectors = model.encode(texts)
        return [
            [float(value) for value in vector]
            for vector in getattr(vectors, "tolist", lambda: vectors)()
        ]
