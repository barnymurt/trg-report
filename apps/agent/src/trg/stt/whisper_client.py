"""Speech-to-text client for distil-whisper (faster-whisper API)."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from trg.config.settings import Settings, get_settings


@dataclass
class TranscriptionResult:
    text: str
    language: str
    duration_sec: float


class WhisperClient:
    """faster-whisper HTTP client (with demo fallback)."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._client = httpx.AsyncClient(timeout=120.0)

    async def transcribe(
        self,
        audio_bytes: bytes,
        *,
        language: str = "en",
        filename: str = "audio.webm",
    ) -> TranscriptionResult:
        if self.settings.trg_demo_mode:
            return TranscriptionResult(
                text="(demo) tell me about the kitchen project",
                language=language,
                duration_sec=2.0,
            )
        url = f"{self.settings.whisper_url.rstrip('/')}/v1/audio/transcriptions"
        files = {"file": (filename, audio_bytes, "application/octet-stream")}
        data = {"language": language, "response_format": "json"}
        resp = await self._client.post(url, files=files, data=data)
        resp.raise_for_status()
        result = resp.json()
        return TranscriptionResult(
            text=result.get("text", "").strip(),
            language=result.get("language", language),
            duration_sec=float(result.get("duration", 0.0)),
        )

    async def close(self) -> None:
        await self._client.aclose()
