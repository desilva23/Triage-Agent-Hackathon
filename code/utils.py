import os
import re

def clean_text(text):
    """Simple text cleaning."""
    if not text:
        return ""
    # Remove extra whitespaces
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def get_repo_root():
    """Returns the absolute path to the repository root."""
    # Assuming this script is in code/
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def resolve_path(relative_path):
    """Resolves a path relative to the repo root."""
    return os.path.join(get_repo_root(), relative_path)
