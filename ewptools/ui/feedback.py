"""Status and log feedback helpers for the Tkinter UI."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox


class AppFeedback:
    """Handles status text, log output, and modal error reporting."""

    def __init__(self, status_var: tk.StringVar, log_text: tk.Text):
        self._status_var = status_var
        self._log_text = log_text

    def set_status(self, text: str) -> None:
        self._status_var.set(text)

    def log(self, text: str) -> None:
        self._log_text.configure(state=tk.NORMAL)
        self._log_text.insert(tk.END, f"{text}\n")
        self._log_text.see(tk.END)
        self._log_text.configure(state=tk.DISABLED)

    def ok(self, text: str) -> None:
        self.set_status(text)
        self.log(f"[OK] {text}")

    def warn(self, text: str) -> None:
        self.set_status(text)
        self.log(f"[WARN] {text}")

    def error(self, text: str, exc: Exception | None = None) -> None:
        message = f"{text}: {exc}" if exc is not None else text
        self.set_status(message)
        self.log(f"[ERR] {message}")
        messagebox.showerror("错误", message)

    def clear_log(self) -> None:
        self._log_text.configure(state=tk.NORMAL)
        self._log_text.delete("1.0", tk.END)
        self._log_text.configure(state=tk.DISABLED)
