"""Vector database operations using FAISS."""
from __future__ import annotations

import json
import os
import pickle
import sys
from typing import List, Dict, Optional, Tuple, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import faiss

from ..config import (
    FAISS_INDEX_FILE,
    CHUNKS_FILE,
    METADATA_FILE,
    MAX_TEXT_LENGTH,
    DEFAULT_WORKERS,
)
from ..manpage import process_program, get_all_executables, extract_name_section, discover_man_pages
from .embeddings import get_embedding_model


def load_vector_database() -> Optional[Tuple[faiss.Index, List[Dict[str, str]]]]:
    """Load the FAISS index and chunks from disk."""
    if not FAISS_INDEX_FILE.exists() or not CHUNKS_FILE.exists():
        return None

    try:
        # Load FAISS index
        index = faiss.read_index(str(FAISS_INDEX_FILE))

        # Load chunks
        with open(CHUNKS_FILE, 'rb') as f:
            chunks = pickle.load(f)

        return index, chunks
    except Exception as e:
        print(f"Error loading database: {e}")
        return None


def get_indexed_programs() -> List[str]:
    """Get list of already indexed programs from metadata."""
    if not METADATA_FILE.exists():
        return []

    try:
        with open(METADATA_FILE) as f:
            metadata = json.load(f)
            return metadata.get("programs", [])
    except Exception:
        return []


def save_vector_database(
    chunks: List[Dict[str, str]],
    embeddings: np.ndarray,
    programs: List[str]
):
    """Save the FAISS index and chunks to disk."""
    # Create FAISS index (L2 distance, normalized for cosine similarity)
    dimension = embeddings.shape[1]
    index = faiss.IndexFlatL2(dimension)

    # Normalize vectors for cosine similarity
    faiss.normalize_L2(embeddings)
    index.add(embeddings)

    # Save FAISS index
    faiss.write_index(index, str(FAISS_INDEX_FILE))

    # Save chunks as pickle (more efficient than JSON)
    with open(CHUNKS_FILE, 'wb') as f:
        pickle.dump(chunks, f)

    # Save metadata with program list
    metadata = {
        "num_chunks": len(chunks),
        "num_programs": len(programs),
        "dimension": dimension,
        "indexed_at": os.popen('date').read().strip(),
        "programs": sorted(programs)
    }
    with open(METADATA_FILE, 'w') as f:
        json.dump(metadata, f, indent=2)

    print(f"✓ Saved {len(chunks)} chunks to FAISS index at {FAISS_INDEX_FILE}")


