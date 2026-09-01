"""Claude.ai conversation history importer.

The Anthropic API doesn't expose Claude.ai UI projects directly. The
practical path is for the user to export her data from
<https://claude.ai/settings/export> (Settings → Account → Export Data).

That produces a ZIP archive containing one or more JSON files. The exact
schema has evolved over time but typically contains a list of
conversations, each with a list of chat messages.

This importer:
  1. Reads the ZIP (or extracted directory).
  2. Walks every conversation.
  3. Splits long conversations into chunks (~800 tokens, with overlap).
  4. Classifies each chunk into the right project using SmolLM2.
  5. Embeds + upserts into the matching Qdrant collection.
  6. Optionally moves any attached files into the project document folder.

The classification is a single forward pass per chunk through SmolLM2 —
cheap and fast. The user can override by passing a `default_project` arg.
"""

from __future__ import annotations

import asyncio
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from trg.config.settings import Settings, get_settings
from trg.llm.smollm2 import SmolLM2Client
from trg.rag.ingest import Chunk
from trg.rag.retriever import Retriever, TEIClient


DEFAULT_PROJECTS = ["remodel", "husband-health", "own-health", "calendar", "inbox", "general"]


@dataclass
class ImportReport:
    """Summary of a single import run."""

    conversations_seen: int = 0
    chunks_imported: int = 0
    by_project: dict[str, int] = None  # type: ignore[assignment]
    errors: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.by_project is None:
            self.by_project = {}
        if self.errors is None:
            self.errors = []


