from __future__ import annotations

import io
import json
import shutil
import socket
import struct
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Callable

from .constants import CHUNK_SIZE, MAX_JSON_BYTES
from .progress import ProgressCallback, noop_progress
from .songs import Song, unique_destination


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


class ChunkedSocketWriter(io.RawIOBase):
    def __init__(self, sock: socket.socket, progress: Callable[[int], None]) -> None:
        super().__init__()
        self.sock = sock
        self.progress = progress
        self.bytes_written = 0

    def writable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return False

    def tell(self) -> int:
        return self.bytes_written

    def write(self, data: bytes | bytearray | memoryview) -> int:
        chunk = bytes(data)
        if not chunk:
            return 0
        self.sock.sendall(struct.pack("!Q", len(chunk)))
        self.sock.sendall(chunk)
        self.bytes_written += len(chunk)
        self.progress(self.bytes_written)
        return len(chunk)


def stream_song_zip(sock: socket.socket, song: Song, progress: Callable[[int], None]) -> None:
    writer = ChunkedSocketWriter(sock, progress)
    try:
        with zipfile.ZipFile(writer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            files = (p for p in song.folder.rglob("*") if p.is_file())
            for file_path in sorted(files, key=lambda p: str(p.relative_to(song.folder)).lower()):
                archive.write(file_path, file_path.relative_to(song.folder).as_posix())
    finally:
        sock.sendall(struct.pack("!Q", 0))


def receive_chunked_file(sock: socket.socket, path: Path, progress: Callable[[int], None]) -> None:
    received = 0
    with path.open("wb") as target:
        while True:
            chunk_size = struct.unpack("!Q", recv_exact(sock, 8))[0]
            if chunk_size == 0:
                break
            remaining = chunk_size
            while remaining:
                chunk = sock.recv(min(CHUNK_SIZE, remaining))
                if not chunk:
                    raise ConnectionError("Connection closed during song transfer.")
                target.write(chunk)
                received += len(chunk)
                remaining -= len(chunk)
                progress(received)


def extract_song_zip(zip_path: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    try:
        with zipfile.ZipFile(zip_path) as archive:
            destination_root = destination.resolve()
            for member in archive.infolist():
                resolved = (destination / member.filename).resolve()
                if destination_root not in resolved.parents and resolved != destination_root:
                    raise ValueError(f"Unsafe zip member path: {member.filename}")
            archive.extractall(destination)
    except Exception:
        if destination.exists():
            shutil.rmtree(destination)
        raise


def send_requested_songs(
    sock: socket.socket,
    requested_hashes: list[str],
    songs: dict[str, Song],
    log: Callable[[str], None],
    progress: ProgressCallback = noop_progress,
) -> None:
    total = len(requested_hashes)
    for position, song_hash in enumerate(requested_hashes, start=1):
        song = songs.get(song_hash)
        if song is None:
            log(f"Peer requested unknown song hash {song_hash[:12]}; skipping.")
            progress("Sending", position, total, "Skipped missing local song")
            continue

        send_json(
            sock,
            {
                "type": "song_stream",
                "hash": song.hash,
                "folder_name": song.folder_name,
                "title": song.title,
                "size": song.size,
                "file_count": song.file_count,
            },
        )
        log(f"Streaming '{song.title}'...")
        stream_song_zip(sock, song, _log_megabytes(log, "Streaming", song.title))
        progress("Sending", position, total, song.title)
    send_json(sock, {"type": "done"})


def receive_requested_songs(
    sock: socket.socket,
    library: Path,
    expected_hashes: set[str],
    log: Callable[[str], None],
    report_progress: ProgressCallback = noop_progress,
) -> int:
    received_count = 0
    expected_total = len(expected_hashes)

    while True:
        message = recv_json(sock)
        message_type = message.get("type")
        if message_type == "done":
            return received_count
        if message_type not in {"song", "song_stream"}:
            raise ValueError(f"Unexpected message from peer: {message_type}")

        song_hash = str(message["hash"])
        title = str(message.get("title") or message.get("folder_name") or song_hash[:12])
        zip_size = int(message.get("zip_size") or 0)
        if song_hash not in expected_hashes:
            log(f"Receiving unexpected song '{title}' anyway.")

        temp = tempfile.NamedTemporaryFile(prefix="clone_hero_recv_", suffix=".zip", delete=False)
        temp_path = Path(temp.name)
        temp.close()

        try:
            progress = _log_receive_progress(log, title, zip_size)
            if message_type == "song":
                receive_file(sock, temp_path, zip_size, progress)
            else:
                receive_chunked_file(sock, temp_path, progress)

            destination = unique_destination(library, str(message.get("folder_name") or title))
            extract_song_zip(temp_path, destination)
            received_count += 1
            current = min(received_count, expected_total) if expected_total else received_count
            report_progress("Receiving", current, expected_total or None, title)
            log(f"Imported '{title}' into {destination.name}.")
        finally:
            temp_path.unlink(missing_ok=True)


def _log_megabytes(log: Callable[[str], None], verb: str, title: str) -> Callable[[int], None]:
    last_report = 0.0

    def progress(byte_count: int) -> None:
        nonlocal last_report
        now = time.monotonic()
        if now - last_report >= 1.0:
            log(f"{verb} '{title}': {byte_count / (1024 * 1024):.1f} MB")
            last_report = now

    return progress


def _log_receive_progress(log: Callable[[str], None], title: str, zip_size: int) -> Callable[[int], None]:
    last_report = 0.0

    def progress(bytes_received: int) -> None:
        nonlocal last_report
        now = time.monotonic()
        if now - last_report < 1.0 and bytes_received != zip_size:
            return
        if zip_size:
            percent = bytes_received / zip_size * 100
            log(f"Receiving '{title}': {percent:.0f}%")
        else:
            log(f"Receiving '{title}': {bytes_received / (1024 * 1024):.1f} MB")
        last_report = now

    return progress
