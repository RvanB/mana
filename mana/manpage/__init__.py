"""Man page processing utilities."""
from __future__ import annotations

from .parser import extract_name_section
from .discovery import get_all_executables, process_program, discover_man_pages

__all__ = [
    'extract_name_section',
    'get_all_executables',
    'process_program',
    'discover_man_pages',
]
