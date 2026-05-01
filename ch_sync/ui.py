from __future__ import annotations

import queue
import threading
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ImportError:  # pragma: no cover - only relevant on Python builds without Tk.
    tk = None
    ttk = None
    filedialog = None
    messagebox = None

from .constants import DEFAULT_PORT
from .sync import sync_library


class SyncApp:
    def __init__(self, root: tk.Tk, initial_library: str = "", initial_port: int = DEFAULT_PORT) -> None:
        self.root = root
        self.root.title("Clone Hero TCP Sync")
        self.root.geometry("760x520")
        self.root.minsize(640, 430)

        self.messages: queue.Queue[str | tuple[str, int, int | None, str]] = queue.Queue()
        self.worker: threading.Thread | None = None

        self.mode_var = tk.StringVar(value="host")
        self.library_var = tk.StringVar(value=initial_library)
        self.host_var = tk.StringVar(value="")
        self.port_var = tk.StringVar(value=str(initial_port))
        self.status_var = tk.StringVar(value="Idle")
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_text_var = tk.StringVar(value="")

        self.build_ui()
        self.root.after(100, self.drain_logs)

    def build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(2, weight=1)

        top = ttk.Frame(self.root, padding=14)
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(1, weight=1)

        ttk.Label(top, text="Library").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(top, textvariable=self.library_var).grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Button(top, text="Browse", command=self.browse_library).grid(row=0, column=2, padx=(8, 0), pady=4)

        mode_frame = ttk.Frame(top)
        mode_frame.grid(row=1, column=1, sticky="w", pady=6)
        ttk.Radiobutton(mode_frame, text="Host", variable=self.mode_var, value="host", command=self.update_mode).pack(side="left")
        ttk.Radiobutton(mode_frame, text="Join", variable=self.mode_var, value="join", command=self.update_mode).pack(side="left", padx=(14, 0))

        ttk.Label(top, text="Friend IP").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=4)
        self.host_entry = ttk.Entry(top, textvariable=self.host_var)
        self.host_entry.grid(row=2, column=1, sticky="ew", pady=4)

        ttk.Label(top, text="Port").grid(row=3, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(top, textvariable=self.port_var, width=12).grid(row=3, column=1, sticky="w", pady=4)

        actions = ttk.Frame(self.root, padding=(14, 0, 14, 10))
        actions.grid(row=1, column=0, sticky="ew")
        actions.columnconfigure(1, weight=1)
        self.start_button = ttk.Button(actions, text="Start Sync", command=self.start_sync)
        self.start_button.grid(row=0, column=0, sticky="w")
        ttk.Label(actions, textvariable=self.status_var).grid(row=0, column=1, sticky="e")
        self.progress_bar = ttk.Progressbar(actions, variable=self.progress_var, maximum=100)
        self.progress_bar.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Label(actions, textvariable=self.progress_text_var).grid(row=2, column=0, columnspan=2, sticky="ew", pady=(3, 0))

        log_frame = ttk.Frame(self.root, padding=(14, 0, 14, 14))
        log_frame.grid(row=2, column=0, sticky="nsew")
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)

        self.log_box = tk.Text(log_frame, wrap="word", state="disabled", height=16)
        self.log_box.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(log_frame, command=self.log_box.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log_box.configure(yscrollcommand=scrollbar.set)

        self.update_mode()

    def update_mode(self) -> None:
        if self.mode_var.get() == "host":
            self.host_entry.configure(state="disabled")
        else:
            self.host_entry.configure(state="normal")

    def browse_library(self) -> None:
        selected = filedialog.askdirectory(title="Select Clone Hero Songs Library")
        if selected:
            self.library_var.set(selected)

    def append_log(self, message: str) -> None:
        self.log_box.configure(state="normal")
        self.log_box.insert("end", message + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def queue_log(self, message: str) -> None:
        self.messages.put(message)

    def queue_progress(self, phase: str, current: int, total: int | None, detail: str) -> None:
        self.messages.put((phase, current, total, detail))

    def apply_progress(self, phase: str, current: int, total: int | None, detail: str) -> None:
        if total:
            percent = max(0.0, min(100.0, current / total * 100))
            self.progress_bar.configure(mode="determinate", maximum=100)
            self.progress_var.set(percent)
            self.progress_text_var.set(f"{phase}: {current}/{total} - {detail}")
        else:
            self.progress_bar.configure(mode="determinate", maximum=100)
            self.progress_var.set(100 if current else 0)
            self.progress_text_var.set(f"{phase}: {detail}")

    def drain_logs(self) -> None:
        while True:
            try:
                message = self.messages.get_nowait()
            except queue.Empty:
                break
            if isinstance(message, tuple):
                self.apply_progress(*message)
            else:
                self.append_log(message)
        self.root.after(100, self.drain_logs)

    def start_sync(self) -> None:
        if self.worker and self.worker.is_alive():
            return

        library = Path(self.library_var.get()).expanduser()
        mode = self.mode_var.get()
        host = self.host_var.get().strip()
        try:
            port = int(self.port_var.get())
            if not 1 <= port <= 65535:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid port", "Port must be a number from 1 to 65535.")
            return

        if mode == "join" and not host:
            messagebox.showerror("Missing friend IP", "Enter your friend's IP address before joining.")
            return
        if not library.exists() or not library.is_dir():
            messagebox.showerror("Invalid library", "Choose a valid Clone Hero song library folder.")
            return

        self.start_button.configure(state="disabled")
        self.status_var.set("Running")
        self.progress_var.set(0)
        self.progress_text_var.set("")
        self.append_log("")
        self.append_log(f"Starting sync for {library}")

        def run() -> None:
            try:
                sync_library(library, mode, host, port, self.queue_log, self.queue_progress)
                self.queue_log("Done.")
            except Exception as exc:  # noqa: BLE001 - show UI-friendly error.
                self.queue_log(f"Error: {exc}")
            finally:
                self.root.after(0, self.finish_sync)

        self.worker = threading.Thread(target=run, daemon=True)
        self.worker.start()

    def finish_sync(self) -> None:
        self.start_button.configure(state="normal")
        self.status_var.set("Idle")


def run_ui(initial_library: str, port: int) -> None:
    if tk is None:
        raise RuntimeError("Tkinter is not available in this Python install. Run with --no-ui instead.")
    root = tk.Tk()
    SyncApp(root, initial_library=initial_library, initial_port=port)
    root.mainloop()
