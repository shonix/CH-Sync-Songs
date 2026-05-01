#!/usr/bin/env python3
"""
Small Clone Hero song-library sync tool.

Run examples:
  python clone_hero_sync.py --library "D:\\Clone Hero\\Songs"
  python clone_hero_sync.py --no-ui --host --library "D:\\Clone Hero\\Songs" --port 50505
  python clone_hero_sync.py --no-ui --connect 192.168.1.50 --library "D:\\Clone Hero\\Songs"
"""

from ch_sync.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