def build_vector_database(
    programs: Optional[List[str]] = None,
    verbose: bool = True,
    max_workers: int = DEFAULT_WORKERS,
    force: bool = False,
    progress_callback: Optional[Callable[[str, int, int, str], None]] = None
):
    """Build or rebuild the vector database for all programs using parallel processing.

    Args:
        programs: Optional list of programs to index. If None, discovers from PATH.
        verbose: Show progress information.
        max_workers: Number of parallel workers.
        force: Force full reindex, ignoring existing data.
        progress_callback: Optional callback function(stage, current, total, message) for progress updates.
    """
    if programs is None:
        programs = get_all_executables()
        if progress_callback:
            progress_callback("discovery", len(programs), len(programs), f"Found {len(programs)} executables")
        elif verbose:
            print(f"Found {len(programs)} unique executables")

    # Check for existing index and do incremental update if not forcing
    existing_programs = []
    existing_chunks = []
    existing_embeddings = None
    if not force:
        existing_programs = get_indexed_programs()
        if existing_programs:
            # Load existing chunks and index
            db = load_vector_database()
            if db:
                existing_index, existing_chunks = db
                # Extract embeddings from FAISS index
                # IndexFlatL2 stores vectors directly, so we can reconstruct them
                try:
                    existing_embeddings = np.zeros((existing_index.ntotal, existing_index.d), dtype=np.float32)
                    for i in range(existing_index.ntotal):
                        existing_embeddings[i] = existing_index.reconstruct(i)
                except Exception as e:
                    # If reconstruction fails, we'll re-embed everything
                    existing_embeddings = None
                    if verbose:
                        print(f"Warning: Could not extract existing embeddings: {e}")

            # Compute diff
            programs_set = set(programs)
            existing_set = set(existing_programs)
            new_programs = sorted(programs_set - existing_set)
            removed_programs = sorted(existing_set - programs_set)

            if not progress_callback and verbose:
                print(f"  Already indexed: {len(existing_programs)} programs")
                if removed_programs:
                    print(f"  Removed from PATH: {len(removed_programs)} programs")
                if new_programs:
                    print(f"  New to index: {len(new_programs)} programs")
                else:
                    print(f"  No new programs to index!")
                    if not removed_programs:
                        return
            elif not new_programs and not removed_programs:
                # No new programs and nothing removed - database is up to date
                if progress_callback:
                    progress_callback("complete", len(existing_programs), len(existing_programs), "Database is up to date")
                return

            # Only process new programs
            programs = new_programs

            # Filter out chunks from removed programs and their embeddings
            if removed_programs:
                removed_set = set(removed_programs)
                # Build mapping to keep track of indices
                filtered_chunks = []
                filtered_embeddings = []
                for i, chunk in enumerate(existing_chunks):
                    if chunk.get('program') not in removed_set:
                        filtered_chunks.append(chunk)
                        if existing_embeddings is not None:
                            filtered_embeddings.append(existing_embeddings[i])
                
                existing_chunks = filtered_chunks
                if filtered_embeddings:
                    existing_embeddings = np.array(filtered_embeddings)
                else:
                    existing_embeddings = None
                existing_programs = [p for p in existing_programs if p not in removed_set]
                
                # If we only removed programs (no new ones), save the updated database
                if not programs and existing_embeddings is not None:
                    if progress_callback:
                        progress_callback("saving", 0, 1, f"Removing {len(removed_programs)} programs from database...")
                    save_vector_database(existing_chunks, existing_embeddings, existing_programs)
                    if progress_callback:
                        progress_callback("complete", len(existing_programs), len(existing_programs), f"Removed {len(removed_programs)} programs")
                    elif verbose:
                        print(f"✓ Removed {len(removed_programs)} programs from database")
                    return

    if not programs:
        if not progress_callback:
            print("\nNothing to index!")
        return

    new_man_pages = {}  # program -> man_page_text
    new_programs = []
    # Discover all man pages once (much faster than checking per program)
    if verbose and not progress_callback:
        print(f"\nDiscovering man page files...")
    man_pages_cache = discover_man_pages()
    if verbose and not progress_callback:
        print(f"  Found {len(man_pages_cache)} man pages")

    # Process programs in parallel - just read man pages
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks with the cache
        future_to_program = {executor.submit(process_program, prog, man_pages_cache): prog for prog in programs}

        # Process results as they complete
        if verbose and not progress_callback:
            print(f"\nDiscovering programs with man pages (workers={max_workers})...")

        completed = 0
        for future in as_completed(future_to_program):
            result = future.result()
            if result:
                program, man_page = result
                new_man_pages[program] = man_page
                new_programs.append(program)
            completed += 1

            if progress_callback:
                progress_callback("scanning", completed, len(programs), f"Found {len(new_programs)} with man pages")
            elif verbose:
                sys.stdout.write(f'\r  [{completed}/{len(programs)}] Discovered {len(new_programs)} programs with man pages...')
                sys.stdout.flush()

        if verbose and not progress_callback:
            sys.stdout.write(f'\r  [{len(programs)}/{len(programs)}] Done!{" " * 50}\n')
            sys.stdout.flush()

    if not new_man_pages and not existing_chunks:
        if not progress_callback:
            print("\nNo programs to index!")
        return

    # Extract NAME sections for display, but use full man page for embedding
    new_chunks = []
    if new_man_pages:
        if verbose and not progress_callback:
            print(f"\nProcessing {len(new_man_pages)} programs...")

        for idx, (program, man_page) in enumerate(new_man_pages.items(), 1):
            # Extract NAME section for display
            name_description = extract_name_section(program, man_page)

            # Calculate man page stats
            line_count = len(man_page.split('\n'))
            word_count = len(man_page.split())
            char_count = len(man_page)

            # Create single chunk per program
            new_chunks.append({
                "program": program,
                "text": man_page,  # Keep full man page for embedding
                "semantic_summary": name_description,  # But display the NAME section
                "line_count": line_count,
                "word_count": word_count,
                "char_count": char_count,
            })

            if progress_callback:
                progress_callback("extracting", idx, len(new_man_pages), f"Processing man pages")

        if verbose and not progress_callback:
            print(f"  Done!")

    # Embed only NEW man pages, not existing ones
    if new_chunks:
        # Truncate to reasonable length to avoid token limits (most models have ~512 token limit)
        texts_to_embed = [c["text"][:MAX_TEXT_LENGTH] for c in new_chunks]
        if verbose and not progress_callback:
            print(f"\nEmbedding {len(new_chunks)} new man pages...")
        # Lazy load embedding model only when needed
        embedding_model = get_embedding_model()
        # For progress tracking: encode in batches to update progress
        if progress_callback:
            batch_size = 32  # Process in batches for progress updates
            embeddings_list = []
            for i in range(0, len(texts_to_embed), batch_size):
                batch = texts_to_embed[i:i + batch_size]
                batch_embeddings = embedding_model.encode(batch, convert_to_numpy=True, show_progress_bar=False)
                embeddings_list.append(batch_embeddings)
                progress_callback("embedding", min(i + batch_size, len(texts_to_embed)), len(new_chunks), f"Embedding {min(i + batch_size, len(texts_to_embed))}/{len(new_chunks)} new man pages")
            new_embeddings = np.vstack(embeddings_list)
        else:
            new_embeddings = embedding_model.encode(texts_to_embed, convert_to_numpy=True, show_progress_bar=False)
        if verbose and not progress_callback:
            print(f"  Done!")
    else:
        new_embeddings = np.array([]).reshape(0, existing_embeddings.shape[1] if existing_embeddings is not None else 384)

    # Merge chunks and embeddings
    all_chunks = existing_chunks + new_chunks
    all_programs = sorted(set(existing_programs + new_programs))
    
    # Concatenate embeddings
    if existing_embeddings is not None and len(existing_embeddings) > 0:
        if len(new_embeddings) > 0:
            all_embeddings = np.vstack([existing_embeddings, new_embeddings])
        else:
            all_embeddings = existing_embeddings
    else:
        all_embeddings = new_embeddings

    if verbose and not progress_callback:
        if new_programs:
            print(f"\n✓ Generated summaries for {len(new_programs)} new programs")
        print(f"  Total programs: {len(all_programs)}")
        print(f"  Total chunks: {len(all_chunks)}")

    if progress_callback:
        progress_callback("saving", 0, 1, "Saving to disk...")
    save_vector_database(all_chunks, all_embeddings, all_programs)
    if progress_callback:
        progress_callback("complete", len(all_programs), len(all_programs), f"Indexed {len(all_programs)} programs")
    elif verbose:
        if new_programs:
            print(f"✓ Added {len(new_programs)} programs")
        print(f"✓ Total: {len(all_programs)} programs indexed")


def search_vector_database(query: str, top_k: int = 200) -> List[Dict[str, str]]:
    """Search using FAISS semantic similarity.

    Args:
        query: Search query string
        top_k: Number of top results to return

    Returns:
        List of matching programs with similarity scores
    """
    result = load_vector_database()

    if not result:
        print("Vector database not found. Run with --index to build it.")
        return []

    index, chunks = result

    # Semantic search with FAISS
    # Lazy load embedding model only when searching
    model = get_embedding_model()
    query_embedding = model.encode(query, convert_to_numpy=True)
    query_embedding = query_embedding.reshape(1, -1)
    faiss.normalize_L2(query_embedding)

    # Limit top_k to actual number of chunks available
    actual_top_k = min(top_k, len(chunks))

    # Search for top-k matches (fast!)
    distances, indices = index.search(query_embedding, actual_top_k)

    # Return chunks with similarity scores
    result_chunks = []
    for idx, dist in zip(indices[0], distances[0]):
        if idx < len(chunks):
            chunk = chunks[idx].copy()
            # Convert L2 distance to similarity score (0-1)
            chunk['similarity'] = 1 - (dist / 2)
            result_chunks.append(chunk)

    return result_chunks
