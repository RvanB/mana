"""Favorites management - persists marked programs."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Set

from .config import MANA_DIR


FAVORITES_FILE = MANA_DIR / "favorites.json"


class FavoritesManager:
    """Manages favorite programs."""

    def __init__(self):
        """Initialize favorites manager."""
        self._favorites: Set[str] = set()
        self._load()

    def _load(self):
        """Load favorites from disk."""
        if FAVORITES_FILE.exists():
            try:
                with open(FAVORITES_FILE, 'r') as f:
                    data = json.load(f)
                    self._favorites = set(data.get('favorites', []))
            except Exception:
                self._favorites = set()

    def _save(self):
        """Save favorites to disk."""
        try:
            MANA_DIR.mkdir(parents=True, exist_ok=True)
            with open(FAVORITES_FILE, 'w') as f:
                json.dump({'favorites': sorted(self._favorites)}, f, indent=2)
        except Exception:
            pass

    def add(self, program: str):
        """Add a program to favorites."""
        self._favorites.add(program)
        self._save()

    def remove(self, program: str):
        """Remove a program from favorites."""
        self._favorites.discard(program)
        self._save()

    def toggle(self, program: str):
        """Toggle a program's favorite status."""
        if program in self._favorites:
            self.remove(program)
        else:
            self.add(program)

    def is_favorite(self, program: str) -> bool:
        """Check if a program is favorited."""
        return program in self._favorites

    def get_all(self) -> Set[str]:
        """Get all favorite programs."""
        return self._favorites.copy()

    def clear(self):
        """Clear all favorites."""
        self._favorites.clear()
        self._save()
