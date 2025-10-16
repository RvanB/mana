"""Main TUI application logic."""
from __future__ import annotations

import curses
import curses.textpad
import os
import subprocess
from typing import List, Dict, Callable

from ..config import DEFAULT_TOP_K


def run_tui(
    initial_query: str = "",
    initial_results: List[Dict[str, str]] = None,
    top_k: int = DEFAULT_TOP_K,
    search_fn: Callable[[str, int], List[Dict[str, str]]] = None
):
    """Run the curses-based TUI.

    Args:
        initial_query: Initial search query to display
        initial_results: Initial search results to display
        top_k: Number of results to return per search
        search_fn: Search callback function(query, top_k) -> results

    Note: The database index must already exist before calling this function.
    Use ensure_index_exists() in cli.py to build it if needed.
    """
    if search_fn is None:
        raise ValueError("search_fn callback is required")
    def main_loop(stdscr):
        # Initialize colors
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_CYAN, -1)
        curses.init_pair(2, curses.COLOR_GREEN, -1)
        curses.init_pair(3, curses.COLOR_BLACK, curses.COLOR_WHITE)
        curses.init_pair(4, curses.COLOR_YELLOW, -1)

        results = initial_results or []
        selected_idx = 0
        current_page = 0
        query = initial_query

        # Hide cursor by default
        curses.curs_set(0)

        while True:
            stdscr.clear()
            height, width = stdscr.getmaxyx()

            # Draw border
            stdscr.border()

            # Draw title
            title = " mana - Program Discovery "
            stdscr.addstr(0, (width - len(title)) // 2, title, curses.color_pair(1) | curses.A_BOLD)

            # Draw search box with padding
            search_label = "Search: "
            stdscr.addstr(2, 4, search_label, curses.color_pair(4))
            stdscr.addstr(2, 4 + len(search_label), query[:width - 8 - len(search_label)])

            # Draw help text - simple version, but we support vim/emacs bindings secretly
            help_text = "/:search | ESC:cancel | q:quit | Enter:man | ↑/↓:navigate | ←/→:page"
            stdscr.addstr(height - 1, 4, help_text[:width-8], curses.color_pair(2))

            # Calculate list area with more padding
            list_start_y = 4
            list_height = height - 5

            # Draw results with pagination
            if not results:
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
                    page_info = f"Page {current_page + 1}/{total_pages}"
                    stdscr.addstr(1, width - len(page_info) - 4, page_info, curses.color_pair(2))

                for i in range(page_size):
                    result_idx = page_start + i
                    if result_idx >= page_end:
                        break

                    chunk = results[result_idx]
                    program = chunk.get('program', 'unknown')
                    description = chunk.get('semantic_summary', 'No description')
                    similarity = chunk.get('similarity', 0)

                    y = list_start_y + i
                    is_selected = result_idx == selected_idx

                    # Format line with better spacing
                    line = f"  {program:<22} {description}"
                    line = line[:width-8]  # Truncate to fit with padding

                    if is_selected:
                        # Draw selection with full-width highlight
                        stdscr.addstr(y, 2, " " * (width - 4), curses.color_pair(3))
                        stdscr.addstr(y, 2, line, curses.color_pair(3) | curses.A_BOLD)
                    else:
                        stdscr.addstr(y, 2, line)

            stdscr.refresh()

            # Handle input
            try:
                key = stdscr.getch()
            except KeyboardInterrupt:
                break

            if key == ord('q'):
                break
            elif key == ord('/') or key == ord('s') or (not results and key >= 32 and key <= 126):  # '/' or 's' or typing when no results
                # Enter search mode
                curses.noecho()  # Disable echo, we'll handle it manually
                curses.curs_set(1)
                stdscr.addstr(2, 4, " " * (width - 8))  # Clear line
                stdscr.addstr(2, 4, "Search: ", curses.color_pair(4))
                stdscr.refresh()

                # Get input using textpad for better control
                input_win = curses.newwin(1, width - 16, 2, 12)
                input_win.keypad(1)

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
                        curses.init_pair(1, curses.COLOR_CYAN, -1)
                        curses.init_pair(2, curses.COLOR_GREEN, -1)
                        curses.init_pair(3, curses.COLOR_BLACK, curses.COLOR_WHITE)
                        curses.init_pair(4, curses.COLOR_YELLOW, -1)

    curses.wrapper(main_loop)
