from __future__ import annotations

import unittest
from contextlib import redirect_stdout
from io import StringIO

from ch_sync.cleanup import apply_actions, build_actions, grouped_duplicates, scan_library

from tests.helpers import make_song, workspace_tempdir


class CleanupTests(unittest.TestCase):
    def test_grouped_duplicates_selects_one_keeper(self) -> None:
        with workspace_tempdir() as root:
            make_song(root, "Artist - Song", name="Song", artist="Artist", chart_text="keeper")
            make_song(root, "Artist - Song (2)", name="Song", artist="Artist", chart_text="duplicate")

            songs = scan_library(root)
            duplicates = grouped_duplicates(songs)

            self.assertEqual(len(duplicates), 1)
            keeper, duplicate_songs = duplicates[0]
            self.assertEqual(keeper.folder.name, "Artist - Song")
            self.assertEqual([song.folder.name for song in duplicate_songs], ["Artist - Song (2)"])

    def test_build_actions_quarantines_duplicates_by_default(self) -> None:
        with workspace_tempdir() as root:
            make_song(root, "Artist - Song", name="Song", artist="Artist")
            make_song(root, "Artist - Song (2)", name="Song", artist="Artist")

            actions = build_actions(root, scan_library(root), "_dupes", False, False)

            self.assertEqual(len(actions), 1)
            self.assertEqual(actions[0].kind, "quarantine")
            self.assertEqual(actions[0].source.name, "Artist - Song (2)")
            self.assertIn("_dupes", actions[0].target.parts)

    def test_build_actions_can_delete_duplicates(self) -> None:
        with workspace_tempdir() as root:
            make_song(root, "Artist - Song", name="Song", artist="Artist")
            make_song(root, "Artist - Song (2)", name="Song", artist="Artist")

            actions = build_actions(root, scan_library(root), "_dupes", False, True)

            self.assertEqual([action.kind for action in actions], ["delete"])

    def test_build_actions_can_rename_kept_folders(self) -> None:
        with workspace_tempdir() as root:
            make_song(root, "Messy Folder", name="Song", artist="Artist")

            actions = build_actions(root, scan_library(root), "_dupes", True, False)

            self.assertEqual(len(actions), 1)
            self.assertEqual(actions[0].kind, "rename")
            self.assertEqual(actions[0].target.name, "Artist - Song")

    def test_apply_actions_moves_quarantine_without_deleting_keeper(self) -> None:
        with workspace_tempdir() as root:
            make_song(root, "Artist - Song", name="Song", artist="Artist")
            duplicate = make_song(root, "Artist - Song (2)", name="Song", artist="Artist")

            actions = build_actions(root, scan_library(root), "_dupes", False, False)
            with redirect_stdout(StringIO()):
                apply_actions(actions)

            self.assertTrue((root / "Artist - Song").exists())
            self.assertFalse(duplicate.exists())
            self.assertTrue(any((root / "_dupes").rglob("song.ini")))

    def test_apply_actions_deletes_duplicate_without_deleting_keeper(self) -> None:
        with workspace_tempdir() as root:
            make_song(root, "Artist - Song", name="Song", artist="Artist")
            duplicate = make_song(root, "Artist - Song (2)", name="Song", artist="Artist")

            actions = build_actions(root, scan_library(root), "_dupes", False, True)
            with redirect_stdout(StringIO()):
                apply_actions(actions)

            self.assertTrue((root / "Artist - Song").exists())
            self.assertFalse(duplicate.exists())
            self.assertFalse((root / "_dupes").exists())


if __name__ == "__main__":
    unittest.main()
