"""Text-to-speech client for Kokoro-82M."""

from __future__ import annotations

import httpx

from trg.config.settings import Settings, get_settings


class KokoroClient:
    """Kokoro TTS HTTP client (returns WAV bytes)."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._client = httpx.AsyncClient(timeout=60.0)

    async def synthesise(
        self,
        text: str,
        *,
        voice: str = "af_bella",
        speed: float = 1.0,
        format: str = "wav",
    ) -> bytes:
        """Return audio bytes (wav/mp3/opus)."""
        url = f"{self.settings.kokoro_url.rstrip('/')}/v1/audio/speech"
        payload = {
            "model": "kokoro",
            "input": text,
            "voice": voice,
            "speed": speed,
            "response_format": format,
        }
        resp = await self._client.post(url, json=payload)
        resp.raise_for_status()
        return resp.content

    async def list_voices(self) -> list[str]:
        url = f"{self.settings.kokoro_url.rstrip('/')}/v1/audio/voices"
        try:
            resp = await self._client.get(url)
            resp.raise_for_status()
            data = resp.json()
            return [v["id"] for v in data.get("voices", [])]
        except Exception:
            return ["af_bella", "af_sky", "am_adam", "bf_emma"]

    async def close(self) -> None:
        await self._client.aclose()
