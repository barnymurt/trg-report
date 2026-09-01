"""Document ingestion pipeline.

Takes raw documents (PDFs, images, plain text) → Docling (granite-docling-258M)
for layout-aware extraction → chunking → embedding → Qdrant upsert.
"""

from __future__ import annotations

import hashlib
import mimetypes
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from trg.config.settings import Settings, get_settings
from trg.rag.retriever import Retriever, TEIClient


@dataclass
class Chunk:
    """A single chunk produced from ingestion."""

    text: str
    source: str
    page: int | None
    project_id: str
    metadata: dict[str, Any]


class IngestionPipeline:
    """End-to-end ingest: file → Docling → chunks → embeddings → Qdrant."""

    def __init__(
        self,
        settings: Settings | None = None,
        retriever: Retriever | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.retriever = retriever or Retriever(self.settings)
        self.embedder = TEIClient(self.settings)
        self._docling = httpx.AsyncClient(
            base_url=self.settings.docling_url.rstrip("/"),
            timeout=300.0,
        )

    async def ingest_file(
        self,
        *,
        path: str | Path,
        project_id: str,
        collection: str,
    ) -> int:
        """Ingest a single file. Returns number of chunks added."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(path)

        mime, _ = mimetypes.guess_type(path)
        chunks = await self._extract_chunks(path, mime)
        if not chunks:
            return 0

        await self.retriever.ensure_collection(collection)
        texts = [c.text for c in chunks]
        vectors = await self.embedder.embed(texts)

        payload = [
            {
                "text": c.text,
                "source": c.source,
                "page": c.page,
                "project_id": c.project_id,
                "metadata": c.metadata,
                "vector": vec,
            }
            for c, vec in zip(chunks, vectors, strict=True)
        ]
        await self.retriever.upsert(collection=collection, chunks=payload)
        return len(chunks)

    async def _extract_chunks(self, path: Path, mime: str | None) -> list[Chunk]:
        """Route to the right extractor based on MIME type."""
        if mime == "application/pdf" or path.suffix.lower() == ".pdf":
            return await self._extract_pdf(path)
        if mime and mime.startswith("image/"):
            return await self._extract_image(path)
        # Plain text / markdown fallback
        return await self._extract_text(path)

    async def _extract_pdf(self, path: Path) -> list[Chunk]:
        """Send the PDF to Docling, return layout-aware chunks."""
        with path.open("rb") as f:
            files = {"file": (path.name, f, "application/pdf")}
            resp = await self._docling.post("/v1/convert/file", files=files)
        resp.raise_for_status()
        data = resp.json()
        chunks: list[Chunk] = []
        for page in data.get("pages", []):
            page_num = page.get("page_number", 0)
            for segment in page.get("segments", []):
                text = segment.get("text", "").strip()
                if not text or len(text) < 20:
                    continue
                chunks.append(
                    Chunk(
                        text=text,
                        source=str(path.name),
                        page=page_num,
                        project_id="",
                        metadata={
                            "section": segment.get("section"),
                            "doc_type": segment.get("doc_type", "paragraph"),
                        },
                    )
                )
        return chunks

    async def _extract_image(self, path: Path) -> list[Chunk]:
        """OCR via Docling (granite-docling-258M has built-in OCR)."""
        with path.open("rb") as f:
            files = {"file": (path.name, f, "image/png")}
            resp = await self._docling.post("/v1/convert/file", files=files)
        resp.raise_for_status()
        data = resp.json()
        return [
            Chunk(
                text=seg.get("text", "").strip(),
                source=str(path.name),
                page=0,
                project_id="",
                metadata={"doc_type": "ocr"},
            )
            for page in data.get("pages", [])
            for seg in page.get("segments", [])
            if seg.get("text", "").strip()
        ]

    async def _extract_text(self, path: Path) -> list[Chunk]:
        """Plain text / markdown ingestion: split into ~800-token chunks."""
        text = path.read_text(encoding="utf-8", errors="ignore")
        # Cheap split on double newline + token-cap fallback
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        chunks: list[Chunk] = []
        buffer = ""
        for p in paragraphs:
            if len(buffer) + len(p) > 3000 and buffer:
                chunks.append(
                    Chunk(
                        text=buffer,
                        source=str(path.name),
                        page=None,
                        project_id="",
                        metadata={"doc_type": "text"},
                    )
                )
                buffer = ""
            buffer += "\n\n" + p
        if buffer:
            chunks.append(
                Chunk(
                    text=buffer.strip(),
                    source=str(path.name),
                    page=None,
                    project_id="",
                    metadata={"doc_type": "text"},
                )
            )
        return chunks

    async def close(self) -> None:
        await self.embedder.close()
        await self._docling.aclose()
        await self.retriever.close()


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def safe_filename(name: str) -> str:
    """Sanitise a filename for the document store."""
    keep = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.")
    return "".join(c if c in keep else "_" for c in name)
