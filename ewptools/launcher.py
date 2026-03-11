"""Application bootstrap helpers."""

from __future__ import annotations

import os
import sys
import tkinter as tk
from collections.abc import Sequence

from .ui.main_window import EwpToolsApp


def _hide_console_window() -> None:
    if os.name != "nt":
        return
    try:
        import ctypes

        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)
    except Exception:
        pass


def run_gui(ewp_path: str | None = None) -> None:
    _hide_console_window()
    root = tk.Tk()
    try:
        from ctypes import windll

        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    EwpToolsApp(root, ewp_path)
    root.mainloop()


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv if argv is None else argv)
    ewp_path = None
    if len(args) > 1 and args[1].lower().endswith(".ewp"):
        ewp_path = args[1]
    run_gui(ewp_path)
    return 0

