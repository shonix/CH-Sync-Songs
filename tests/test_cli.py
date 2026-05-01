from __future__ import annotations

import sys
import unittest
from unittest.mock import patch

from ch_sync import cleanup
from ch_sync import cli


class CliTests(unittest.TestCase):
    def test_sync_no_ui_requires_mode(self) -> None:
        with patch.object(sys, "argv", ["clone_hero_sync.py", "--no-ui", "--library", "songs"]):
            with self.assertRaises(SystemExit) as raised:
                cli.main()

        self.assertIn("Use --host or --connect", str(raised.exception))

    def test_cleanup_delete_requires_apply(self) -> None:
        with patch.object(sys, "argv", ["cleanup_songs.py", "--library", ".", "--delete-duplicates"]):
            with self.assertRaises(SystemExit) as raised:
                cleanup.main()

        self.assertIn("--delete-duplicates requires --apply", str(raised.exception))

    def test_cleanup_default_quarantine_folder_is_cleanup(self) -> None:
        with patch.object(sys, "argv", ["cleanup_songs.py", "--library", "."]):
            args = cleanup.parse_args()

        self.assertEqual(args.quarantine, "cleanup")


if __name__ == "__main__":
    unittest.main()
