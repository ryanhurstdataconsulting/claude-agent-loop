---
name: rag-pipeline-scaffolding
description: Use when a task asks to build, tune, or debug a retrieval-augmented-generation (RAG) feature — "answer questions over our docs," "add a knowledge base to the chatbot," "the bot keeps citing the wrong document," or "retrieval quality is bad." Covers chunking-strategy selection, embedding-model choice, vector-database setup (pgvector, Pinecone, Weaviate, Qdrant), reranking, and diagnosing low recall@k or hallucinated citations.
---

# rag-pipeline-scaffolding

## Overview
Scaffolds a retrieval-augmented-generation pipeline end to end — ingestion
and chunking, embedding and indexing, retrieval and reranking, and the
generation step that consumes the retrieved context. Owns the question
"how should this system find and use the right documents," distinct from
prompt wording or model choice for generation itself.

## When to use
- A task asks to add "chat with your docs," semantic search, or a
  knowledge-base Q&A feature to an application.
- An existing RAG feature returns irrelevant chunks, misses an answer that
  is clearly present in the source documents, or cites the wrong document.
- A task asks which vector database, embedding model, or chunking strategy
  fits a given corpus and query pattern.
- Retrieval looks fine in isolation but the generated answer still
  hallucinates or ignores the retrieved context.

## Workflow

1. **Chunking strategy — decide by document structure and query type, not
   by default:**

   | Corpus shape | Recommended chunking | Why |
   |---|---|---|
   | Long-form prose (articles, reports) | Recursive character/token splitting, 300–800 tokens, 10–20% overlap | Preserves local coherence without cutting mid-thought |
   | Structured docs (API references, manuals) | Section/heading-aware splitting (split on markdown headers or XML/HTML tags) | Keeps a self-contained unit (one endpoint, one policy clause) per chunk |
   | Code | Function/class-aware splitting (AST-based, e.g., a language-aware splitter) | Naive fixed-size splitting breaks syntax and destroys retrievability |
   | Tables / structured records | One row or one logical record per chunk, with header context repeated | Fixed-size splitting mid-table produces meaningless fragments |
   | Q&A pairs / FAQ | One pair per chunk | Matches the query shape directly; avoid merging unrelated Q&A pairs |

   Default to 200–500 token chunks with 10–20% overlap when the corpus
   shape is unknown, then tune against retrieval-quality metrics (step 5)
   rather than guessing further.

2. **Embedding-model selection — weigh these factors in order:**
   - **Domain match.** A general-purpose embedding model underperforms on
     narrow technical or legal vocabulary; check for a domain-tuned
     alternative before defaulting to a general model.
   - **Context window.** The embedding model's max input must exceed the
     chosen chunk size with room to spare.
   - **Dimensionality vs. cost.** Higher-dimension embeddings improve
     recall marginally but increase storage and query latency linearly;
     start with a mid-size model (for example, 512–1536 dimensions) unless
     benchmarking shows a real gap.
   - **Latency budget.** A hosted embedding API call adds round-trip time
     to both ingestion and query paths; a self-hosted or smaller model may
     be required for a tight query-latency SLO.
   - **Consistency.** Never mix embeddings from two different models in
     one index — re-embed the whole corpus after any model change.

3. **Vector database setup — pick by existing infrastructure and scale,
   not by novelty:**

   | Store | Reach for it when | Watch out for |
   |---|---|---|
   | `pgvector` (Postgres extension) | The application already runs Postgres and the corpus is small-to-medium (roughly under a few million vectors) | Approximate-nearest-neighbor index tuning (`ivfflat`/`hnsw`) is manual; index build time grows with corpus size |
   | Managed vector DB (e.g., Pinecone) | Rapid setup with no infrastructure to operate is a hard requirement | Recurring per-vector cost; data leaves the primary infrastructure boundary |
   | Self-hosted vector DB (e.g., Weaviate, Qdrant) | Scale or filtering needs exceed what `pgvector` handles well, and self-hosting is acceptable | Operational overhead — backups, upgrades, and capacity planning become the team's responsibility |

   Every choice needs metadata filtering (source, date, access level) —
   confirm the store supports filtered search before committing, not
   after the corpus is loaded.

4. **Add a reranking step whenever the initial retrieval set exceeds what
   the generation prompt should actually receive.** Retrieve a wider
   candidate set (for example, top 20–50 by vector similarity), then apply
   a cross-encoder reranker to select the final top-k (typically 3–8) that
   goes into the prompt. Vector similarity alone frequently surfaces
   topically related but not directly relevant chunks; reranking is the
   highest-leverage single addition for citation accuracy.

5. **Diagnose retrieval quality with recall@k before touching the
   generation prompt.** A hallucinated or wrong answer is a generation
   problem only if retrieval already found the right chunk — check that
   first:
   - Build (or reuse) a small golden set of query → expected-source-chunk
     pairs.
   - Measure recall@k: does the expected chunk appear in the top-k
     retrieved results?
   - Low recall@k → the problem is chunking, embedding, or indexing (steps
     1–3). Revisit chunk size/overlap first — it is the cheapest lever.
   - High recall@k but a wrong or unsupported answer → the problem is
     prompt construction or generation, not retrieval; hand off to prompt
     iteration and regression testing instead of re-tuning the index.

6. **Guard against context-window overflow and citation drift.** Truncate
   or summarize retrieved chunks that would push the prompt past the
   model's effective context window, and instruct the model explicitly to
   answer only from retrieved context and to say when the answer is not
   present — an unconstrained prompt will otherwise fall back to
   parametric knowledge and silently drop the "grounded in these
   documents" guarantee.

## Checklist / quality gate
- [ ] Chunking strategy matches the corpus shape (prose vs. structured vs.
      code vs. tabular), not a single fixed-size default applied
      everywhere.
- [ ] Embedding model's context window comfortably exceeds the chunk size,
      and the whole corpus uses one consistent embedding model.
- [ ] Vector store supports the metadata filtering the application
      actually needs (access control, date range, source type).
- [ ] A reranking step sits between initial retrieval and the generation
      prompt when the candidate set is wider than the final top-k.
- [ ] Recall@k is measured against a golden set before any generation
      prompt changes are made to fix a "wrong answer" complaint.
- [ ] The generation prompt instructs the model to answer only from
      retrieved context and to say explicitly when the answer is absent.

## References
- Retrieval-augmented generation is documented as the dominant enterprise
  pattern for grounding LLM output in a specific corpus, spanning vector
  databases, embedding models, chunking strategy, and reranking as the
  core skill set.
- pgvector: https://github.com/pgvector/pgvector
- Pinecone documentation: https://docs.pinecone.io/
- Weaviate documentation: https://weaviate.io/developers/weaviate
- Qdrant documentation: https://qdrant.tech/documentation/

## Composition
- Hands off to **eval-harness** once the pipeline is scaffolded — that
  skill builds the golden dataset and pass/fail thresholds (faithfulness,
  relevance, safety) that gate future changes to this pipeline.
- Hands off to **prompt-regression-testing** when a wrong answer is
  isolated to the generation step (high recall@k, bad answer) rather than
  retrieval.
- Feeds **llm-cost-latency-optimization** when reranking or a wider
  retrieval candidate set pushes latency or per-request cost past budget.
- Pairs with **agent-tool-use-design** when retrieval is exposed to an
  agent as a callable tool rather than a fixed pipeline step.
