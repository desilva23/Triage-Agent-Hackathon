import os
import json
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from utils import resolve_path

class SemanticCache:
    def __init__(self, cache_file="data/semantic_cache.json", threshold=0.95, model=None):
        self.cache_file = resolve_path(cache_file)
        self.threshold = threshold
        self.vectorizer = TfidfVectorizer(stop_words='english')
        self.model = None # Lightweight mode
        
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
        """Checks if the query is in the cache (semantically or via keywords)."""
        if not self.queries:
            return None
            
        # Simple keyword overlap for lightweight mode
        query_set = set(query.lower().split())
        best_score = 0
        best_idx = -1
        
        for i, q in enumerate(self.queries):
            cached_set = set(q.lower().split())
            if not cached_set: continue
            overlap = len(query_set.intersection(cached_set)) / len(query_set.union(cached_set))
            if overlap > best_score:
                best_score = overlap
                best_idx = i
        
        from telemetry import telemetry
        if best_score >= self.threshold:
            print(f"  [CACHE HIT] Keyword match ({best_score:.2f}) found for query!")
            telemetry.log_cache_hit(500) 
            return self.responses[best_idx]
            
        print(f"  [CACHE MISS] Best match was {best_score:.2f} (Threshold: {self.threshold})")
        telemetry.log_cache_miss()
        return None

    def set(self, query, response_dict):
        """Adds a query and its response to the cache."""
        self.queries.append(query)
        self.responses.append(response_dict)
        # We don't store embeddings in lightweight mode
        self._save_cache()
