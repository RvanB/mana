"""Embedding model management."""
from __future__ import annotations

from typing import Optional
from sentence_transformers import SentenceTransformer

from ..config import EMBEDDING_MODEL_NAME

# Global embedding model (lazy loaded)
_EMBEDDING_MODEL: Optional[SentenceTransformer] = None


def get_embedding_model() -> SentenceTransformer:
    """Lazy load embedding model."""
    global _EMBEDDING_MODEL
    if _EMBEDDING_MODEL is None:
        # all-MiniLM-L6-v2: fast, small (80MB), good quality
        _EMBEDDING_MODEL = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return _EMBEDDING_MODEL
