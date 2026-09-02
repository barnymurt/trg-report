---
title: TRG Embeddings
emoji: 🧮
colorFrom: yellow
colorTo: orange
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: TEI embeddings (bge-small-en-v1.5)
---

# TRG Embeddings

Hugging Face Text Embeddings Inference running `BAAI/bge-small-en-v1.5`
(384-dim, English, top MTEB-retrieval at this size).

Endpoint:
- `POST /v1/embeddings` — OpenAI-compatible
- `GET  /health`

See the main repo: <https://github.com/barnymurt/trg-report>

## Notes

For now we use just one model. If recall suffers in production, deploy a
second Space running `bge-reranker-v2-m3` and point `RERANKER_URL` at it.
