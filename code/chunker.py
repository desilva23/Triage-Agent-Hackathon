"""
chunker.py — Semantic Markdown document chunker.

Instead of truncating entire documents at an arbitrary character count,
this module splits each markdown file into logical sections based on
headers (##, ###). Each chunk is a meaningful, self-contained unit of
information that can be retrieved and passed to the LLM in full.

This solves the core accuracy problem: the LLM now sees complete,
coherent paragraphs instead of garbled half-sentences.
"""

import re
from typing import List, Dict


def chunk_markdown(content: str, file_path: str, max_chunk_chars: int = 2000) -> List[Dict]:
    """
    Splits a markdown document into semantic chunks based on headers.

    Args:
        content: The full markdown text.
        file_path: The source file path (for metadata).
        max_chunk_chars: Maximum characters per chunk before further splitting.

    Returns:
        A list of chunk dicts: {"content": str, "path": str, "header": str}
    """
    if not content.strip():
        return []

    # Split on H2 and H3 headers (## and ###)
    # Keep the header with the chunk that follows it
    pattern = r'(^#{1,3} .+$)'
    parts = re.split(pattern, content, flags=re.MULTILINE)

    chunks = []
    current_header = ""
    current_body = ""

    for part in parts:
        if re.match(r'^#{1,3} ', part):
            # Save previous chunk if it has content
            if current_body.strip():
                chunk_text = (f"{current_header}\n{current_body}").strip() if current_header else current_body.strip()
                _add_chunks(chunks, chunk_text, file_path, current_header, max_chunk_chars)
            current_header = part.strip()
            current_body = ""
        else:
            current_body += part

    # Don't forget the last chunk
    if current_body.strip():
        chunk_text = (f"{current_header}\n{current_body}").strip() if current_header else current_body.strip()
        _add_chunks(chunks, chunk_text, file_path, current_header, max_chunk_chars)

    # If no headers were found, treat the whole document as one chunk
    if not chunks and content.strip():
        _add_chunks(chunks, content.strip(), file_path, "", max_chunk_chars)

    return chunks


def _add_chunks(chunks: list, text: str, path: str, header: str, max_chars: int):
    """Adds a chunk, splitting further if it exceeds max_chars."""
    if len(text) <= max_chars:
        chunks.append({"content": text, "path": path, "header": header})
    else:
        # Split oversized chunks by paragraph
        paragraphs = text.split("\n\n")
        current = ""
        for para in paragraphs:
            if len(current) + len(para) + 2 > max_chars and current:
                chunks.append({"content": current.strip(), "path": path, "header": header})
                current = para
            else:
                current += "\n\n" + para
        if current.strip():
            chunks.append({"content": current.strip(), "path": path, "header": header})
