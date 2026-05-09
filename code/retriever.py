"""
retriever.py — Hybrid Retriever with Semantic Chunking.

Upgraded from whole-document retrieval to chunk-level retrieval:
- Documents are split into semantic sections (via chunker.py)
- Each chunk is indexed by BM25 and dense embedding separately
- Hybrid scoring (BM25 + cosine) identifies top candidates
- CrossEncoder reranker picks the best 2 chunks to pass to the LLM
- Embeddings are cached to disk so the first run is the only slow run
"""

import os
import time
import json
import numpy as np
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer, CrossEncoder
from sklearn.metrics.pairwise import cosine_similarity
from utils import resolve_path
from chunker import chunk_markdown


class SupportRetriever:
    def __init__(self, data_dir="data", use_hybrid=True):
        self.data_dir = resolve_path(data_dir)
        self.use_hybrid = use_hybrid

        # Chunk-level storage
        self.chunks = []        # list of {"content", "path", "header"}
        self.tokenized_chunks = []  # for BM25
        self.chunk_embeddings = None  # numpy array for semantic search
        self.bm25 = None

        if self.use_hybrid:
            print("Loading embedding model (all-MiniLM-L6-v2)...")
            self.embedder = SentenceTransformer("all-MiniLM-L6-v2")
            print("Loading Cross-Encoder reranker (ms-marco-MiniLM-L-6-v2)...")
            self.reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")

        self._index_corpus()

    # ------------------------------------------------------------------ #
    # Indexing
    # ------------------------------------------------------------------ #

    def _index_corpus(self):
        """Walks data dir, chunks every .md file, builds BM25 + dense index."""
        chunk_cache = os.path.join(self.data_dir, "chunks_meta.json")
        emb_cache = os.path.join(self.data_dir, "chunks_embeddings.npy")

        # Fast path: load from disk cache
        if self.use_hybrid and os.path.exists(chunk_cache) and os.path.exists(emb_cache):
            print("Loading cached chunk index...")
            t0 = time.time()
            with open(chunk_cache, "r", encoding="utf-8") as f:
                self.chunks = json.load(f)
            self.chunk_embeddings = np.load(emb_cache)
            self.tokenized_chunks = [c["content"].lower().split() for c in self.chunks]
            self.bm25 = BM25Okapi(self.tokenized_chunks)
            print(f"Loaded {len(self.chunks)} chunks in {time.time()-t0:.2f}s.")
            return

        # Slow path: build from scratch
        print(f"Indexing corpus from {self.data_dir} (semantic chunking)...")
        t0 = time.time()

        for root, _, files in os.walk(self.data_dir):
            for fname in files:
                if not fname.endswith(".md"):
                    continue
                fpath = os.path.join(root, fname)
                rel_path = os.path.relpath(fpath, self.data_dir)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        content = f.read()
                    for chunk in chunk_markdown(content, rel_path):
                        self.chunks.append(chunk)
                        self.tokenized_chunks.append(chunk["content"].lower().split())
                except Exception as e:
                    print(f"  Error reading {fpath}: {e}")

        if not self.chunks:
            print("WARNING: No chunks indexed.")
            return

        self.bm25 = BM25Okapi(self.tokenized_chunks)

        if self.use_hybrid:
            print(f"Computing dense embeddings for {len(self.chunks)} chunks...")
            texts = [c["content"] for c in self.chunks]
            self.chunk_embeddings = self.embedder.encode(
                texts, show_progress_bar=True, batch_size=64
            )
            # Persist cache
            with open(chunk_cache, "w", encoding="utf-8") as f:
                json.dump(self.chunks, f)
            np.save(emb_cache, self.chunk_embeddings)

        print(f"Indexed {len(self.chunks)} chunks in {time.time()-t0:.2f}s.")

    # ------------------------------------------------------------------ #
    # Search
    # ------------------------------------------------------------------ #

    def search(self, query: str, company: str = None, top_k: int = 2) -> list:
        """
        Hybrid BM25 + Semantic search with Cross-Encoder reranking.

        Returns top_k chunks as dicts: {"content", "path", "score"}
        """
        if not self.bm25:
            return []

        tokenized_q = query.lower().split()
        bm25_scores = self.bm25.get_scores(tokenized_q)

        # Normalise BM25 scores to [0, 1]
        max_bm25 = np.max(bm25_scores)
        if max_bm25 > 0:
            bm25_scores = bm25_scores / max_bm25

        # Dense semantic scores
        sem_scores = np.zeros(len(self.chunks))
        if self.use_hybrid and self.chunk_embeddings is not None:
            q_emb = self.embedder.encode([query])
            sem_scores = cosine_similarity(q_emb, self.chunk_embeddings)[0]

        # Combine: 40% keyword, 60% semantic
        hybrid_scores = 0.4 * bm25_scores + 0.6 * sem_scores

        # Filter by company (path-based)
        candidates = []
        for i, score in enumerate(hybrid_scores):
            chunk = self.chunks[i]
            if company and company.lower() not in ("none", ""):
                if company.lower() not in chunk["path"].lower():
                    continue
            candidates.append((i, score))

        # Sort and take top 10 for reranking
        candidates.sort(key=lambda x: x[1], reverse=True)
        top_candidates = candidates[:10]

        if not top_candidates:
            return []

        if not self.use_hybrid:
            return [
                {"content": self.chunks[i]["content"], "path": self.chunks[i]["path"], "score": s}
                for i, s in top_candidates[:top_k]
            ]

        # Cross-Encoder reranking
        cross_inputs = [[query, self.chunks[i]["content"]] for i, _ in top_candidates]
        cross_scores = self.reranker.predict(cross_inputs)

        reranked = []
        for idx, (orig_i, _) in enumerate(top_candidates):
            reranked.append({
                "content": self.chunks[orig_i]["content"],
                "path": self.chunks[orig_i]["path"],
                "score": float(cross_scores[idx]),
            })

        reranked.sort(key=lambda x: x["score"], reverse=True)
        return reranked[:top_k]
