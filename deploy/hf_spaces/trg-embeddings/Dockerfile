# TRG Embeddings — single TEI process
#
# Hugging Face Text Embeddings Inference with bge-small-en-v1.5
# (English, 384-dim). Fast on CPU, top MTEB-retrieval at this size.

FROM ghcr.io/huggingface/text-embeddings-inference:1.6

CMD ["--model-id", "BAAI/bge-small-en-v1.5", \
     "--revision", "main", \
     "--pooling", "cls", \
     "--normalize", \
     "--max-client-batch-size", "32", \
     "--max-batch-tokens", "16384"]
