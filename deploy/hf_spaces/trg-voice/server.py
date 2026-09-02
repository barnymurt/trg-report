"""Combined voice service: Whisper STT + Kokoro TTS.

Exposes:
  POST /v1/audio/transcriptions   (Whisper)
  POST /v1/audio/speech           (Kokoro)
  GET  /v1/audio/voices           (Kokoro)
"""

from __future__ import annotations

import io
import logging
from typing import Any

import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("trg-voice")

app = FastAPI(title="TRG Voice", version="0.1.0")

# Lazy-load on first request to keep container startup quick
_whisper = None
_kokoro = None


def get_whisper():
    global _whisper
    if _whisper is None:
        from faster_whisper import WhisperModel

        log.info("loading Whisper distil-large-v3 (CPU int8)…")
        _whisper = WhisperModel(
            "distil-whisper/distil-large-v3",
            device="cpu",
            compute_type="int8",
            download_root="/app/data",
        )
    return _whisper


def get_kokoro():
    global _kokoro
    if _kokoro is None:
        log.info("loading Kokoro-82M…")
        try:
            from kokoro_onnx import Kokoro

            _kokoro = Kokoro("kokoro-v0_19.onnx", "voices.bin")
        except Exception as e:
            log.warning("Kokoro not available: %s", e)
            _kokoro = False  # mark unavailable
    return _kokoro or None


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "whisper": _whisper is not None,
        "kokoro": _kokoro is not None,
    }


@app.post("/v1/audio/transcriptions")
async def transcribe(
    file: UploadFile = File(...),
    language: str = Form("en"),
    response_format: str = Form("json"),
) -> dict[str, Any]:
    """Whisper transcription. Returns OpenAI-compatible JSON."""
    audio_bytes = await file.read()
    model = get_whisper()

    # faster-whisper expects numpy float32
    import tempfile, os

    with tempfile.NamedTemporaryFile(suffix=".audio", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        segments, info = model.transcribe(tmp_path, language=language, vad_filter=True)
        text = " ".join(seg.text.strip() for seg in segments).strip()
        return {
            "text": text,
            "language": info.language,
            "duration": info.duration,
        }
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


class SpeechRequest(BaseModel):
    input: str
    voice: str = "af_bella"
    speed: float = 1.0
    response_format: str = "wav"


@app.post("/v1/audio/speech")
async def speech(req: SpeechRequest) -> Response:
    """Kokoro TTS. Returns WAV bytes."""
    kokoro = get_kokoro()
    if kokoro is None:
        raise HTTPException(status_code=503, detail="Kokoro not available")

    samples, sample_rate = kokoro.create(
        req.input, voice=req.voice, speed=req.speed, is_phonemes=False
    )
    audio = (np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0) * 32767).astype(np.int16)

    # Wrap PCM in a WAV header (16-bit mono)
    buf = io.BytesIO()
    import wave

    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(audio.tobytes())
    return Response(content=buf.getvalue(), media_type="audio/wav")


@app.get("/v1/audio/voices")
async def voices() -> dict[str, Any]:
    return {
        "voices": [
            {"id": "af_bella", "name": "Bella (US female)"},
            {"id": "af_sky", "name": "Sky (US female)"},
            {"id": "am_adam", "name": "Adam (US male)"},
            {"id": "bf_emma", "name": "Emma (UK female)"},
        ]
    }
