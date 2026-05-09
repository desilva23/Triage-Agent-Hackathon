"""
examples.py — Dynamic Few-Shot Example Retrieval.

Indexes the sample_support_issues.csv and retrieves similar resolved cases
to provide as 'In-Context Learning' examples for the ReAct agent.
"""

import csv
import os
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from utils import resolve_path

class ExampleRetriever:
    def __init__(self, sample_csv="support_issues/sample_support_issues.csv"):
        self.sample_csv = resolve_path(sample_csv)
        self.examples = []
        self.embeddings = None
        self.vectorizer = TfidfVectorizer(stop_words='english')
        
        self._load_examples()

    def _load_examples(self):
        if not os.path.exists(self.sample_csv):
            print(f"Warning: {self.sample_csv} not found. Dynamic examples disabled.")
            return

        try:
            with open(self.sample_csv, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Clean the example
                    ex = {
                        "issue": row.get("Issue", ""),
                        "response": row.get("response", ""),
                        "status": row.get("status", ""),
                        "area": row.get("product_area", "")
                    }
                    self.examples.append(ex)
            
            if self.examples:
                texts = [e["issue"] for e in self.examples]
                self.embeddings = self.vectorizer.fit_transform(texts)
                print(f"  [EXAMPLES] Indexed {len(self.examples)} gold-standard examples via TF-IDF.")
        except Exception as e:
            print(f"Error loading examples: {e}")

    def get_examples(self, query: str, k: int = 2) -> str:
        if not self.examples or self.embeddings is None:
            return ""
            
        try:
            q_emb = self.vectorizer.transform([query])
            sims = cosine_similarity(q_emb, self.embeddings)[0]
            top_indices = np.argsort(sims)[-k:][::-1]
            
            lines = []
            for i in top_indices:
                ex = self.examples[i]
                lines.append(f"Example Case:\nIssue: {ex['issue']}\nCorrect Status: {ex['status']}\nCorrect Product Area: {ex['area']}\nCorrect Response: {ex['response']}\n")
                
            return "\n".join(lines)
        except:
            return ""
