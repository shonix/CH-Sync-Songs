from __future__ import annotations

import socket
import threading
from pathlib import Path
from typing import Callable

from .progress import ProgressCallback, noop_progress
from .songs import build_library_state, manifest_identities, missing_hashes_by_hash_or_identity
from .transfer import receive_requested_songs, recv_json, send_json, send_requested_songs


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


def sync_library(
    library: Path,
    mode: str,
    host: str,
    port: int,
    log: Callable[[str], None],
    progress: ProgressCallback = noop_progress,
) -> None:
    library = library.resolve()
    local_manifest, local_index = build_library_state(library, log, progress)

    with (connect_as_host(port, log) if mode == "host" else connect_as_client(host, port, log)) as sock:
        sock.settimeout(None)
        send_json(sock, {"type": "manifest", "songs": local_manifest})
        peer_message = recv_json(sock)
        if peer_message.get("type") != "manifest":
            raise ValueError("Peer did not send a manifest.")

        peer_manifest = dict(peer_message["songs"])
        local_hashes = set(local_manifest)
        peer_hashes = set(peer_manifest)
        local_identities = manifest_identities(local_manifest)
        peer_identities = manifest_identities(peer_manifest)
        needed_from_peer = missing_hashes_by_hash_or_identity(peer_manifest, local_hashes, local_identities)
        peer_needs = missing_hashes_by_hash_or_identity(local_manifest, peer_hashes, peer_identities)
        skipped_from_peer = len(peer_hashes - local_hashes) - len(needed_from_peer)
        skipped_for_peer = len(local_hashes - peer_hashes) - len(peer_needs)

        log(f"You are missing {len(needed_from_peer)} songs. Peer is missing {len(peer_needs)} songs.")
        if skipped_from_peer or skipped_for_peer:
            log(f"Skipped {skipped_from_peer} peer songs and {skipped_for_peer} local songs that matched existing song metadata.")

        send_json(sock, {"type": "request", "hashes": needed_from_peer})
        request_message = recv_json(sock)
        if request_message.get("type") != "request":
            raise ValueError("Peer did not send a request list.")
        requested_by_peer = [str(h) for h in request_message["hashes"]]

        sender_error: list[BaseException] = []

        def sender() -> None:
            try:
                send_requested_songs(sock, requested_by_peer, local_index, log, progress)
            except BaseException as exc:  # noqa: BLE001 - surfaced to caller after receiver exits.
                sender_error.append(exc)

        thread = threading.Thread(target=sender, daemon=True)
        thread.start()
        received = receive_requested_songs(sock, library, set(needed_from_peer), log, progress)
        thread.join()
        if sender_error:
            raise sender_error[0]

    log(f"Sync complete. Imported {received} songs.")
