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
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from utils import resolve_path
from chunker import chunk_markdown


class SupportRetriever:
    def __init__(self, data_dir="data", use_hybrid=True, model=None):
        self.data_dir = resolve_path(data_dir)
        self.use_hybrid = use_hybrid

        # Chunk-level storage
        self.chunks = []        # list of {"content", "path", "header"}
        self.tokenized_chunks = []  # for BM25
        self.chunk_embeddings = None  # numpy array for semantic search (now TF-IDF)
        self.bm25 = None
        self.vectorizer = TfidfVectorizer(stop_words='english')

        if self.use_hybrid:
            print("Initialising Lightweight Semantic Search (TF-IDF)...")
            self.embedder = None # No SentenceTransformer in lightweight mode
            self.reranker = None 

        self._index_corpus()

    # ------------------------------------------------------------------ #
    # Indexing
    # ------------------------------------------------------------------ #

    def _index_corpus(self):
        """Walks data dir, chunks every .md file, builds BM25 + TF-IDF index."""
        print(f"Indexing corpus (Lightweight Mode) from {self.data_dir}...")
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
            print(f"Fitting TF-IDF on {len(self.chunks)} chunks...")
            texts = [c["content"] for c in self.chunks]
            self.chunk_embeddings = self.vectorizer.fit_transform(texts)

        print(f"Indexed {len(self.chunks)} chunks in {time.time()-t0:.2f}s.")

    # ------------------------------------------------------------------ #
    # Search
    # ------------------------------------------------------------------ #

    def search(self, query: str, company: str = None, top_k: int = 2) -> list:
        """
        Hybrid search using BM25 + TF-IDF Cosine Similarity.
        """
        if not self.bm25:
            return []

        tokenized_q = query.lower().split()
        bm25_scores = self.bm25.get_scores(tokenized_q)

        # Normalise BM25 scores to [0, 1]
        max_bm25 = np.max(bm25_scores)
        if max_bm25 > 0:
            bm25_scores = bm25_scores / max_bm25

        # Dense semantic scores (TF-IDF)
        sem_scores = np.zeros(len(self.chunks))
        if self.use_hybrid and self.chunk_embeddings is not None:
            q_emb = self.vectorizer.transform([query])
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

        # Sort and take top k
        candidates.sort(key=lambda x: x[1], reverse=True)
        top_candidates = candidates[:10]

        if not top_candidates:
            return []

        return [
            {"content": self.chunks[i]["content"], "path": self.chunks[i]["path"], "score": float(s)}
            for i, s in top_candidates[:top_k]
        ]
