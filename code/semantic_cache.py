import os
import json
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from utils import resolve_path

class SemanticCache:
    def __init__(self, cache_file="data/semantic_cache.json", threshold=0.95, model=None):
        self.cache_file = resolve_path(cache_file)
        self.threshold = threshold
        
        if model:
            self.model = model
        else:
            print(f"Loading embedding model for cache: all-MiniLM-L6-v2...")
            self.model = SentenceTransformer("all-MiniLM-L6-v2")
        
        self.queries = []
        self.embeddings = []
        self.responses = []
        
        self._load_cache()

    def _load_cache(self):
        """Loads the cache from disk if it exists."""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.queries = data.get("queries", [])
                    self.embeddings = [np.array(e) for e in data.get("embeddings", [])]
                    self.responses = data.get("responses", [])
                print(f"Loaded {len(self.queries)} items from semantic cache.")
            except Exception as e:
                print(f"Failed to load cache: {e}")

    def _save_cache(self):
        """Saves the cache to disk."""
        os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
        try:
            data = {
                "queries": self.queries,
                "embeddings": [e.tolist() for e in self.embeddings],
                "responses": self.responses
            }
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f)
        except Exception as e:
            print(f"Failed to save cache: {e}")

    def get(self, query):
        """Checks if the query is in the cache (semantically)."""
        if not self.embeddings:
            return None
            
        query_emb = self.model.encode([query])[0]
        
        # Calculate cosine similarity against all cached embeddings
        # Reshape to 2D array for sklearn
        cached_embs_array = np.array(self.embeddings)
        similarities = cosine_similarity([query_emb], cached_embs_array)[0]
        
        max_sim_idx = np.argmax(similarities)
        max_sim = similarities[max_sim_idx]
        
        from telemetry import telemetry
        if max_sim >= self.threshold:
            print(f"  [CACHE HIT] Semantic match ({max_sim:.2f}) found for query!")
            telemetry.log_cache_hit(500) # Estimate 500 tokens saved
            return self.responses[max_sim_idx]
            
        print(f"  [CACHE MISS] Best match was {max_sim:.2f} (Threshold: {self.threshold})")
        telemetry.log_cache_miss()
        return None

    def set(self, query, response_dict):
        """Adds a query and its response to the cache."""
        query_emb = self.model.encode([query])[0]
        self.queries.append(query)
        self.embeddings.append(query_emb)
        self.responses.append(response_dict)
        self._save_cache()
