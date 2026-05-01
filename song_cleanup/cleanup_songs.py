#!/usr/bin/env python3
"""
Clone Hero song-library cleanup helper.

Examples:
  python song_cleanup/cleanup_songs.py --library "D:\\Clone Hero\\Songs"
  python song_cleanup/cleanup_songs.py --library "D:\\Clone Hero\\Songs" --apply
  python song_cleanup/cleanup_songs.py --library "D:\\Clone Hero\\Songs" --apply --delete-duplicates
  python song_cleanup/cleanup_songs.py --library "D:\\Clone Hero\\Songs" --apply --rename-folders
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ch_sync.cleanup import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
