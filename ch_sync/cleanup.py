from __future__ import annotations

import argparse
import shutil
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .songs import find_song_dirs, hash_song_folder, parse_song_metadata, safe_folder_name, song_identity


@dataclass(frozen=True)
class CleanupSong:
    folder: Path
    title: str
    artist: str
    identity: str
    content_hash: str
    size: int
    file_count: int


@dataclass(frozen=True)
class CleanupAction:
    kind: str
    source: Path
    target: Path
    reason: str


def scan_library(library: Path) -> list[CleanupSong]:
    songs: list[CleanupSong] = []
    song_dirs = find_song_dirs(library)
    for position, folder in enumerate(song_dirs, start=1):
        metadata = parse_song_metadata(folder / "song.ini")
        content_hash, size, file_count = hash_song_folder(folder)
        title = metadata.get("name") or folder.name
        artist = metadata.get("artist") or ""
        songs.append(CleanupSong(folder, title, artist, song_identity(folder, metadata), content_hash, size, file_count))
        if position % 25 == 0:
            print(f"Scanned {position}/{len(song_dirs)} songs...", flush=True)
    return songs


def preferred_song(group: list[CleanupSong]) -> CleanupSong:
    def score(song: CleanupSong) -> tuple[int, int, int, int, str]:
        duplicate_suffix_penalty = 0 if " (" not in song.folder.name else -1
        root_depth_bonus = -len(song.folder.relative_to(song.folder.anchor).parts)
        return (duplicate_suffix_penalty, song.file_count, song.size, root_depth_bonus, song.folder.name.casefold())

    return max(group, key=score)


def grouped_duplicates(songs: list[CleanupSong]) -> list[tuple[CleanupSong, list[CleanupSong]]]:
    by_identity: dict[str, list[CleanupSong]] = defaultdict(list)
    for song in songs:
        by_identity[song.identity].append(song)

    duplicates: list[tuple[CleanupSong, list[CleanupSong]]] = []
    for group in by_identity.values():
        if len(group) >= 2:
            keeper = preferred_song(group)
            duplicates.append((keeper, [song for song in group if song != keeper]))
    return duplicates


def desired_folder_name(song: CleanupSong) -> str:
    if song.artist:
        return safe_folder_name(f"{song.artist} - {song.title}")
    return safe_folder_name(song.title)


def unique_target(base: Path) -> Path:
    candidate = base
    counter = 2
    while candidate.exists():
        candidate = base.with_name(f"{base.name} ({counter})")
        counter += 1
    return candidate


def build_actions(
    library: Path,
    songs: list[CleanupSong],
    quarantine_name: str,
    rename_folders: bool,
    delete_duplicates: bool,
) -> list[CleanupAction]:
    actions: list[CleanupAction] = []
    quarantine = library / quarantine_name / datetime.now().strftime("%Y%m%d_%H%M%S")

    duplicate_folders: set[Path] = set()
    for keeper, duplicates in grouped_duplicates(songs):
        for duplicate in duplicates:
            duplicate_folders.add(duplicate.folder)
            actions.append(
                CleanupAction(
                    kind="delete" if delete_duplicates else "quarantine",
                    source=duplicate.folder,
                    target=unique_target(quarantine / duplicate.folder.name),
                    reason=f"Duplicate of '{keeper.folder.name}' by song.ini identity",
                )
            )

    if rename_folders:
        for song in songs:
            if song.folder in duplicate_folders:
                continue
            target = unique_target(song.folder.with_name(desired_folder_name(song)))
            if target != song.folder:
                actions.append(CleanupAction("rename", song.folder, target, "Normalize folder to Artist - Title"))

    return actions


def apply_actions(actions: list[CleanupAction]) -> None:
    for action in actions:
        if action.kind == "delete":
            print(f"delete: {action.source}")
            shutil.rmtree(action.source)
            continue
        action.target.parent.mkdir(parents=True, exist_ok=True)
        print(f"{action.kind}: {action.source} -> {action.target}")
        shutil.move(str(action.source), str(action.target))


def print_report(songs: list[CleanupSong], actions: list[CleanupAction], apply: bool) -> None:
    duplicate_actions = [action for action in actions if action.kind == "quarantine"]
    delete_actions = [action for action in actions if action.kind == "delete"]
    rename_actions = [action for action in actions if action.kind == "rename"]

    print(f"Songs scanned: {len(songs)}")
    print(f"Duplicate folders to quarantine: {len(duplicate_actions)}")
    print(f"Duplicate folders to delete: {len(delete_actions)}")
    print(f"Folders to rename: {len(rename_actions)}")
    print(f"Mode: {'APPLY' if apply else 'DRY RUN'}")

    if not actions:
        print("No cleanup actions needed.")
        return

    print("")
    for action in actions:
        if action.kind == "delete":
            print(f"[delete] {action.source}")
        else:
            print(f"[{action.kind}] {action.source} -> {action.target}")
        print(f"  {action.reason}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Find Clone Hero duplicate song folders and optional folder-name cleanup.")
    parser.add_argument("--library", "-l", required=True, help="Path to your Clone Hero Songs library.")
    parser.add_argument("--apply", action="store_true", help="Actually move folders. Without this, only prints a dry-run plan.")
    parser.add_argument("--delete-duplicates", action="store_true", help="Permanently delete duplicate folders instead of moving them to quarantine. Requires --apply.")
    parser.add_argument("--rename-folders", action="store_true", help="Also rename kept song folders to 'Artist - Title'.")
    parser.add_argument("--quarantine", default="_cleanup_duplicates", help="Folder under the library where duplicates are moved.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    library = Path(args.library).expanduser().resolve()
    if not library.exists() or not library.is_dir():
        raise SystemExit(f"Library path does not exist or is not a folder: {library}")
    if args.delete_duplicates and not args.apply:
        raise SystemExit("--delete-duplicates requires --apply. Run without --apply first to review the dry-run plan.")

    songs = scan_library(library)
    actions = build_actions(library, songs, args.quarantine, args.rename_folders, args.delete_duplicates)
    print_report(songs, actions, args.apply)
    if args.apply and actions:
        print("")
        apply_actions(actions)
    return 0
