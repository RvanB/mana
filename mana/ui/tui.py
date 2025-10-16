"""Main TUI application logic."""
from __future__ import annotations

import curses
import curses.textpad
import os
import subprocess
import time
from typing import List, Dict, Callable, Optional

from ..config import DEFAULT_TOP_K
from ..init_manager import InitializationManager, InitStage


def run_tui(
    initial_query: str = "",
    initial_results: List[Dict[str, str]] = None,
    top_k: int = DEFAULT_TOP_K,
    search_fn: Callable[[str, int], List[Dict[str, str]]] = None,
    is_favorite_fn: Callable[[str], bool] = None,
    toggle_favorite_fn: Callable[[str], None] = None,
    get_favorites_fn: Callable[[], List[Dict[str, str]]] = None,
    init_manager: Optional[InitializationManager] = None
):
    """Run the curses-based TUI.

    Args:
        initial_query: Initial search query to display
        initial_results: Initial search results to display
        top_k: Number of results to return per search
        search_fn: Search callback function(query, top_k) -> results
        is_favorite_fn: Check if program is favorited callback(program) -> bool
        toggle_favorite_fn: Toggle favorite status callback(program) -> None
        get_favorites_fn: Get all favorites as results callback() -> results
        init_manager: Optional initialization manager for background loading

    Note: The database index must already exist before calling this function,
    or an init_manager must be provided to handle background initialization.
    """
    if search_fn is None:
        raise ValueError("search_fn callback is required")
    if is_favorite_fn is None:
        raise ValueError("is_favorite_fn callback is required")
    if toggle_favorite_fn is None:
        raise ValueError("toggle_favorite_fn callback is required")
    if get_favorites_fn is None:
        raise ValueError("get_favorites_fn callback is required")
    def main_loop(stdscr):
        # Initialize modern color scheme
        curses.start_color()
        curses.use_default_colors()

        # Modern color palette - blue as accent color
        curses.init_pair(1, curses.COLOR_BLUE, -1)         # Title/headers/accents - blue
        curses.init_pair(2, 240, -1)                        # Help text - dim gray
        curses.init_pair(3, curses.COLOR_BLUE, -1)         # Selection text - blue
        curses.init_pair(4, curses.COLOR_BLUE, -1)         # Search label - blue
        curses.init_pair(5, curses.COLOR_MAGENTA, -1)      # Unused
        curses.init_pair(6, -1, -1)                         # Program names - default terminal color
        curses.init_pair(7, 244, -1)                        # Descriptions - medium gray
        curses.init_pair(8, curses.COLOR_RED, -1)          # Favorite star - red
        curses.init_pair(9, curses.COLOR_YELLOW, -1)       # Spinner - yellow

        results = initial_results or []
        selected_idx = 0
        current_page = 0
        query = initial_query
        viewing_favorites = False  # Track if we're in favorites view
        spinner_chars = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
        spinner_idx = 0

        # Hide cursor by default
        curses.curs_set(0)
        
        # Set non-blocking input for spinner animation
        stdscr.nodelay(True)
        stdscr.timeout(100)  # 100ms timeout for getch()

        while True:
            stdscr.clear()
            height, width = stdscr.getmaxyx()
            
            # Check if we're still initializing
            is_initializing = init_manager and not init_manager.is_complete() and not init_manager.is_error()

            # Draw title with icon
            if viewing_favorites:
                title = "★ Favorites"
                stdscr.addstr(0, 2, title, curses.color_pair(1) | curses.A_BOLD)
            else:
                title = "◉ mana"
                stdscr.addstr(0, 2, title, curses.color_pair(1) | curses.A_BOLD)

            # Draw initialization status or count in top right
            if is_initializing and init_manager:
                status = init_manager.get_status()
                spinner = spinner_chars[spinner_idx % len(spinner_chars)]
                status_text = f"{spinner} {status.message}"
                stdscr.addstr(0, width - len(status_text) - 2, status_text, curses.color_pair(9))
                spinner_idx += 1
            elif results:
                count_text = f"{len(results)} results"
                stdscr.addstr(0, width - len(count_text) - 2, count_text, curses.color_pair(2))

            # Draw horizontal line under the header (using hyphens for ligature support)
            stdscr.addstr(1, 0, "-" * width, curses.color_pair(2))

            # Draw bottom border
            stdscr.addstr(height - 2, 0, "-" * width, curses.color_pair(2))

            # If initializing, show status message in center
            if is_initializing and init_manager:
                status = init_manager.get_status()
                
                # Center status messages
                center_y = height // 2
                
                # Draw spinner and main message
                spinner = spinner_chars[spinner_idx % len(spinner_chars)]
                main_msg = f"{spinner}  {status.message}"
                msg_x = max(2, (width - len(main_msg)) // 2)
                stdscr.addstr(center_y, msg_x, main_msg, curses.color_pair(9) | curses.A_BOLD)
                
                # Draw progress bar if we have progress info
                if status.total > 0:
                    bar_width = min(60, width - 10)
                    bar_x = (width - bar_width) // 2
                    percent = int((status.current / status.total) * 100)
                    filled = int((bar_width * percent) / 100)
                    bar = "█" * filled + "░" * (bar_width - filled)
                    bar_text = f"[{bar}] {percent}%"
                    stdscr.addstr(center_y + 2, bar_x, bar_text, curses.color_pair(2))
                    
                    # Show detail message below if available
                    if status.current > 0 and status.total > 0:
                        detail = f"{status.current}/{status.total}"
                        detail_x = (width - len(detail)) // 2
                        stdscr.addstr(center_y + 3, detail_x, detail, curses.color_pair(7))
                
                # Help text for initializing state
                help_text = "Initializing...  │  q quit"
                stdscr.addstr(height - 1, 2, help_text[:width-4], curses.color_pair(2))
            else:
                # Normal UI - draw search box with padding (only in search mode)
                if not viewing_favorites:
                    search_label = "› "
                    stdscr.addstr(2, 2, search_label, curses.color_pair(4) | curses.A_BOLD)
                    query_text = query if query else "(press / to search)"
                    query_color = curses.color_pair(0) if query else curses.color_pair(2)
                    stdscr.addstr(2, 2 + len(search_label), query_text[:width - 6 - len(search_label)], query_color)

                # Draw help text with modern look
                if viewing_favorites:
                    help_text = "v back  │  m unmark  │  ↑↓ navigate  │  ⏎ view  │  q quit"
                else:
                    help_text = "/ search  │  v favorites  │  m mark  │  ↑↓ navigate  │  ⏎ view  │  q quit"
                stdscr.addstr(height - 1, 2, help_text[:width-4], curses.color_pair(2))

            # Calculate list area with padding (avoid bottom border)
            list_start_y = 4
            list_height = height - 6  # Leave space for bottom border and help text

            # Draw results with pagination (only when not initializing)
            if is_initializing:
                # Don't show results during initialization
                pass
            elif not results:
                # Just show empty space when no results
                pass
            else:
                page_size = list_height
                total_pages = (len(results) + page_size - 1) // page_size  # Ceiling division
                current_page = max(0, min(current_page, total_pages - 1))

                page_start = current_page * page_size
                page_end = min(page_start + page_size, len(results))

                # Draw page indicator if multiple pages
                if total_pages > 1:
                    page_info = f"page {current_page + 1}/{total_pages}"
                    stdscr.addstr(0, width - len(page_info) - 15, page_info, curses.color_pair(2))

                for i in range(page_size):
                    result_idx = page_start + i
                    if result_idx >= page_end:
                        break

                    chunk = results[result_idx]
                    program = chunk.get('program', 'unknown')
                    description = chunk.get('semantic_summary', 'No description')
                    similarity = chunk.get('similarity', 0)

                    # Strip redundant program name from description
                    # e.g. "display - displays an image" -> "displays an image"
                    desc_lower = description.lower()
                    prog_lower = program.lower()
                    # Check for common patterns: "program - description" or "program – description"
                    for separator in [' - ', ' – ', ' — ']:
                        prefix = prog_lower + separator
                        if desc_lower.startswith(prefix):
                            description = description[len(prefix):].strip()
                            # Capitalize first letter
                            if description:
                                description = description[0].upper() + description[1:]
                            break

                    y = list_start_y + i
                    is_selected = result_idx == selected_idx
                    is_fav = is_favorite_fn(program)

                    # Modern list item layout - arrow and blue text for selection
                    # Cursor indicator (only show on selected)
                    if is_selected:
                        cursor = "▶ "
                        stdscr.addstr(y, 2, cursor, curses.color_pair(3) | curses.A_BOLD)  # Blue arrow
                    else:
                        stdscr.addstr(y, 2, "  ", curses.color_pair(0))

                    # Favorite star (red) - shown after arrow/space
                    star_x = 4
                    if is_fav:
                        stdscr.addstr(y, star_x, "★ ", curses.color_pair(8))  # Red star
                    else:
                        stdscr.addstr(y, star_x, "  ", curses.color_pair(0))  # Empty space to align

                    # Program name - blue if selected, always starts at same position
                    prog_x = 6
                    if is_selected:
                        prog_color = curses.color_pair(3)  # Blue for selected
                    else:
                        prog_color = curses.color_pair(6)  # Default (no special color for favorites)
                    stdscr.addstr(y, prog_x, program, prog_color | curses.A_BOLD)

                    # Description - blue if selected, always starts at same position
                    desc_x = prog_x + 24
                    desc_text = description[:width - desc_x - 2]
                    desc_color = curses.color_pair(3) if is_selected else curses.color_pair(7)
                    stdscr.addstr(y, desc_x, desc_text, desc_color)

            stdscr.refresh()

            # Handle input
            try:
                key = stdscr.getch()
            except KeyboardInterrupt:
                break

            # During initialization, only allow quit
            if is_initializing:
                if key == ord('q'):
                    break
                # Ignore all other input and continue showing status
                continue

            # Handle -1 (no input due to timeout) - just refresh the display
            if key == -1:
                continue

            if key == ord('q'):
                break
            elif key == ord('v'):  # Toggle favorites view
                viewing_favorites = not viewing_favorites
                if viewing_favorites:
                    # Switch to favorites view
                    results = get_favorites_fn()
                    selected_idx = 0
                    current_page = 0
                else:
                    # Switch back to search view
                    if query:
                        results = search_fn(query, top_k)
                    else:
                        results = []
                    selected_idx = 0
                    current_page = 0
            elif key == ord('m'):  # Mark/unmark favorite
                if results and 0 <= selected_idx < len(results):
                    program = results[selected_idx].get('program', '')
                    if program:
                        toggle_favorite_fn(program)
                        # If we're in favorites view and unmarked, refresh the list
                        if viewing_favorites:
                            results = get_favorites_fn()
                            # Adjust selection if we're now past the end
                            if selected_idx >= len(results) and results:
                                selected_idx = len(results) - 1
                            elif not results:
                                selected_idx = 0
            elif key == ord('/') or key == ord('s') or (not results and key >= 32 and key <= 126):  # '/' or 's' or typing when no results
                # Don't allow search in favorites view
                if viewing_favorites:
                    continue
                # Enter search mode
                curses.noecho()  # Disable echo, we'll handle it manually
                curses.curs_set(1)
                stdscr.addstr(2, 2, " " * (width - 4))  # Clear line
                stdscr.addstr(2, 2, "› ", curses.color_pair(4) | curses.A_BOLD)
                stdscr.refresh()

                # Get input using textpad for better control
                input_win = curses.newwin(1, width - 8, 2, 4)
                input_win.keypad(True)

                # Read input character by character to handle ESC
                new_query = ""

                # If we started with a character (not '/' or 's'), add it
                if key != ord('/') and key != ord('s'):
                    new_query = chr(key)
                    input_win.addch(chr(key))

                while True:
                    ch = input_win.getch()
                    if ch == 27:  # ESC
                        # Cancel search, restore previous query
                        new_query = None
                        break
                    elif ch == ord('\n') or ch == 10:  # Enter
                        break
                    elif ch == curses.KEY_BACKSPACE or ch == 127 or ch == 8:  # Backspace
                        if new_query:
                            new_query = new_query[:-1]
                            y, x = input_win.getyx()
                            if x > 0:
                                input_win.move(y, x - 1)
                                input_win.delch()
                    elif ch == curses.KEY_DOWN:  # Down arrow - exit to results
                        new_query = None
                        break
                    elif 32 <= ch <= 126:  # Printable character
                        new_query += chr(ch)
                        input_win.addch(chr(ch))
                    input_win.refresh()

                del input_win
                curses.noecho()
                curses.curs_set(0)

                # Only update if we didn't cancel
                if new_query is not None and new_query.strip():
                    query = new_query.strip()
                    results = search_fn(query, top_k)
                    selected_idx = 0
                    current_page = 0
            elif key == curses.KEY_DOWN or key == ord('j') or key == ord('n'):  # Down arrow or j or n
                if results:
                    page_size = list_height
                    page_start = current_page * page_size
                    page_end = min(page_start + page_size, len(results))

                    if selected_idx < len(results) - 1:
                        selected_idx += 1
                        # If we moved past the current page, go to next page
                        if selected_idx >= page_end:
                            current_page += 1
                    elif selected_idx == len(results) - 1:
                        # At the last item, wrap to first item on first page
                        selected_idx = 0
                        current_page = 0
            elif key == curses.KEY_UP or key == ord('k') or key == ord('p'):  # Up arrow or k or p
                if results:
                    page_size = list_height
                    page_start = current_page * page_size

                    if selected_idx > 0:
                        selected_idx -= 1
                        # If we moved before the current page, go to previous page
                        if selected_idx < page_start:
                            current_page -= 1
                    elif selected_idx == 0:
                        # At the first item, wrap to last item on last page
                        selected_idx = len(results) - 1
                        current_page = (len(results) - 1) // page_size
            elif key == curses.KEY_RIGHT or key == ord('l') or key == ord('f'):  # Right arrow or l or f
                if results:
                    page_size = list_height
                    total_pages = (len(results) + page_size - 1) // page_size
                    if current_page < total_pages - 1:
                        current_page += 1
                        # Move selection to first item on new page
                        selected_idx = current_page * page_size
            elif key == curses.KEY_LEFT or key == ord('h') or key == ord('b'):  # Left arrow or h or b
                if results:
                    page_size = list_height
                    if current_page > 0:
                        current_page -= 1
                        # Move selection to first item on new page
                        selected_idx = current_page * page_size
            elif key == ord('\n') or key == curses.KEY_ENTER or key == 10:
                # View man page
                if results and 0 <= selected_idx < len(results):
                    program = results[selected_idx].get('program', '')
                    if program:
                        curses.endwin()
                        # Clear screen before showing man page to avoid flash
                        os.system('clear')
                        subprocess.run(["man", program])
                        stdscr = curses.initscr()
                        curses.start_color()
                        curses.use_default_colors()
                        # Reinitialize color scheme after returning from man
                        curses.init_pair(1, curses.COLOR_BLUE, -1)
                        curses.init_pair(2, 240, -1)
                        curses.init_pair(3, curses.COLOR_BLUE, -1)
                        curses.init_pair(4, curses.COLOR_BLUE, -1)
                        curses.init_pair(5, curses.COLOR_MAGENTA, -1)
                        curses.init_pair(6, -1, -1)
                        curses.init_pair(7, 244, -1)
                        curses.init_pair(8, curses.COLOR_RED, -1)

    curses.wrapper(main_loop)
