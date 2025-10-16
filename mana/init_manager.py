"""Initialization manager for handling background startup tasks."""
from __future__ import annotations

import threading
from typing import Callable, Optional
from dataclasses import dataclass
from enum import Enum


class InitStage(Enum):
    """Stages of initialization."""
    NOT_STARTED = "not_started"
    LOADING_MODEL = "loading_model"
    CHECKING_INDEX = "checking_index"
    BUILDING_INDEX = "building_index"
    COMPLETE = "complete"
    ERROR = "error"


@dataclass
class InitStatus:
    """Current initialization status."""
    stage: InitStage
    message: str
    current: int = 0
    total: int = 0
    error: Optional[str] = None


class InitializationManager:
    """Manages background initialization and status updates."""
    
    def __init__(self):
        self._status = InitStatus(InitStage.NOT_STARTED, "Starting up...")
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._status_callbacks = []
        
    def add_status_callback(self, callback: Callable[[InitStatus], None]):
        """Add a callback to be notified of status changes."""
        with self._lock:
            self._status_callbacks.append(callback)
    
    def get_status(self) -> InitStatus:
        """Get current initialization status."""
        with self._lock:
            return self._status
    
    def is_complete(self) -> bool:
        """Check if initialization is complete."""
        with self._lock:
            return self._status.stage == InitStage.COMPLETE
    
    def is_error(self) -> bool:
        """Check if there was an error."""
        with self._lock:
            return self._status.stage == InitStage.ERROR
    
    def mark_complete(self):
        """Mark initialization as complete (for when it's not needed)."""
        self._update_status(InitStage.COMPLETE, "Ready!", 1, 1)
    
    def _update_status(self, stage: InitStage, message: str, current: int = 0, total: int = 0, error: Optional[str] = None):
        """Update status and notify callbacks."""
        with self._lock:
            self._status = InitStatus(stage, message, current, total, error)
            callbacks = self._status_callbacks.copy()
        
        # Call callbacks outside lock to avoid deadlocks
        for callback in callbacks:
            try:
                callback(self._status)
            except Exception:
                pass  # Ignore callback errors
    
    def start_initialization(self, init_fn: Callable[[Callable], None]):
        """Start initialization in background thread.
        
        Args:
            init_fn: Function that performs initialization. It receives a progress_callback
                    function(stage, current, total, message) that it should call to report progress.
        """
        if self._thread is not None and self._thread.is_alive():
            return  # Already running
        
        def progress_callback(stage: str, current: int, total: int, message: str):
            """Progress callback for initialization functions."""
            # Map stage strings to InitStage enum
            stage_map = {
                "discovery": (InitStage.CHECKING_INDEX, "Discovering executables..."),
                "scanning": (InitStage.BUILDING_INDEX, "Scanning for man pages..."),
                "extracting": (InitStage.BUILDING_INDEX, "Processing man pages..."),
                "embedding": (InitStage.BUILDING_INDEX, "Generating embeddings..."),
                "saving": (InitStage.BUILDING_INDEX, "Saving database..."),
                "complete": (InitStage.COMPLETE, "Ready!"),
            }
            
            init_stage, base_message = stage_map.get(stage, (InitStage.BUILDING_INDEX, message))
            
            # Use the provided message if it's more specific
            display_message = message if message and message != base_message else base_message
            self._update_status(init_stage, display_message, current, total)
        
        def run_init():
            """Run initialization in background."""
            try:
                # First update: loading model (happens during first build_vector_database call)
                self._update_status(InitStage.LOADING_MODEL, "Loading embedding model...")
                init_fn(progress_callback)
                # Mark complete if not already done
                if self.get_status().stage != InitStage.COMPLETE:
                    self._update_status(InitStage.COMPLETE, "Ready!", 1, 1)
            except Exception as e:
                self._update_status(InitStage.ERROR, "Initialization failed", error=str(e))
        
        self._thread = threading.Thread(target=run_init, daemon=True)
        self._thread.start()