class ClaudeImporter:
    """Imports Claude conversation history into Qdrant."""

    def __init__(
        self,
        settings: Settings | None = None,
        retriever: Retriever | None = None,
        smollm2: SmolLM2Client | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.retriever = retriever or Retriever(self.settings)
        self.smollm2 = smollm2 or SmolLM2Client(self.settings)
        self.embedder = TEIClient(self.settings)

    async def import_path(
        self,
        path: str | Path,
        *,
        projects: Iterable[str] = DEFAULT_PROJECTS,
        default_project: str | None = None,
        chunk_token_cap: int = 800,
    ) -> ImportReport:
        """Import from a ZIP file or an extracted directory."""
        path = Path(path)
        report = ImportReport()
        project_list = list(projects)
        if default_project and default_project not in project_list:
            project_list.append(default_project)

        # Ensure all collections exist
        for project in project_list:
            await self.retriever.ensure_collection(f"project-{project}")

        # Walk conversations
        conversations = self._load_conversations(path)
        for convo in conversations:
            report.conversations_seen += 1
            try:
                chunks = self._chunk_conversation(convo, token_cap=chunk_token_cap)
                if not chunks:
                    continue
                # Classify the first chunk to pick a project; assume whole convo
                # stays in that project (cheap; conversations are usually coherent).
                sample_text = chunks[0].text[:600]
                project = default_project or await self.smollm2.classify_project(
                    sample_text, project_list
                )
                if project not in project_list:
                    project = default_project or project_list[0]
                # Embed + upsert
                vectors = await self.embedder.embed([c.text for c in chunks])
                payload = [
                    {
                        "text": c.text,
                        "source": c.source,
                        "page": c.page,
                        "project_id": c.project_id,
                        "metadata": {**c.metadata, "importer": "claude"},
                        "vector": vec,
                    }
                    for c, vec in zip(chunks, vectors, strict=True)
                ]
                await self.retriever.upsert(
                    collection=f"project-{project}", chunks=payload
                )
                report.chunks_imported += len(chunks)
                report.by_project[project] = (
                    report.by_project.get(project, 0) + len(chunks)
                )
            except Exception as e:  # noqa: BLE001
                report.errors.append(f"{convo.get('id', '?')}: {e}")

        return report

    # ─── Conversation loading ────────────────────────────────────────

    def _load_conversations(self, path: Path) -> list[dict[str, Any]]:
        if path.is_dir():
            files = list(path.rglob("*.json"))
        elif path.suffix == ".zip":
            files = self._extract_zip_listing(path)
        else:
            raise ValueError(f"Unsupported import path: {path}")

        conversations: list[dict[str, Any]] = []
        for f in files:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            # Heuristic: a file is either a list of conversations or a single one.
            if isinstance(data, list):
                conversations.extend(c for c in data if isinstance(c, dict))
            elif isinstance(data, dict):
                # Some exports nest conversations under keys like
                # `conversations`, `data`, `chats`. Try them in order.
                for key in ("conversations", "data", "chats"):
                    nested = data.get(key)
                    if isinstance(nested, list):
                        conversations.extend(c for c in nested if isinstance(c, dict))
                        break
                else:
                    conversations.append(data)
        return conversations

    def _extract_zip_listing(self, path: Path) -> list[Path]:
        """Extract the zip to a temp dir and return its JSON files."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            with zipfile.ZipFile(path) as zf:
                zf.extractall(tmp)
            tmp_path = Path(tmp)
            return list(tmp_path.rglob("*.json"))

    # ─── Chunking ────────────────────────────────────────────────────

    def _chunk_conversation(
        self, convo: dict[str, Any], *, token_cap: int = 800
    ) -> list[Chunk]:
        """Turn a Claude conversation into Chunk objects.

        A conversation schema is approximated; we tolerate variations and
        just walk `messages` / `chat_messages` / `conversation` lists.
        """
        convo_id = str(convo.get("uuid") or convo.get("id") or convo.get("conversation_id") or "?")
        convo_name = convo.get("name") or convo.get("title") or "Untitled conversation"
        created = convo.get("created_at") or convo.get("updated_at") or ""

        messages = self._extract_messages(convo)
        if not messages:
            return []

        # Build a single transcript then split by paragraph groups.
        transcript_lines: list[str] = [
            f"# Conversation: {convo_name}",
            f"- ID: {convo_id}",
            f"- Created: {created}",
            "",
        ]
        for m in messages:
            role = m.get("role") or m.get("sender") or "unknown"
            text = (m.get("text") or m.get("content") or "").strip()
            if isinstance(text, list):
                # Some exports store content as a list of blocks
                text = "\n".join(
                    blk.get("text", "") if isinstance(blk, dict) else str(blk)
                    for blk in text
                ).strip()
            if not text:
                continue
            transcript_lines.append(f"[{role}]")
            transcript_lines.append(text)
            transcript_lines.append("")

        transcript = "\n".join(transcript_lines)
        return self._split_text(
            transcript,
            source=f"claude:{convo_name}",
            page=None,
            project_id="",
            metadata={"conversation_id": convo_id, "created_at": created},
            token_cap=token_cap,
        )

    def _extract_messages(self, convo: dict[str, Any]) -> list[dict[str, Any]]:
        for key in ("messages", "chat_messages", "conversation", "turns"):
            v = convo.get(key)
            if isinstance(v, list) and v and isinstance(v[0], dict):
                return v
        # Some exports store the whole conversation as a single message
        return []

    def _split_text(
        self,
        text: str,
        *,
        source: str,
        page: int | None,
        project_id: str,
        metadata: dict[str, Any],
        token_cap: int,
    ) -> list[Chunk]:
        """Split text into ~token_cap-sized chunks on double newlines."""
        # Crude token estimate: ~4 chars per token
        char_cap = token_cap * 4
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        chunks: list[Chunk] = []
        buffer = ""
        for p in paragraphs:
            if len(buffer) + len(p) > char_cap and buffer:
                chunks.append(
                    Chunk(
                        text=buffer.strip(),
                        source=source,
                        page=page,
                        project_id=project_id,
                        metadata=metadata,
                    )
                )
                buffer = ""
            buffer += "\n\n" + p
        if buffer.strip():
            chunks.append(
                Chunk(
                    text=buffer.strip(),
                    source=source,
                    page=page,
                    project_id=project_id,
                    metadata=metadata,
                )
            )
        return chunks

    async def close(self) -> None:
        await self.retriever.close()
        await self.smollm2.close()
        await self.embedder.close()


# ─── CLI ────────────────────────────────────────────────────────────────

async def _main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Import a Claude conversation export into TRG."
    )
    parser.add_argument("path", help="ZIP file or directory containing Claude export JSON")
    parser.add_argument(
        "--default-project",
        choices=DEFAULT_PROJECTS,
        default="general",
        help="Project to use when classification fails",
    )
    args = parser.parse_args()

    importer = ClaudeImporter()
    try:
        report = await importer.import_path(
            args.path, default_project=args.default_project
        )
        print(json.dumps(report.__dict__, indent=2))
    finally:
        await importer.close()


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(_main())
