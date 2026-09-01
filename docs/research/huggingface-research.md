# Hugging Face Research — Multi-Agent Claude System with RAG

Research compiled from Hugging Face documentation, model cards, the HF Blog, GitHub repos, and the Hugging Face Inference Endpoints / Inference Providers docs. All findings are evidence-based on what is currently shipped and supported. All model cards and project URLs cited below were fetched directly.

Goal: build an AI agent team that runs multiple projects, uses Claude as its LLM, employs RAG to minimise hallucinations and preserve context, and is cost-conscious (memory and tokens are expensive) with task-appropriate model selection.

---

## 1. Agent / Multi-agent Frameworks

### 1.1 smolagents — Hugging Face's flagship agent library

- **URL:** [github.com/huggingface/smolagents](https://github.com/huggingface/smolagents) (29.1k stars, Apache-2.0); docs at [huggingface.co/docs/smolagents](https://huggingface.co/docs/smolagents/index).
- **What it is:** A barebones (~1k LoC) Python library for building agents. Has first-class support for `CodeAgent` (writes actions as Python code), and a more conventional `ToolCallingAgent` for JSON-style tool calls.
- **Model-agnostic — Claude support is documented.** README explicitly shows how to wire Claude via `LiteLLMModel(model_id="anthropic/claude-4-sonnet-latest", api_key=os.environ["ANTHROPIC_API_KEY"])`. Also supports `OpenAIModel`, `AzureOpenAIModel`, `AmazonBedrockModel`, `TransformersModel`, and `InferenceClientModel` (HF router).
- **Tool-calling:** MCP server tool collections, LangChain tool imports, and Hugging Face Spaces-as-tools. Two agent types cover both worlds: code agents (better benchmarks per HF's own research, "30% fewer steps") and JSON tool-calling agents.
- **Multi-agent:** Supported — `MultiStepAgent` hierarchy lets you nest a managed agent inside a manager agent.
- **Security:** Built-in `LocalPythonExecutor` is explicitly *not* a security boundary; you must use E2B, Blaxel, Modal, or Docker sandboxes for real isolation.
- **Hub integrations:** Agents and tools can be pushed/pulled to the Hub as Gradio Spaces — good for sharing across a team.

**Pros for our use case:**
- Native Claude/Anthropic binding via LiteLLM is one line.
- Model can be selected per-agent (`CodeAgent(tools=..., model=claude_for_complex)`, `CodeAgent(tools=..., model=qwen_for_cheap)`).
- Hub sharing fits a multi-team, multi-project setup.
- `CodeAgent` paradigm reduces LLM round-trips → lower token cost.

**Cons:**
- Smolagents' own benchmarks show Claude-family tooling sometimes trails open models in raw agentic benchmarks — but the library is the orchestration layer, not the model choice.
- Sandboxing is your responsibility.

**Recommendation:** **Adopt as the orchestration backbone.** It explicitly lists `anthropic/claude-4-sonnet-latest` as a first-class target, supports per-agent model selection (critical for cost control), and is the only framework HF actively maintains and integrates into their Hub share/load ecosystem.

### 1.2 Hugging Face Agent Course / AI Agents Course

- **URL:** [huggingface.co/learn/agents-course](https://huggingface.co/learn/agents-course/unit0/introduction).
- **What it is:** Hugging Face's official training curriculum. Syllabus covers smolagents, LangGraph, and LlamaIndex; hands-on units; a student leaderboard; a free certificate.
- **Useful for:** Onboarding team members, picking up patterns, and benchmarking on the student challenge.

**Recommendation:** Strongly recommended as a learning reference; do not rely on it as a runtime framework.

### 1.3 smol-course (separate from smolagents)

- **URL:** [huggingface.co/learn/smol-course](https://huggingface.co/learn/smol-course) — covers fine-tuning (SFT, DPO, preference alignment, VLM) with TRL + Transformers, not agents.
- **Useful for:** If we need to fine-tune small routing/utility models later. Not required for the agent core.

### 1.4 Other Agent Frameworks Hugging Face Surfaces

- **LangGraph / LlamaIndex:** Both are explicitly taught in the HF Agents Course alongside smolagents.
- **Transformers Agent (legacy):** The original `transformers.agents` is deprecated in favour of smolagents.

**Recommendation:** Stick with smolagents. LangGraph is excellent but is tied more to LangChain's stack; LlamaIndex is more RAG-centric than agent-centric.

---

## 2. Embedding Models for RAG

The Hugging Face Hub hosts the canonical benchmark for text embeddings: the [MTEB leaderboard](https://huggingface.co/spaces/mteb/leaderboard). Findings from MTEB scores cited below come from the official BGE model card [BAAI/bge-large-en-v1.5](https://huggingface.co/BAAI/bge-large-en-v1.5).

### 2.1 BGE family (BAAI)

- **Top English models:** `BAAI/bge-large-en-v1.5` (1024-d, 512-tok, MTEB avg **64.23**, retrieval avg **54.29**), `BAAI/bge-base-en-v1.5` (768-d), `BAAI/bge-small-en-v1.5` (384-d).
- **Multilingual hybrid:** `BAAI/bge-m3` — supports dense + sparse (lexical) + multi-vector (ColBERT) retrieval, 8192-tok context, 100+ languages. Has hybrid (dense + sparse) on a single forward pass.
- **Hostability:** ONNX and safetensors variants available; works with HF's Text Embeddings Inference (TEI) server.
- **Pros:** Top-tier MTEB scores, mature, MIT-licensed, the de facto reference on HF. BGE-M3's hybrid retrieval substantially helps on long/legal/code domains where pure semantics misses exact matches.
- **Cons:** English BGE tops out at 512 tokens; longer docs must be chunked.

### 2.2 E5 / Multilingual-E5 (intfloat)

- `intfloat/e5-large-v2` (1024-d, 512-tok, MTEB 62.25), `intfloat/multilingual-e5-large` (100+ languages).
- **Critical requirement:** E5 must be invoked with `"query: "` and `"passage: "` prefixes — failure to do so degrades quality. Less forgiving than BGE.
- **Pros:** Strong retrieval baseline.
- **Cons:** Strict prefix requirement complicates production use; BGE has no such hard requirement.

### 2.3 GTE (Alibaba, thenlper)

- `thenlper/gte-large` (1024-d, 512-tok, MTEB 63.13), `thenlper/gte-base`, `thenlper/gte-small`.
- Also more recent `Alibaba-NLP/gte-Qwen2-7B-instruct` and similar LLM-based embedders if you want SOTA.
- **Pros:** Competitive quality, fine-tuned on a large relevance corpus.
- **Cons:** English only.

### 2.4 Sentence-Transformers top picks

- `sentence-transformers/all-mpnet-base-v2` (768-d, 110M) — reliable general-purpose baseline.
- `sentence-transformers/all-MiniLM-L6-v2` (384-d, 22M) — extremely fast, lower quality; useful for routing/classification routing.
- `sentence-transformers/paraphrase-multilingual-mpnet-base-v2` (768-d, 50+ langs).
- **Pros:** Excellent tooling, ubiquitous, the sentence-transformers library gives you a single API across all of these.
- **Cons:** MTEB-retrieval lag behind BGE-large by several points.

### 2.5 SOTA frontier (heavier, optional)

- `mixedbread-ai/mxbai-embed-large-v1` (MTEB avg **64.68**, retrieval **54.39**) — Matryoshka support so you can truncate dimensions at inference for cost control.
- `nvidia/NV-Embed-v2` — ranks #1 on MTEB (72.31 avg, retrieval 62.65) at the time of the model card but is 8B parameters and CC-BY-NC-4.0, **non-commercial**. Rules itself out for a commercial build.
- `Alibaba-NLP/gte-Qwen2-...` family — LLM-based, very high quality, slower and more expensive per inference than BERT-size embedders.

### 2.6 Comparison summary (MTEB avg / Retrieval subscore / dims / license)

| Model | MTEB Avg | Retrieval | Dims | Lang | Commercial OK |
|---|---|---|---|---|---|
| `NV-Embed-v2` | 72.31 | 62.65 | 4096 | EN | **No (CC-BY-NC-4.0)** |
| `mxbai-embed-large-v1` | 64.68 | 54.39 | 1024 (MRL) | EN | Yes |
| `bge-large-en-v1.5` | 64.23 | 54.29 | 1024 | EN | Yes (MIT) |
| `gte-large` | 63.13 | 52.22 | 1024 | EN | Yes |
| `e5-large-v2` | 62.25 | 50.56 | 1024 | EN | Yes (MIT) |
| `all-mpnet-base-v2` | 57.78 | 43.81 | 768 | EN | Yes |
| `bge-m3` | strong multilingual (60s) | strong | 1024 (8192 tok) | 100+ | Yes |
| `all-MiniLM-L6-v2` | ~56 | ~42 | 384 | EN | Yes (22M params!) |

### 2.7 Cost-quality recommendation

For a production multi-project RAG:
- **Primary embedder (English docs):** `BAAI/bge-large-en-v1.5`. Top MTEB-retrieval among commercially-licensed English models, 1024-d, MIT. Run via TEI for high-throughput serving.
- **Primary embedder (multilingual or long docs, 8192 tok):** `BAAI/bge-m3` — single forward pass yields dense + sparse + multi-vector, perfect for hybrid retrieval.
- **Cheap fallback / routing embeddings (micro, fast):** `sentence-transformers/all-MiniLM-L6-v2` (384-d, 22M params, runs anywhere) — great for "is this query about project X vs project Y" classification without touching Claude.
- **Stretch / max quality:** `mixedbread-ai/mxbai-embed-large-v1` with Matryoshka truncation to 512-d — ~40% storage reduction with minimal quality loss.

---

## 3. Reranking / Cross-Encoders

### 3.1 BGE rerankers

- **URL:** [BAAI/bge-reranker-v2-m3](https://huggingface.co/BAAI/bge-reranker-v2-m3), plus `bge-reranker-base`, `bge-reranker-large`, `bge-reranker-v2-gemma` (LLM-based), `bge-reranker-v2-minicpm-layerwise` (truncatable).
- **Specs:** 0.6B params for v2-m3; 568M for v2-gemma; 2.4B for v2-minicpm-layerwise; max_length 512.
- **Cost efficiency:** v2-m3 (the multilingual XLM-RoBERTa base) is the cheapest decent reranker; v2-minicpm-layerwise lets you pick which layer to cut off for additional speed.
- **Pros:** Plug-and-play via FlagEmbedding's `FlagReranker`. Significant gain on BEIR benchmark charts published in the model card.

### 3.2 mixedbread-ai / mxbai-rerank

- **URL:** [mixedbread-ai/mxbai-rerank-large-v1](https://huggingface.co/mixedbread-ai/mxbai-rerank-large-v1), plus `mxbai-rerank-base-v1` and `mxbai-rerank-xsmall-v1`.
- **Headline:** NDCG@10 of **48.8** on BEIR (vs. 45.2 for bge-reranker-large), per the model's own eval table. Smaller than BGE v2-m3 (~0.4B).
- **Pros:** Best BEIR score among open rerankers in this size class as of the card.
- **Cons:** Not hosted by HF Inference Providers yet — must self-host or use the mixedbread.ai API.

### 3.3 When reranking helps vs. hurts

- **Helps:** When you retrieve top-50 to top-200 candidates with a fast bi-encoder, then rerank with a cross-encoder to top-5–10. Standard 2-stage pattern.
- **Hurts:** When you already retrieved top-k where k is small (≤5) and your embedder is strong (e.g., bge-m3 or NV-Embed) — rerank latency (~150 ms/cross-encode on CPU, faster on GPU with TEI) adds up. Also hurts at scale if every query invokes a cross-encoder instead of being cached.
- **Rule of thumb for cost-sensitive:** Rerank top-20 from the embedder down to top-5 for LLM context. Keep reranker call off the hot path for "yes/no" classification tasks — use embedder similarity threshold instead.

**Recommendation:** **`BAAI/bge-reranker-v2-m3` as the default reranker** (works in any language, small, plays nicely with BGE embedders). Promote to **`mixedbread-ai/mxbai-rerank-large-v1`** if recall-critical projects demand it.

---

## 4. Document Processing / Chunking

### 4.1 SmolDocling & Granite-Docling (vision-language doc models)

- **[docling-project/SmolDocling-256M-preview](https://huggingface.co/docling-project/SmolDocling-256M-preview)** — 256M-param VLM for end-to-end document conversion; outputs structured DocTags that preserve layout, tables, code, formulas, charts, captions. Avg 0.35 s/page on A100 via vLLM.
- **[ibm-granite/granite-docling-258M](https://huggingface.co/ibm-granite/granite-docling-258M)** — successor (release Sep 2025), Apache-2.0. Beats SmolDocling on every metric published: table TEDS 0.97 vs 0.82, equation recognition, code recognition (BLEU 0.98 vs 0.88), OCR (500 vs 338 on OCRBench). Adds Japanese/Arabic/Chinese support.
- **Whole library:** [github.com/docling-project/docling](https://github.com/docling-project/docling) — provides the vlm pipeline and downstream Markdown/HTML/JSON export. Plays well with `vllm`/`transformers`/`onnx`.
- **Pros:** End-to-end (no chain of separate OCR/layout/table models to maintain); 256M params runs cheaply; layout-aware chunks reduce RAG retrieval noise on figures and tables; ideal for the document-heavy multi-project use case.
- **Cons:** Each page render is a generative step, slightly slower than classical OCR but vastly cleaner for RAG.

### 4.2 LayoutLM / DocLayNet lineage

- The DocLayNet dataset (IBM Research) feeds Docling; LayoutLM-derived models are upstream of Docling's legacy pipeline. SmolDocling / Granite-Docling effectively subsume LayoutLMv3 for our purposes.

### 4.3 Chunking strategies recommended

- **Layout-aware / structure-aware chunking** (Docling's `HybridChunker`, RecursiveCharacterTextSplitter with markdown headers) — preserve section boundaries; quote text + bounding-box/page metadata for citation.
- **Semantic chunking** — `semantic-chunker` style: embed each sentence, merge adjacent sentences above similarity threshold. Costly but useful for very long docs.
- **Token-based fixed-window** with overlap — last resort. Always store the source chunk_id and page number so the LLM can cite.

### 4.4 Small / specialised document models

- For pure OCR on scanned images, classic `microsoft/trocr-base-printed` etc. remain. SmolDocling/Granite-Docling already do OCR internally, so for greenfield you typically don't need a separate OCR model.

**Recommendation:**
- **Adopt Granite-Docling-258M** as the document ingest workhorse — it returns structured DocTags that you can feed straight into a hybrid chunker, preserving headings, tables, and figures.
- Use HF's **Docling** library as the chunking/coercion layer (Markdown export + RecursiveCharacter splitter with 800-token chunks / 100-token overlap is a sane default).

---

## 5. Vector Databases / Retrieval Infrastructure

### 5.1 Vector library: FAISS (Meta, on the HF-adjacent ecosystem)

- **URL:** [github.com/facebookresearch/faiss](https://github.com/facebookresearch/faiss) (40.8k stars, MIT). Scales to billions of vectors, supports CPU + GPU.
- Hugging Face doesn't host a vector DB but its **Text Embeddings Inference (TEI)** server ships with FAISS-style endpoints, and many HF projects use FAISS directly. The BAAI FAQ explicitly recommends FAISS-backed hybrid retrieval with `bge-m3`.

### 5.2 Text Embeddings Inference (TEI)

- **URL:** [huggingface.co/docs/text-embeddings-inference](https://huggingface.co/docs/text-embeddings-inference/en/index).
- **What it does:** HF's purpose-built inference server for embedders and rerankers (FlagEmbedding, GTE, E5, etc.). Flash Attention, dynamic batching, OpenTelemetry, Prometheus metrics, exposes an OpenAI-compatible `/v1/embeddings` endpoint. CPU-only or NVIDIA GPU Docker images.
- This is essentially the missing "vector DB ingestion API" you wire to your own FAISS / Chroma / Qdrant / Milvus.

### 5.3 Vector DBs commonly paired with HF

HF itself doesn't run Chroma/Qdrant/Milvus, but all of them have first-class HF integration:
- **ChromaDB** — easiest "single node" DB; pairs well with LangChain/smolagents; embedded-mode is fine for a single project, server mode for multi-project.
- **Qdrant** — Rust, fast, has hybrid sparse+dense built in (pairs naturally with `bge-m3`'s lexical weights).
- **Milvus / Zilliz** — battle-tested at very large scale; BGE-M3 hybrid retrieval example is published in their docs (cited on the bge-m3 card).
- **FAISS** — if you want everything in-process and don't need a network service. Best when paired with payloads in SQLite/Parquet.

### 5.4 HF-native retrieval & storage

- **HF Hub datasets:** Use HF datasets as a versioned, multi-project document store. Cheap, has versioning, ACLs via orgs.
- **Buckets:** New HF Storage Buckets for raw PDF/blob storage.
- **No hosted FAISS-as-a-service** is offered on HF today; you self-host.

**Recommendation:**
- **Vector DB: Qdrant** (single self-hosted instance, multi-project namespaced collections, supports hybrid dense+sparse — leverages `bge-m3`'s sparse weights directly). Chroma is fine for prototyping.
- **Embeddings server: HF Text Embeddings Inference (TEI)** with `bge-large-en-v1.5` (EN-only projects) and `bge-m3` (multilingual/long-doc projects).
- **Document store: HF Datasets** for raw/processed text chunks (multi-project revisioning is free).
- **Raw blobs (PDFs etc.): HF Storage Buckets.**

---

## 6. Inference Options & Cost Optimisation

### 6.1 Inference Providers (serverless, pay-as-you-go)

- **URL:** [huggingface.co/docs/inference-providers](https://huggingface.co/docs/inference-providers).
- **17 third-party providers** route through HF: Together, Groq, Cohere, Cerebras, DeepInfra, Fireworks, Fal-AI, Featherless, Scaleway, HF-Inference, Replicate, Novita, Nscale, OVHcloud, Public AI, WaveSpeedAI, Z.ai, Baseten. OpenAI-compatible endpoint at `https://router.huggingface.co/v1`.
- Supports chat (LLM), VLM, feature extraction (embeddings), text-to-image, text-to-video, and speech-to-text.
- Routing policies: `:fastest` (default), `:cheapest`, `:preferred`. **Pick `:cheapest` for cost-sensitive model routing.**

### 6.2 Inference Endpoints (dedicated instances)

- **URL:** [huggingface.co/docs/inference-endpoints/pricing](https://huggingface.co/docs/inference-endpoints/pricing).
- Sample prices (AWS, per hour, billed by minute):
  - CPU `intel-spr x2` (2 vCPU / 4 GB): $0.067/hr → ~$49/mo
  - GPU T4 x1 (16 GB): $0.5/hr → ~$365/mo
  - GPU L4 x1 (24 GB): $0.8/hr → ~$584/mo
  - GPU A10G x1 (24 GB): $1.0/hr → ~$730/mo
  - GPU A100 x1 (80 GB): $2.5/hr → ~$1825/mo
  - GPU H100 x1: ~$10/hr → ~$7300/mo
- Supports vLLM, TGI, SGLang, TEI, llama.cpp — drop any HF model in.

### 6.3 Free / cheap tiers

- **Free HF users:** $0.10/month credit (covers many embeddings for a small project).
- **PRO users / Org seats:** $2.00/month each — can be spent on Inference Providers, Endpoints, Spaces GPU, Jobs.
- **Team/Enterprise organisations:** Pooled credits per seat, billing centralised via `X-HF-Bill-To` header.

### 6.4 Local vs hosted tradeoffs

- **Hosted inference** = predictable $/token, no GPU ops, scale-to-zero.
- **Local (TEI / vLLM / llama.cpp on your own GPU)** = best per-token cost at high volume, but you wear idle hardware cost.
- A common pattern: small embedder & reranker on TEI as a long-running endpoint (cheap, high-throughput, always warm), Claude via Anthropic API only when reasoning is needed.

### 6.5 Small models for routing / classification (cost lever)

This is the single biggest cost lever for a Claude-centric system: do **not** route to Claude for trivial classification. Use a small HF model instead.

- **Router / cheap classifier (1B-class):**
  - `HuggingFaceTB/SmolLM2-1.7B-Instruct` — Apache-2.0; one of the strongest sub-2B chat models (IFEval 56.7, MT-Bench 6.13 vs Qwen2.5-1.5B-Instruct 47.4 / 6.52).
  - `HuggingFaceTB/SmolLM2-360M-Instruct` — ~360M, runs on CPU, MT-Bench 3.66.
  - `Qwen/Qwen2.5-1.5B-Instruct` — strong small generalist.
  - `openbmb/MiniCPM3-4B` — 4B, scores higher than GPT-3.5-Turbo on many benchmarks, has function-calling support, 32k context.
- **Embedding-distance classifier (cheapest):** `sentence-transformers/all-MiniLM-L6-v2`. Compare an incoming query to a known-good set of labelled example queries via cosine similarity; pick the project/agent. Sub-millisecond per query on CPU.

**Recommendation:**
- Run TEI locally for `bge-large-en-v1.5` + `bge-reranker-v2-m3` + `MiniLM-L6-v2` (CPU) on cheap CPU/T4 hardware ~$365–730/mo.
- Use Anthropic API for Claude only — at Sonnet tier or above for "hard reasoning," Haiku for "easy reasoning."
- Spend PRO credits on occasional heavier hosted inference.
- **Critical pattern:** tiny local embedder decides "which project / which sub-agent / which tool" before any Claude call — saves orders of magnitude in tokens.

---

## 7. Memory / Context Management

### 7.1 Long-context LLMs hosted on HF

- **`Qwen/Qwen2.5-7B-Instruct-1M`** ([link](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-1M)) — 7.61B params, **1,010,000-token context**, Apache-2.0. Sparse-attention via a custom vLLM branch. Needs ~120 GB VRAM (multi-GPU) for 1M tokens.
- **`mistralai/Mistral-Large-Instruct-2407`** ([link](https://huggingface.co/mistralai/Mistral-Large-Instruct-2407)) — 123B, 128k context, native function calling, well-suited as a Claude-substitute for non-Claude reasoning tasks if/when cost pressures. **However, restricted to "Research Purposes" in the Mistral Research License — disqualifies it for commercial agent use** unless a separate license is negotiated.
- **`01-ai/Yi-1.5-9B-32K`** — 9B params, 32k context, Apache-2.0, fits on a single 24 GB card with KV-cache offloading. Practical free-tier long-context.
- Earlier `Qwen2-7B-Instruct`, `Mixtral-8x7B-Instruct-v0.1`, `Llama-3.1-8B-Instruct` all support 128k with RoPE extensions.

### 7.2 Long-context techniques on HF

- **Activation Beacon** (BAAI): [paper](https://huggingface.co/papers/2401.03462) — token-level compression, extends LLM context cheaply. Repo: `FlagOpen/FlagEmbedding/tree/master/Long_LLM/activation_beacon`.
- **LongRoPE / Self-Extend / YaRN** — RoPE scaling recipes widely adopted in HF model cards.
- **StreamingLLM / sliding-window attention** — implementation available via `transformers`'s custom attention hooks.

### 7.3 Summarisation models for compressing agent memory

- **Built-in:** Any HF chat model can run a "summarise this conversation" call cheaply. `SmolLM2-1.7B-Instruct` is the right default for compressing long histories before a Claude call (cost: ~$0 of Claude tokens; cheaper than even Haiku).
- **Dedicated:** `facebook/bart-large-cnn`, `philschmid/bart-large-cnn-samsum`, `Falconsai/text_summarization` (T5-small), `pszemraj/led-large-book-summary` for long docs. All usable via `transformers` pipeline.

### 7.4 Memory architectures that pair with Claude

- **Episodic buffer → compressed summary → vector store** is the canonical pattern.
- For the agent team, give every agent a `ShortTermMemory` (a working list of recent tool results / scratchpad) plus a `LongTermMemory` (vector store of past solutions / facts). Each multi-step agent in smolagents already has built-in `agent.memory`.

**Recommendation:**
- Primary long-context compressor / summariser: `HuggingFaceTB/SmolLM2-1.7B-Instruct` (runs locally or via TEI — keep Claude for comprehension, not for routine compression).
- For very large single-context windows in a non-Claude fallback: `Qwen/Qwen2.5-7B-Instruct-1M` if you have GPU; `Yi-1.5-9B-32K` for a 24 GB card.
- For the agent memory layer: rely on smolagents' `agent.memory` for short-term; FAISS/Qdrant for long-term.

---

## 8. Evaluation / Hallucination Reduction

### 8.1 Ragas — the de facto RAG evaluation toolkit

- **URL:** [github.com/vibrantlabsai/ragas](https://github.com/vibrantlabsai/ragas) (note: formerly `explodinggradients`, now under `vibrantlabsai`; the HF organisation `explodinggradients` still exists with related datasets). Apache-2.0, 15.6k stars.
- **What it does:** Objective RAG/agent metrics — faithfulness, answer relevance, context precision/recall, plus custom LLM-as-judge metrics and synthetic test-data generation. Includes `ragas quickstart rag_eval` template. Works with LangChain, also has callbacks into observability tools.
- **HF hosting:** Not a first-class "HF product" — but the dataset and metric conventions are widely used in HF Spaces (e.g., reference RAG eval Spaces).
- **Recommendation:** Adopt as primary offline/online RAG eval.

### 8.2 Faithfulness scoring models on HF

HF doesn't host a "faithfulness-model" canonical label like it does for `bge-reranker-v2-m3`. Most teams use one of:
- **NLI-based faithfulness** — `MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli` and similar NLI models are reasonable proxies: claim must be entailed by the retrieved context.
- **LLM-as-judge** with a cheap model: `SmolLM2-1.7B-Instruct` or, when you need the strongest judgement, `claude-3-5-haiku` (cheapest Claude) as the judge. Use a stronger Claude only to evaluate final production runs.
- **Citation/attribution enforcement:** prompt the generator to emit `[[chunk_id]]` tokens and use a post-hoc checker (`numpy.where`) to verify each cited chunk is in the retrieved set. Belt-and-braces.

### 8.3 Citation / attribution / quote-verification techniques

- **Quote extraction NLI:** For each cited passage, generate the claim, then run NLI entailment over it.
- **Self-consistency:** Sample multiple responses at low temperature and check overlap on factual claims.
- **Tool-calling hybrid:** Force the agent to retrieve-then-cite by passing `tool_definitions` to Claude with explicit `cite_span` / `cite_source_id` fields.

**Recommendation:**
- Run **ragas nightly** against a held-out set of representative project queries per project.
- Use **NLI-based faithfulness** (`MoritzLaurer/DeBERTa-v3-large-mnli-...` family) for cheap per-answer checks; sample a fraction for Claude-as-judge.
- Always store `(query, retrieved_chunk_ids, response, faithfulness_score, cited_chunk_ids)` as a replayable artefact per interaction. That's how you debug hallucinations later.

---

## 9. Synthesised Recommendation: Top 8 Picks

| # | Component | Recommended pick | Why |
|---|---|---|---|
| 1 | **Agent orchestration** | `huggingface/smolagents` (`CodeAgent` + `ToolCallingAgent`) | Native Claude binding via LiteLLM; per-agent model selection; Hub tools; multi-agent hierarchies. |
| 2 | **Primary embedder (EN)** | `BAAI/bge-large-en-v1.5` via HF **TEI** | MIT, top MTEB-retrieval, mature tooling, low VRAM. |
| 3 | **Primary embedder (multilingual / long)** | `BAAI/bge-m3` via TEI | Dense+sparse+multi-vector in one forward pass; 8192 tokens; 100+ langs. |
| 4 | **Reranker** | `BAAI/bge-reranker-v2-m3` | Small, multilingual, plug-in via FlagEmbedding; optional upgrade to `mxbai-rerank-large-v1` for peak NDCG. |
| 5 | **Document ingest VLM** | `ibm-granite/granite-docling-258M` with `docling-project/docling` | SOTA doc conversion, layout/tables/code/equations preserved, Apache-2.0. |
| 6 | **Vector DB** | **Qdrant** (self-hosted) | Multi-project namespaced collections; hybrid dense+sparse matches bge-m3; production-grade. |
| 7 | **Small routing/utility LLM** | `HuggingFaceTB/SmolLM2-1.7B-Instruct` (via TEI/local vLLM) | Apache-2.0, function-calling capable, MT-Bench 6.13 — solves "which agent, which project, which Claude tier" routing and summarisation without spending Claude tokens. Use `MiniLM-L6-v2` for the cheapest embedding-distance classifier. |
| 8 | **Evaluation** | **Ragas** (ragas-ai OSS) for offline/online RAG metrics + `MoritzLaurer/DeBERTa-v3-large-mnli-*` for cheap per-answer faithfulness NLI + Claude-as-judge for sampled audits. |

**Strong optional additions:**
- `mixedbread-ai/mxbai-embed-large-v1` with Matryoshka 512-d truncation if you need quality headroom on a project.
- `Qwen/Qwen2.5-7B-Instruct-1M` for a non-Claude long-context fallback if a project's memory exceeds Claude's 200k.

---

## 10. Architecture Sketch (text only)

```
+--------------------------- Multi-project orchestrator ----------------------------+
|  smolagents  +  per-project system prompts  +  per-project HF Dataset (chunks)    |
|  Manager agent dispatches to sub-agents: route -> retrieve -> analyze -> reply  |
+------------------------------------------------------------------------------ ---+

                 |                              |
                 v                              v
      [Step 1 — ROUTE]                [Step 2 — RETRIEVE per project]
   SmolLM2-1.7B-Instruct           +---------------+    +----------------+
   (cheap local HF model)          |  Docling      |    |  TEI embedders |
   - decides: project, sub-agent,  |  + Granite-   |    |  - bge-large-en|
     tool, Claude tier             |  Docling-258M |    |    (EN)        |
   - micro-second, ~free           |  parses PDFs, |    |  - bge-m3      |
                                   |  tables,      |    |    (multilingual)
                                   |  figures      |    +----------------+
                                   +---------------+            |
                                          |                     v
                                          |        +----------------------------+
                                          |        | Qdrant vector DB           |
                                          |        |  /project-A    (dense+sparse)|
                                          |        |  /project-B    (dense+sparse)|
                                          |        |  /global       (policy docs)|
                                          +------->| + payload (chunk_id,page,    |
                                                   |     project, source, ts)   |
                                                   +-------------+--------------+
                                                                 |
                                            +--------------------+
                                            |  bge-reranker-v2-m3|
                                            |  (optional 2nd pass)|
                                            +--------------------+
                                                                 |
                                                                 v
                              +-------------------------------------------+
                              |   [Step 3 — COMPRESS]                       |
                              |   SmolLM2-1.7B (summarise retrieved ctx,    |
                              |   strip boilerplate, format citation span)  |
                              +-------------------------------------------+
                                                                 |
                                                                 v
                              +-------------------------------------------+
                              |   [Step 4 — REASON]                        |
                              |   Claude (Anthropic API)                   |
                              |   - Sonnet/Opus when complexity is high    |
                              |   - Haiku for routine steps                |
                              |   Inherit citations from prior step        |
                              +-------------------------------------------+
                                                                 |
                                                                 v
                              +-------------------------------------------+
                              |   [Step 5 — VERIFY + LOG]                  |
                              |   - NLI faithfulness (DeBERTa-v3-mnli)     |
                              |   - ragas nightly scoring                  |
                              |   - audit sample → Claude-as-judge         |
                              +-------------------------------------------+
```

**Cost-control rules (enforced in the manager agent):**

1. Nothing leaves the routing layer without a `(project_id, sub_agent, claude_tier, estimated_tokens)` log entry.
2. Embedder (bge-large / bge-m3) always runs on local TEI — no per-request external charges.
3. Reranker invocation is conditional: only on `(k≥20 candidates) OR (project has a "rerank_required=true" flag)`.
4. RAG compression to ≤ 3k tokens before any Claude call (avoids runaway context).
5. Claude tier auto-selected by `SmolLM2-1.7B` based on a structured difficulty rubric: `trivial → no Claude (sub-2B handles it)`, `medium → Haiku`, `hard → Sonnet`, `expert → Sonnet w/ extended thinking`.
6. Per-project budget caps enforced by the orchestrator; over-quota jobs fall back to the local Qwen/Granite fallback models.
7. Per-answer faithfulness score is logged; responses flagged below threshold are auto-rerun with the higher Claude tier.

**Multi-project isolation:**
- Each project = a Qdrant collection + an HF Dataset repo for the chunked text + a Hugging Face Storage Bucket for raw files, plus per-project system prompts and tool allow-lists in the manager agent's config.
- Cross-project queries go through a global/policy collection only.

---

## TL;DR — The stack in one line

> **smolagents + Docling (Granite-Docling-258M) for ingestion → TEI on `bge-m3`/`bge-large-en-v1.5` for embeddings, `bge-reranker-v2-m3` for two-stage retrieval → Qdrant for vectors → `SmolLM2-1.7B-Instruct` for routing/compression → Claude for comprehension → ragas + NLI for verification.**
