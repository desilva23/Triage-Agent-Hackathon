"""
index.py — Automated Documentation Indexer CLI.

Use this script to pre-compute semantic chunks and embeddings for the support corpus.
Separating indexing from inference is a best practice for production RAG systems.
"""

import os
import time
import argparse
from retriever import SupportRetriever
from utils import resolve_path

def main():
    parser = argparse.ArgumentParser(description="Index the support corpus.")
    parser.add_argument("--data-dir", default="data", help="Directory containing support docs.")
    parser.add_argument("--force", action="store_true", help="Force re-indexing even if cache exists.")
    args = parser.parse_args()

    data_path = resolve_path(args.data_dir)
    chunk_cache = os.path.join(data_path, "chunks_meta.json")
    emb_cache = os.path.join(data_path, "chunks_embeddings.npy")

    if args.force:
        print("Force re-indexing enabled. Clearing existing cache...")
        if os.path.exists(chunk_cache): os.remove(chunk_cache)
        if os.path.exists(emb_cache): os.remove(emb_cache)

    print("\n" + "="*40)
    print("  DOCUMENTATION INDEXER CLI")
    print("="*40)
    
    t0 = time.time()
    
    # Initializing SupportRetriever triggers indexing if cache is missing
    retriever = SupportRetriever(data_dir=args.data_dir)
    
    duration = time.time() - t0
    print("-" * 40)
    print(f"Index Location:  {data_path}")
    print(f"Total Chunks:    {len(retriever.chunks)}")
    print(f"Total Time:      {duration:.2f}s")
    print("="*40)
    print("\n✓ Indexing complete. The agent will now start instantly.")

if __name__ == "__main__":
    main()
