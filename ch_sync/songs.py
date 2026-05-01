from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .constants import CHUNK_SIZE
from .progress import ProgressCallback, noop_progress


@dataclass(frozen=True)
class Song:
    hash: str
    folder: Path
    folder_name: str
    title: str
    identity: str
    size: int
    file_count: int


Manifest = dict[str, dict[str, object]]


def parse_song_metadata(song_ini: Path) -> dict[str, str]:
    metadata: dict[str, str] = {}
    try:
        for line in song_ini.read_text(encoding="utf-8", errors="replace").splitlines():
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip().lower()
            value = " ".join(value.strip().split())
            if key and value:
                metadata[key] = value
    except OSError:
        return {}
    return metadata


def parse_song_title(song_ini: Path) -> str:
    return parse_song_metadata(song_ini).get("name") or song_ini.parent.name


def normalize_identity_part(value: str) -> str:
    return " ".join(value.casefold().split())


def song_identity(folder: Path, metadata: dict[str, str]) -> str:
    parts = [
        metadata.get("name", ""),
        metadata.get("artist", ""),
        metadata.get("album", ""),
        metadata.get("year", ""),
        metadata.get("charter", "") or metadata.get("frets", ""),
    ]
    normalized = [normalize_identity_part(part) for part in parts if normalize_identity_part(part)]
    if normalized:
        return "|".join(normalized)
    return normalize_identity_part(folder.name)


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

    files = (p for p in folder.rglob("*") if p.is_file())
    for file_path in sorted(files, key=lambda p: str(p.relative_to(folder)).lower()):
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


def build_library_state(
    library: Path,
    log: Callable[[str], None],
    progress: ProgressCallback = noop_progress,
) -> tuple[Manifest, dict[str, Song]]:
    library = library.resolve()
    if not library.exists() or not library.is_dir():
        raise ValueError(f"Library path does not exist or is not a folder: {library}")

    song_dirs = find_song_dirs(library)
    log(f"Found {len(song_dirs)} song folders. Hashing files...")
    manifest: Manifest = {}
    song_index: dict[str, Song] = {}

    for position, folder in enumerate(song_dirs, start=1):
        song_hash, size, file_count = hash_song_folder(folder)
        metadata = parse_song_metadata(folder / "song.ini")
        title = metadata.get("name") or folder.name
        identity = song_identity(folder, metadata)
        song = Song(song_hash, folder, folder.name, title, identity, size, file_count)
        manifest.setdefault(
            song_hash,
            {
                "folder_name": folder.name,
                "title": title,
                "identity": identity,
                "size": size,
                "file_count": file_count,
            },
        )
        song_index.setdefault(song_hash, song)
        progress("Hashing", position, len(song_dirs), title)
        if position % 25 == 0:
            log(f"Hashed {position}/{len(song_dirs)} songs...")

    log(f"Indexed {len(song_index)} local unique songs.")
    return manifest, song_index


def build_manifest(library: Path, log: Callable[[str], None]) -> Manifest:
    manifest, _index = build_library_state(library, log)
    return manifest


def manifest_identities(manifest: dict[str, object]) -> set[str]:
    identities: set[str] = set()
    for song_info in manifest.values():
        if isinstance(song_info, dict):
            identity = song_info.get("identity")
            if isinstance(identity, str) and identity:
                identities.add(identity)
    return identities


def missing_hashes_by_hash_or_identity(
    source_manifest: dict[str, object],
    target_hashes: set[str],
    target_identities: set[str],
) -> list[str]:
    missing: list[str] = []
    for song_hash, song_info in source_manifest.items():
        if song_hash in target_hashes:
            continue
        identity = song_info.get("identity") if isinstance(song_info, dict) else None
        if isinstance(identity, str) and identity in target_identities:
            continue
        missing.append(str(song_hash))
    return sorted(missing)
