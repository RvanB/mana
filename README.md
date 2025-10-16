# mai - CLI Command Generator with RAG

Generate shell commands from natural language using RAG (Retrieval Augmented Generation) on your local man pages. Mai prevents LLM hallucination by only allowing commands built from actual documentation on your system.

## Features

- = **FAISS-powered vector search** - Fast semantic search across all man pages
- =� **Zero hallucination** - LLM can only use documented flags and options
- <� **Color-coded explanations** - Visual breakdown of command parts
- =� **Model-agnostic** - Works with any LLM (OpenAI, Ollama, Copilot, etc.)
- =� **Persistent index** - One-time indexing, fast subsequent queries
- =' **Auto-discovery** - Automatically finds all executables with man pages

## Installation

```bash
# Install dependencies
uv sync
```

## Quick Start

### 1. Build the Vector Database

First time only - indexes all man pages on your PATH (~5-10 minutes):

```bash
uv run mai.py --index
```

Example output:
```
Discovering executables with man pages...
Found 342 executables with man pages

Indexing man pages:
------------------------------------------------------------
[   1/342] ls                              47 chunks
[   2/342] grep                            89 chunks
[   3/342] find                            156 chunks
...
------------------------------------------------------------

Embedding 8,234 chunks...
 Indexed 342 programs, 8,234 total chunks
```

### 2. Generate Commands

```bash
# Basic usage
uv run mai.py "find all jpg files recursively"

# With color-coded explanation
uv run mai.py "find all jpg files recursively" --explain

# Adjust number of relevant chunks
uv run mai.py "your task" --top-k 20
```

### 3. View Indexed Programs

```bash
uv run mai.py --list
```

## Configuration

### Use with Different LLM Providers

**OpenAI** (default):
```bash
export OPENAI_API_KEY=your_key
uv run mai.py "your task"
```

**GitHub Copilot**:
```bash
export COPILOT_TOKEN=your_token
uv run mai.py --provider copilot "your task"
```

**Ollama** (local):
```bash
# Start Ollama server first: ollama serve
uv run mai.py --provider openai --api-base http://localhost:11434/v1 --model llama3 "your task"
```

**Any OpenAI-compatible API**:
```bash
uv run mai.py --provider openai --api-base http://your-api:port --model your-model "your task"
```

## How It Works

1. **Indexing Phase** (`--index`):
   - Discovers all executables in PATH with man pages
   - Chunks each man page by: synopsis, individual options, description paragraphs
   - Generates embeddings using sentence-transformers (all-MiniLM-L6-v2)
   - Stores in FAISS vector database at `~/.mai/`

2. **Query Phase**:
   - Embeds your task query
   - FAISS finds top-K most relevant chunks via cosine similarity
   - Sends ONLY those chunks to LLM with strict prompt
   - LLM generates command using ONLY documented options
   - Optional: explains command with color-coded breakdown

## Files

- `~/.mai/vectors.faiss` - FAISS vector index
- `~/.mai/chunks.pkl` - Pickled man page chunks
- `~/.mai/metadata.json` - Index metadata (programs, timestamp, etc.)

## Command Reference

```bash
# First time: Full index
uv run mai.py --index

# Update: Add new programs only (incremental)
uv run mai.py --index

# Force full rebuild from scratch
uv run mai.py --force-reindex

# Use more workers for faster indexing
uv run mai.py --index --workers 16

# List indexed programs
uv run mai.py --list

# Generate command
uv run mai.py "your task here"

# With explanation
uv run mai.py "your task" --explain

# Adjust retrieval
uv run mai.py "your task" --top-k 20

# Use different model
uv run mai.py --model gpt-4o "your task"
```

## Why RAG?

Traditional LLM command generation often hallucinates flags:
- `grep --recursive` (wrong, should be `-r` or `-R`)
- `find -regex` (exists but `-regextype` is platform-specific)
- Made-up flags that don't exist

Mai solves this by:
1. Only passing actual man page content to the LLM
2. Instructing the LLM to use ONLY documented options
3. Semantic search ensures relevant options are included

## Troubleshooting

**"Vector database not found"**:
Run `uv run mai.py --index` first.

**Slow indexing**:
Normal for first run. Indexes ~30-50 programs/minute. Subsequent queries are instant.

**Model token limits**:
Use `--top-k` to reduce chunks sent (default: 15). FAISS makes this efficient.

## License

MIT
