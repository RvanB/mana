"""Program discovery and man page fetching."""
from __future__ import annotations

import gzip
import os
import subprocess
from typing import List, Optional, Tuple, Dict
from pathlib import Path


def get_man_directories() -> List[Path]:
    """Get list of man page directories from manpath."""
    try:
        result = subprocess.run(
            ['manpath'],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=2
        )
        paths = result.stdout.strip().split(':')
        return [Path(p) for p in paths if Path(p).exists()]
    except Exception:
        # Fallback to common directories
        common_paths = [
            Path('/usr/share/man'),
            Path('/usr/local/share/man'),
            Path('/opt/homebrew/share/man'),
        ]
        return [p for p in common_paths if p.exists()]


def read_man_file(file_path: Path) -> Optional[str]:
    """Read and format a man page file, handling compression."""
    try:
        # Use `man` to format the page (it handles decompression and formatting)
        # Extract section from filename (e.g., grep.1 -> section 1)
        name_parts = file_path.name.replace('.gz', '').rsplit('.', 1)
        if len(name_parts) == 2:
            program_name, section = name_parts
        else:
            program_name = name_parts[0]
            section = None

        # Use man -l to format a local file
        result = subprocess.run(
            ['man', '-l', str(file_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
            env={'MANWIDTH': '10000'}  # Wide width to avoid wrapping
        )

        if result.returncode == 0 and result.stdout:
            return result.stdout

        # Fallback: read raw content if man fails
        if file_path.suffix == '.gz':
            with gzip.open(file_path, 'rt', encoding='utf-8', errors='ignore') as f:
                return f.read()
        else:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
    except Exception:
        return None


def discover_man_pages(sections: List[str] = None) -> Dict[str, Path]:
    """Discover all available man pages by scanning man directories.

    Args:
        sections: List of man sections to include (e.g., ['man1', 'man8']).
                  If None, uses default from config.

    Returns:
        Dictionary mapping program name to man page file path
    """
    if sections is None:
        from ..config import DEFAULT_SECTIONS
        sections = DEFAULT_SECTIONS

    man_dirs = get_man_directories()
    man_pages = {}

    for man_dir in man_dirs:
        # Check specified sections
        for section in sections:
            section_dir = man_dir / section
            if not section_dir.exists():
                continue

            try:
                for man_file in section_dir.iterdir():
                    if not man_file.is_file():
                        continue

                    # Extract program name (remove .1.gz, .1, etc.)
                    name = man_file.name

                    # Remove compression extension
                    if name.endswith('.gz'):
                        name = name[:-3]

                    # Remove section number (e.g., .1, .8)
                    if '.' in name:
                        name = name.rsplit('.', 1)[0]

                    # Skip if we already have this program (prefer earlier paths)
                    if name not in man_pages:
                        man_pages[name] = man_file

            except (PermissionError, OSError):
                continue

    return man_pages


def get_all_executables() -> List[str]:
    """Get all unique executables that have man pages."""
    man_pages = discover_man_pages()
    return sorted(man_pages.keys())


def process_program(program: str, man_pages_cache: Optional[Dict[str, Path]] = None) -> Optional[Tuple[str, str]]:
    """Process a single program: read its man page.

    Args:
        program: Program name
        man_pages_cache: Optional pre-computed map of program -> man page path

    Returns:
        (program_name, man_page_text) or None if no man page.
    """
    # Use cache if provided, otherwise discover
    if man_pages_cache is None:
        man_pages_cache = discover_man_pages()

    if program not in man_pages_cache:
        return None

    # Just run `man <program>` to get formatted output
    try:
        # Merge environment variables
        env = os.environ.copy()
        env['MANWIDTH'] = '200'  # Wide width to avoid excessive wrapping
        env['MANPAGER'] = 'cat'  # Disable pager

        result = subprocess.run(
            ['man', program],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
            env=env
        )

        if result.returncode == 0 and result.stdout:
            return (program, result.stdout)

    except Exception:
        pass

    return None
