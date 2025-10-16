"""Command-line interface for mana."""
from __future__ import annotations

import argparse
from typing import List, Dict

from .rag import search_vector_database, build_vector_database, load_vector_database
from .ui import run_tui
from .config import DEFAULT_TOP_K, DEFAULT_WORKERS, FAISS_INDEX_FILE, CHUNKS_FILE
from .favorites import FavoritesManager
from .init_manager import InitializationManager


def print_results(results, n: int):
    """Print search results to stdout (non-TUI mode)."""
    if not results:
        print("No results found.")
        return

    # Print top n results
    for i, result in enumerate(results[:n], 1):
        program = result.get('program', 'unknown')
        description = result.get('semantic_summary', 'No description')
        similarity = result.get('similarity', 0)
        print(f"{i:2d}. {program:<20} {description}")


def ensure_index_exists(force_reindex: bool, max_workers: int, verbose: bool = True):
    """Ensure the database index exists, building if necessary.

    Returns True if index was built/rebuilt, False if it already existed.
    """
    needs_build = force_reindex or not FAISS_INDEX_FILE.exists() or not CHUNKS_FILE.exists()

    if needs_build:
        if verbose:
            print("Building index...")
        build_vector_database(verbose=verbose, max_workers=max_workers, force=force_reindex)
        if verbose:
            print("✓ Index built successfully!")
        return True

    return False


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Semantic search for command-line programs using FAISS.",
        epilog="Example: mana 'rotate an image'"
    )
    parser.add_argument("query", nargs='?', help="Search query (e.g., 'rotate an image')")
    parser.add_argument("--force-reindex", action="store_true", help="Force full reindex from scratch")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help=f"Number of parallel workers for indexing (default: {DEFAULT_WORKERS})")
    parser.add_argument("-n", type=int, default=DEFAULT_TOP_K, help=f"Number of results to return (default: {DEFAULT_TOP_K})")
    parser.add_argument("--no-tui", action="store_true", help="Print results to stdout instead of launching TUI")

    args = parser.parse_args()

    # Non-TUI mode
    if args.no_tui:
        # Build index if needed (or forced)
        ensure_index_exists(args.force_reindex, args.workers, verbose=True)

        # Search if query provided
        if args.query:
            results = search_vector_database(args.query, top_k=args.n)
            print_results(results, args.n)
        elif not args.force_reindex:
            # No query and no reindex requested
            print("Error: Query required when using --no-tui")
            print("Usage: mana [query] --no-tui")
        return

    # TUI mode
    # Initialize favorites manager
    favorites = FavoritesManager()

    # Create callbacks that the TUI can call (decouples view from model)
    def search_callback(query: str, top_k: int) -> List[Dict[str, str]]:
        """Search callback for TUI."""
        return search_vector_database(query, top_k=top_k)

    def is_favorite_callback(program: str) -> bool:
        """Check if program is favorited."""
        return favorites.is_favorite(program)

    def toggle_favorite_callback(program: str) -> None:
        """Toggle favorite status."""
        favorites.toggle(program)

    def get_favorites_callback() -> List[Dict[str, str]]:
        """Get all favorites as search results."""
        # Load the database to get full program info
        db_result = load_vector_database()
        if not db_result:
            return []

        _, chunks = db_result
        fav_programs = favorites.get_all()

        # Filter chunks to only favorites
        fav_results = []
        for chunk in chunks:
            if chunk.get('program') in fav_programs:
                fav_results.append(chunk)

        return fav_results

    # Check if index needs full rebuild (doesn't exist or forced)
    needs_full_rebuild = args.force_reindex or not FAISS_INDEX_FILE.exists() or not CHUNKS_FILE.exists()
    
    # In TUI mode, we always check for updates (incremental or full rebuild)
    # For queries with existing index, we can search first then update in background
    if args.query and not needs_full_rebuild:
        # Query provided and index exists - search first, then launch TUI with background update
        results = search_callback(args.query, args.n)
        init_manager = InitializationManager()
        
        # Define initialization function for incremental update
        def init_fn(progress_callback):
            """Update database in background."""
            build_vector_database(
                verbose=False,
                max_workers=args.workers,
                force=False,  # Incremental update
                progress_callback=progress_callback
            )
        
        # Always start background update check
        init_manager.start_initialization(init_fn)
        
        run_tui(
            initial_query=args.query,
            initial_results=results,
            top_k=args.n,
            search_fn=search_callback,
            is_favorite_fn=is_favorite_callback,
            toggle_favorite_fn=toggle_favorite_callback,
            get_favorites_fn=get_favorites_callback,
            init_manager=init_manager
        )
    else:
        # Either no query, or index needs full rebuild - launch TUI immediately with initialization
        init_manager = InitializationManager()
        
        # Define initialization function
        def init_fn(progress_callback):
            """Initialize/update database in background."""
            build_vector_database(
                verbose=False,
                max_workers=args.workers,
                force=args.force_reindex,
                progress_callback=progress_callback
            )
        
        # Start initialization/update in background
        init_manager.start_initialization(init_fn)
        
        # Launch TUI with initial query/results if provided
        initial_results = []
        if args.query and not needs_full_rebuild:
            initial_results = search_callback(args.query, args.n)
        
        run_tui(
            initial_query=args.query or "",
            initial_results=initial_results,
            top_k=args.n,
            search_fn=search_callback,
            is_favorite_fn=is_favorite_callback,
            toggle_favorite_fn=toggle_favorite_callback,
            get_favorites_fn=get_favorites_callback,
            init_manager=init_manager
        )
