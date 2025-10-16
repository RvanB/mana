"""Progress bar rendering for TUI."""
from __future__ import annotations

import curses


def draw_progress_bar(stdscr, y: int, x: int, width: int, current: int, total: int, message: str = ""):
    """Draw a progress bar in the TUI."""
    height, screen_width = stdscr.getmaxyx()

    if total == 0:
        percent = 0
    else:
        percent = min(100, int((current / total) * 100))

    bar_width = width - 10  # Leave room for percentage
    filled = int((bar_width * percent) / 100)
    bar = "█" * filled + "░" * (bar_width - filled)

    # Draw progress bar
    bar_line = f"[{bar}] {percent:3d}%"
    stdscr.addstr(y, x, bar_line, curses.color_pair(2))

    # Draw message centered below progress bar
    if message:
        # Truncate message if too long
        msg = message[:screen_width - 4]
        msg_x = (screen_width - len(msg)) // 2
        stdscr.addstr(y + 2, msg_x, msg, curses.color_pair(4))
