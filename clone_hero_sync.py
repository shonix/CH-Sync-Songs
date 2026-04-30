#!/usr/bin/env python3
"""
Small Clone Hero song-library sync tool.

Run examples:
  python clone_hero_sync.py --library "D:\\Clone Hero\\Songs"
  python clone_hero_sync.py --no-ui --host --library "D:\\Clone Hero\\Songs" --port 50505
  python clone_hero_sync.py --no-ui --connect 192.168.1.50 --library "D:\\Clone Hero\\Songs"
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import queue
import socket
import struct
import tempfile
import threading
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ImportError:  # pragma: no cover - only relevant on Python builds without Tk.
    tk = None
    ttk = None
    filedialog = None
    messagebox = None


DEFAULT_PORT = 50505
CHUNK_SIZE = 1024 * 1024
MAX_JSON_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True)
class Song:
    hash: str
    folder: Path
    folder_name: str
    title: str
    size: int
    file_count: int


def log_print(message: str) -> None:
    print(message, flush=True)


def parse_song_title(song_ini: Path) -> str:
    try:
        for line in song_ini.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.strip().lower().startswith("name"):
                _, value = line.split("=", 1)
                value = value.strip()
                if value:
                    return value
    except OSError:
        pass
    return song_ini.parent.name


def find_song_dirs(library: Path) -> list[Path]:
    song_dirs: list[Path] = []
    ignored = {".git", "__pycache__"}
    for root, dirs, files in os.walk(library):
        dirs[:] = [d for d in dirs if d not in ignored]
        if any(f.lower() == "song.ini" for f in files):
            song_dirs.append(Path(root))
            dirs[:] = []
    return sorted(song_dirs, key=lambda p: str(p).lower())


def hash_song_folder(folder: Path) -> tuple[str, int, int]:
    digest = hashlib.sha256()
    total_size = 0
    file_count = 0

    for file_path in sorted((p for p in folder.rglob("*") if p.is_file()), key=lambda p: str(p.relative_to(folder)).lower()):
        rel = file_path.relative_to(folder).as_posix()
        digest.update(rel.encode("utf-8", errors="surrogateescape"))
        digest.update(b"\0")
        try:
            with file_path.open("rb") as source:
                while True:
                    chunk = source.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    digest.update(chunk)
                    total_size += len(chunk)
            file_count += 1
        except OSError:
            continue

    return digest.hexdigest(), total_size, file_count


def build_manifest(library: Path, log: Callable[[str], None]) -> dict[str, dict[str, object]]:
    library = library.resolve()
    if not library.exists() or not library.is_dir():
        raise ValueError(f"Library path does not exist or is not a folder: {library}")

    song_dirs = find_song_dirs(library)
    log(f"Found {len(song_dirs)} song folders. Hashing files...")
    manifest: dict[str, dict[str, object]] = {}

    for index, folder in enumerate(song_dirs, start=1):
        song_hash, size, file_count = hash_song_folder(folder)
        title = parse_song_title(folder / "song.ini")
        manifest.setdefault(
            song_hash,
            {
                "folder_name": folder.name,
                "title": title,
                "size": size,
                "file_count": file_count,
            },
        )
        if index % 25 == 0:
            log(f"Hashed {index}/{len(song_dirs)} songs...")

    return manifest


def build_song_index(library: Path, log: Callable[[str], None]) -> dict[str, Song]:
    index: dict[str, Song] = {}
    for folder in find_song_dirs(library):
        song_hash, size, file_count = hash_song_folder(folder)
        index.setdefault(
            song_hash,
            Song(
                hash=song_hash,
                folder=folder,
                folder_name=folder.name,
                title=parse_song_title(folder / "song.ini"),
                size=size,
                file_count=file_count,
            ),
        )
    log(f"Indexed {len(index)} local unique songs.")
    return index


def send_json(sock: socket.socket, payload: dict[str, object]) -> None:
    data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    sock.sendall(struct.pack("!Q", len(data)))
    sock.sendall(data)


def recv_exact(sock: socket.socket, size: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < size:
        chunk = sock.recv(min(CHUNK_SIZE, size - len(chunks)))
        if not chunk:
            raise ConnectionError("Connection closed while receiving data.")
        chunks.extend(chunk)
    return bytes(chunks)


def recv_json(sock: socket.socket) -> dict[str, object]:
    size = struct.unpack("!Q", recv_exact(sock, 8))[0]
    if size > MAX_JSON_BYTES:
        raise ValueError(f"Refusing oversized JSON message: {size} bytes")
    return json.loads(recv_exact(sock, size).decode("utf-8"))


def stream_file(sock: socket.socket, path: Path) -> None:
    with path.open("rb") as source:
        while True:
            chunk = source.read(CHUNK_SIZE)
            if not chunk:
                break
            sock.sendall(chunk)


def receive_file(sock: socket.socket, path: Path, size: int, progress: Callable[[int], None]) -> None:
    received = 0
    with path.open("wb") as target:
        while received < size:
            chunk = sock.recv(min(CHUNK_SIZE, size - received))
            if not chunk:
                raise ConnectionError("Connection closed during file transfer.")
            target.write(chunk)
            received += len(chunk)
            progress(received)


def make_song_zip(song: Song) -> Path:
    temp = tempfile.NamedTemporaryFile(prefix="clone_hero_song_", suffix=".zip", delete=False)
    temp_path = Path(temp.name)
    temp.close()
    try:
        with zipfile.ZipFile(temp_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for file_path in sorted((p for p in song.folder.rglob("*") if p.is_file()), key=lambda p: str(p.relative_to(song.folder)).lower()):
                archive.write(file_path, file_path.relative_to(song.folder).as_posix())
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise
    return temp_path


def safe_folder_name(name: str) -> str:
    cleaned = "".join("_" if c in '<>:"/\\|?*' or ord(c) < 32 else c for c in name).strip(" .")
    return cleaned or "Imported Song"


def unique_destination(library: Path, folder_name: str) -> Path:
    base = safe_folder_name(folder_name)
    candidate = library / base
    counter = 2
    while candidate.exists():
        candidate = library / f"{base} ({counter})"
        counter += 1
    return candidate


def extract_song_zip(zip_path: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    try:
        with zipfile.ZipFile(zip_path) as archive:
            for member in archive.infolist():
                member_path = destination / member.filename
                resolved = member_path.resolve()
                if destination.resolve() not in resolved.parents and resolved != destination.resolve():
                    raise ValueError(f"Unsafe zip member path: {member.filename}")
            archive.extractall(destination)
    except Exception:
        if destination.exists():
            for child in sorted(destination.rglob("*"), reverse=True):
                if child.is_file() or child.is_symlink():
                    child.unlink(missing_ok=True)
                elif child.is_dir():
                    child.rmdir()
            destination.rmdir()
        raise


def send_requested_songs(sock: socket.socket, requested_hashes: list[str], songs: dict[str, Song], log: Callable[[str], None]) -> None:
    for song_hash in requested_hashes:
        song = songs.get(song_hash)
        if song is None:
            log(f"Peer requested unknown song hash {song_hash[:12]}; skipping.")
            continue

        log(f"Packing '{song.title}'...")
        zip_path = make_song_zip(song)
        try:
            send_json(
                sock,
                {
                    "type": "song",
                    "hash": song.hash,
                    "folder_name": song.folder_name,
                    "title": song.title,
                    "zip_size": zip_path.stat().st_size,
                },
            )
            log(f"Sending '{song.title}'...")
            stream_file(sock, zip_path)
        finally:
            zip_path.unlink(missing_ok=True)
    send_json(sock, {"type": "done"})


def receive_requested_songs(sock: socket.socket, library: Path, expected_hashes: set[str], log: Callable[[str], None]) -> int:
    received_count = 0
    while True:
        message = recv_json(sock)
        message_type = message.get("type")
        if message_type == "done":
            return received_count
        if message_type != "song":
            raise ValueError(f"Unexpected message from peer: {message_type}")

        song_hash = str(message["hash"])
        title = str(message.get("title") or message.get("folder_name") or song_hash[:12])
        zip_size = int(message["zip_size"])
        if song_hash not in expected_hashes:
            log(f"Receiving unexpected song '{title}' anyway.")

        temp = tempfile.NamedTemporaryFile(prefix="clone_hero_recv_", suffix=".zip", delete=False)
        temp_path = Path(temp.name)
        temp.close()

        last_report = 0.0

        def progress(bytes_received: int) -> None:
            nonlocal last_report
            now = time.monotonic()
            if now - last_report >= 1.0 or bytes_received == zip_size:
                percent = (bytes_received / zip_size * 100) if zip_size else 100
                log(f"Receiving '{title}': {percent:.0f}%")
                last_report = now

        try:
            receive_file(sock, temp_path, zip_size, progress)
            destination = unique_destination(library, str(message.get("folder_name") or title))
            extract_song_zip(temp_path, destination)
            received_count += 1
            log(f"Imported '{title}' into {destination.name}.")
        finally:
            temp_path.unlink(missing_ok=True)


def connect_as_host(port: int, log: Callable[[str], None]) -> socket.socket:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("", port))
    listener.listen(1)
    log(f"Hosting on port {port}. Waiting for a friend to connect...")
    conn, address = listener.accept()
    listener.close()
    log(f"Connected to {address[0]}:{address[1]}.")
    return conn


def connect_as_client(host: str, port: int, log: Callable[[str], None]) -> socket.socket:
    log(f"Connecting to {host}:{port}...")
    sock = socket.create_connection((host, port), timeout=30)
    log("Connected.")
    return sock


def sync_library(library: Path, mode: str, host: str, port: int, log: Callable[[str], None]) -> None:
    library = library.resolve()
    local_manifest = build_manifest(library, log)
    local_index = build_song_index(library, log)

    with (connect_as_host(port, log) if mode == "host" else connect_as_client(host, port, log)) as sock:
        sock.settimeout(None)
        send_json(sock, {"type": "manifest", "songs": local_manifest})
        peer_message = recv_json(sock)
        if peer_message.get("type") != "manifest":
            raise ValueError("Peer did not send a manifest.")

        peer_manifest = dict(peer_message["songs"])
        local_hashes = set(local_manifest)
        peer_hashes = set(peer_manifest)
        needed_from_peer = sorted(peer_hashes - local_hashes)
        peer_needs = sorted(local_hashes - peer_hashes)

        log(f"You are missing {len(needed_from_peer)} songs. Peer is missing {len(peer_needs)} songs.")
        send_json(sock, {"type": "request", "hashes": needed_from_peer})
        request_message = recv_json(sock)
        if request_message.get("type") != "request":
            raise ValueError("Peer did not send a request list.")
        requested_by_peer = [str(h) for h in request_message["hashes"]]

        sender_error: list[BaseException] = []

        def sender() -> None:
            try:
                send_requested_songs(sock, requested_by_peer, local_index, log)
            except BaseException as exc:  # noqa: BLE001 - surfaced to caller after receiver exits.
                sender_error.append(exc)

        thread = threading.Thread(target=sender, daemon=True)
        thread.start()
        received = receive_requested_songs(sock, library, set(needed_from_peer), log)
        thread.join()
        if sender_error:
            raise sender_error[0]

    log(f"Sync complete. Imported {received} songs.")


class SyncApp:
    def __init__(self, root: tk.Tk, initial_library: str = "", initial_port: int = DEFAULT_PORT) -> None:
        self.root = root
        self.root.title("Clone Hero TCP Sync")
        self.root.geometry("760x520")
        self.root.minsize(640, 430)

        self.messages: queue.Queue[str] = queue.Queue()
        self.worker: threading.Thread | None = None

        self.mode_var = tk.StringVar(value="host")
        self.library_var = tk.StringVar(value=initial_library)
        self.host_var = tk.StringVar(value="")
        self.port_var = tk.StringVar(value=str(initial_port))
        self.status_var = tk.StringVar(value="Idle")

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

    def drain_logs(self) -> None:
        while True:
            try:
                self.append_log(self.messages.get_nowait())
            except queue.Empty:
                break
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
        self.append_log("")
        self.append_log(f"Starting sync for {library}")

        def run() -> None:
            try:
                sync_library(library, mode, host, port, self.queue_log)
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync Clone Hero song folders with a friend over TCP.")
    parser.add_argument("--library", "-l", default="", help="Path to your Clone Hero Songs library.")
    parser.add_argument("--port", "-p", type=int, default=DEFAULT_PORT, help=f"TCP port to use. Default: {DEFAULT_PORT}")
    parser.add_argument("--no-ui", action="store_true", help="Run in terminal mode instead of opening the UI.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--host", action="store_true", help="Wait for a friend to connect.")
    group.add_argument("--connect", metavar="IP_OR_HOST", help="Connect to a friend's hosted sync.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.no_ui:
        if not args.library:
            raise SystemExit("--library is required when using --no-ui")
        if args.host:
            mode = "host"
            host = ""
        elif args.connect:
            mode = "join"
            host = args.connect
        else:
            raise SystemExit("Use --host or --connect with --no-ui")
        sync_library(Path(args.library).expanduser(), mode, host, args.port, log_print)
        return 0

    run_ui(args.library, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
