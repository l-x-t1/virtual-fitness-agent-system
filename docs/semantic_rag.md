# Semantic Embedding and RAG Retrieval Upgrade

## Embedding Model

The project now uses `SemanticEmbeddings`, a LangChain `Embeddings` adapter.

- Default model: `BAAI/bge-small-zh-v1.5`
- Loader: `sentence-transformers`
- Protocol: `embed_documents(texts)` and `embed_query(text)`
- Test/offline fallback: concept-based semantic fallback, not `HashingEmbeddings`

Recommended `.env` values:

```env
EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
EMBEDDING_DEVICE=cpu
EMBEDDING_BATCH_SIZE=32
EMBEDDING_ALLOW_FALLBACK=true
EMBEDDING_ALLOW_DOWNLOAD=false
CHROMA_PERSIST_DIRECTORY=data/chroma
```

Set `EMBEDDING_ALLOW_DOWNLOAD=true` only when the environment is allowed to
download the model at runtime. Otherwise the adapter loads local cached model
files first and uses the offline semantic fallback if they are unavailable.

## Vector Store

FAISS has been replaced by Chroma through `ChromaVectorStore`.

Capabilities used by the project:

- Persistent index directory
- Upsert/add/delete/get/query operations
- Metadata filtering, including `user_id`, `source`, and `category`
- Thread-safe access around collection operations

## Integration Points

- Exercise recommendation: `app/agents/embedding_store.py`
- AI knowledge base vector search: `app/ai/knowledge_base.py`
- Hybrid RAG vector adapter: `app/ai/rag/vector_retriever.py`
- Cross-session memory recall: `app/ai/memory.py`

SQLite remains the durable fact store for AI conversation memory. Long-term
memory and summaries are also synchronized into Chroma for semantic recall.

## Evaluation

`tools/evaluate_semantic_recall.py` compares the old hashing algorithm with the
new semantic embedding retrieval over 25 fitness scenarios:

```bash
python tools/evaluate_semantic_recall.py --top-k 3
python tools/evaluate_semantic_recall.py --top-k 3 --json
```

The test cases live in:

```text
tests/fixtures/fitness_semantic_recall_cases.json
```
