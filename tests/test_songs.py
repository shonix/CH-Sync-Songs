from __future__ import annotations

import unittest
from pathlib import Path

from ch_sync.songs import (
    build_library_state,
    find_song_dirs,
    manifest_identities,
    missing_hashes_by_hash_or_identity,
    parse_song_metadata,
    safe_folder_name,
    song_identity,
    unique_destination,
)

from tests.helpers import make_song, workspace_tempdir


class SongTests(unittest.TestCase):
    def test_metadata_parsing_normalizes_keys_and_spacing(self) -> None:
        with workspace_tempdir() as temp:
            song_ini = temp / "song.ini"
            song_ini.write_text(" Name =  My   Song  \nARTIST= The  Band\nbad line\n", encoding="utf-8")

            self.assertEqual(parse_song_metadata(song_ini), {"name": "My Song", "artist": "The Band"})

    def test_identity_uses_normalized_metadata(self) -> None:
        folder = Path("Some Folder")
        identity = song_identity(folder, {"name": " My   Song ", "artist": "THE Band", "charter": " Tester "})

        self.assertEqual(identity, "my song|the band|tester")

    def test_find_song_dirs_does_not_descend_inside_song_folder(self) -> None:
        with workspace_tempdir() as root:
            make_song(root, "Outer", name="Outer")
            make_song(root / "Outer", "Nested", name="Nested")
            make_song(root, "Other", name="Other")

            self.assertEqual([path.name for path in find_song_dirs(root)], ["Other", "Outer"])

    def test_build_library_state_returns_manifest_and_index(self) -> None:
        with workspace_tempdir() as root:
            make_song(root, "Artist - Song", name="Song", artist="Artist")

            logs: list[str] = []
            progress: list[tuple[str, int, int | None, str]] = []
            manifest, index = build_library_state(root, logs.append, lambda *event: progress.append(event))

            self.assertEqual(len(manifest), 1)
            self.assertEqual(len(index), 1)
            song = next(iter(index.values()))
            self.assertEqual(song.title, "Song")
            self.assertEqual(song.identity, "song|artist|tester")
            self.assertEqual(progress[0], ("Hashing", 1, 1, "Song"))

    def test_missing_hashes_skip_matching_identity(self) -> None:
        local = {"h1": {"identity": "song|artist"}}
        peer = {
            "h2": {"identity": "song|artist"},
            "h3": {"identity": "other|artist"},
            "h4": {},
        }

        missing = missing_hashes_by_hash_or_identity(peer, set(local), manifest_identities(local))

        self.assertEqual(missing, ["h3", "h4"])

    def test_safe_and_unique_folder_names(self) -> None:
        with workspace_tempdir() as root:
            (root / "Bad_Name").mkdir()

            self.assertEqual(safe_folder_name('Bad:/Name.'), "Bad__Name")
            self.assertEqual(unique_destination(root, "Bad_Name"), root / "Bad_Name (2)")


if __name__ == "__main__":
    unittest.main()
