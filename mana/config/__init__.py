"""Configuration and constants for mana."""
from __future__ import annotations

import os
from pathlib import Path

# Set environment variables before importing torch-based libraries
os.environ.setdefault('TOKENIZERS_PARALLELISM', 'false')
os.environ.setdefault('OMP_NUM_THREADS', '1')
os.environ.setdefault('MKL_NUM_THREADS', '1')

# Paths
MANA_DIR = Path.home() / ".mana"
MANA_DIR.mkdir(parents=True, exist_ok=True)

FAISS_INDEX_FILE = MANA_DIR / "vectors.faiss"
CHUNKS_FILE = MANA_DIR / "chunks.pkl"
METADATA_FILE = MANA_DIR / "metadata.json"

# Embedding model configuration
EMBEDDING_MODEL_NAME = 'all-MiniLM-L6-v2'
MAX_TEXT_LENGTH = 8000  # ~2000 tokens worth of text

# Indexing defaults
DEFAULT_WORKERS = 8
DEFAULT_TOP_K = 200

# Man page sections to index
# 1: User commands, 8: System admin commands
DEFAULT_SECTIONS = ['man1', 'man8']
