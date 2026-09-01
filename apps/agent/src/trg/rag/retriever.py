"""RAG retrieval pipeline.

Pipeline:
  1. Embed the query (bge-small-en-v1.5 or bge-m3)
  2. Hybrid search in Qdrant (dense + sparse for bge-m3)
  3. Rerank top-K candidates with bge-reranker-v2-m3
  4. Return final top-N with source metadata
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

import httpx
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qm

from trg.config.settings import Settings, get_settings


@dataclass
class RetrievedChunk:
    """A chunk returned from the retrieval pipeline."""

    id: str
    text: str
    score: float
    source: str
    page: int | None
    project_id: str
    metadata: dict[str, Any]


class TEIClient:
    """Text Embeddings Inference client (Hugging Face)."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._client = httpx.AsyncClient(timeout=30.0)

    async def embed(self, texts: list[str], model: str = "en") -> list[list[float]]:
        """Embed texts. model='en' or 'multilingual'."""
        url = (
            self.settings.tei_url
            if model == "en"
            else self.settings.tei_url.replace(":8080", ":8082")
        )
        url = f"{url.rstrip('/')}/v1/embeddings"
        payload = {"input": texts, "model": "embed"}
        resp = await self._client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return [item["embedding"] for item in sorted(data["data"], key=lambda x: x["index"])]

    async def close(self) -> None:
        await self._client.aclose()


class RerankerClient:
    """bge-reranker-v2-m3 via TEI rerank endpoint."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._client = httpx.AsyncClient(timeout=30.0)

    async def rerank(
        self, query: str, documents: list[str], top_k: int
    ) -> list[tuple[int, float]]:
        """Return [(doc_index, score)] sorted by score desc, top_k results."""
        url = f"{self.settings.reranker_url.rstrip('/')}/v1/rerank"
        payload = {
            "query": query,
            "texts": documents,
            "top_n": top_k,
            "return_documents": False,
        }
        resp = await self._client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return [(item["index"], item["score"]) for item in data]

    async def close(self) -> None:
        await self._client.aclose()


class Retriever:
    """End-to-end retrieval: embed → Qdrant search → rerank."""

    def __init__(
        self,
        settings: Settings | None = None,
        embedder: TEIClient | None = None,
        reranker: RerankerClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.embedder = embedder or TEIClient(self.settings)
        self.reranker = reranker or RerankerClient(self.settings)
        self.qdrant = AsyncQdrantClient(
            url=self.settings.qdrant_url,
            api_key=self.settings.qdrant_api_key or None,
        )

    async def retrieve(
        self,
        *,
        query: str,
        collection: str,
        project_id: str,
        top_k: int | None = None,
        final_k: int | None = None,
        rerank: bool = True,
    ) -> list[RetrievedChunk]:
        """Retrieve top-final_k chunks from a collection, optionally reranked."""
        top_k = top_k or self.settings.rerank_top_k
        final_k = final_k or self.settings.rerank_final_k

        # 1. Embed query
        query_vec = (await self.embedder.embed([query]))[0]

        # 2. Vector search in Qdrant
        search_result = await self.qdrant.search(
            collection_name=collection,
            query_vector=("dense", query_vec),
            limit=top_k,
            with_payload=True,
            with_vectors=False,
            query_filter=qm.Filter(
                must=[
                    qm.FieldCondition(
                        key="project_id",
                        match=qm.MatchValue(value=project_id),
                    )
                ]
            ),
        )

        if not search_result:
            return []

        candidates = [
            (
                hit.id,
                hit.payload.get("text", ""),
                hit.payload.get("source", ""),
                hit.payload.get("page"),
                hit.payload.get("metadata", {}),
                hit.score,
            )
            for hit in search_result
        ]

        # 3. Rerank (optional)
        if rerank and len(candidates) > final_k:
            docs = [c[1] for c in candidates]
            ranked = await self.reranker.rerank(query, docs, final_k)
            candidates = [candidates[i] for i, _ in ranked]

        return [
            RetrievedChunk(
                id=c[0],
                text=c[1],
                score=float(c[5]),
                source=str(c[2]),
                page=c[3],
                project_id=project_id,
                metadata=c[4] if isinstance(c[4], dict) else {},
            )
            for c in candidates[:final_k]
        ]

    async def ensure_collection(self, name: str, vector_size: int = 384) -> None:
        """Create the collection if it doesn't exist."""
        if not await self.qdrant.collection_exists(name):
            await self.qdrant.create_collection(
                collection_name=name,
                vectors_config={
                    "dense": qm.VectorParams(
                        size=vector_size,
                        distance=qm.Distance.COSINE,
                    ),
                },
            )

    async def upsert(
        self,
        *,
        collection: str,
        chunks: list[dict[str, Any]],
    ) -> None:
        """Upsert chunks (each: {id, text, source, page, project_id, metadata, vector})."""
        if not chunks:
            return
        points = [
            qm.PointStruct(
                id=hashlib.md5(
                    f"{collection}:{c['source']}:{c.get('page', '')}:{i}".encode()
                ).hexdigest(),
                vector={"dense": c["vector"]},
                payload={
                    "text": c["text"],
                    "source": c["source"],
                    "page": c.get("page"),
                    "project_id": c.get("project_id", ""),
                    "metadata": c.get("metadata", {}),
                },
            )
            for i, c in enumerate(chunks)
        ]
        await self.qdrant.upsert(collection_name=collection, points=points)

    async def close(self) -> None:
        await self.embedder.close()
        await self.reranker.close()
        await self.qdrant.close()
