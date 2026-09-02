---
title: TRG Voice
emoji: 🎙️
colorFrom: green
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: Whisper STT + Kokoro TTS in one Space
---

# TRG Voice

Combined Space serving:
- **POST /v1/audio/transcriptions** — distil-whisper/distil-large-v3 (CPU int8)
- **POST /v1/audio/speech** — Kokoro-82M
- **GET  /v1/audio/voices**

See the main repo: <https://github.com/barnymurt/trg-report>

## Why one Space?

Bundling Whisper + Kokoro into a single Space halves the cold-start cost
and avoids cross-Space latency. Models share the same Python runtime and
HF cache.
