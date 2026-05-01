# Clone Hero Sync Songs

A small Python toolset for syncing and cleaning up Clone Hero song libraries.

The project has two user-facing tools:

- `clone_hero_sync.py` starts the sync app.
- `song_cleanup/cleanup_songs.py` scans a song library for duplicates and folder cleanup.

No third-party Python packages are required.

## Features

- Sync Clone Hero song folders with a friend over TCP.
- GUI mode with progress bar.
- Terminal mode for host/join workflows.
- Streams requested songs one by one instead of prebuilding all transfers.
- Skips likely duplicates by comparing normalized `song.ini` metadata.
- Cleanup tool for duplicate detection, quarantine, deletion, and folder renaming.
- Unit and integration-style tests using Python's built-in `unittest`.

## Requirements

- Python 3.11 or newer recommended.
- Tkinter is needed for GUI mode. Most standard Windows Python installs include it.
- Both users must be able to connect over the network on the selected TCP port.

## Run The Sync App

From the project root:

```powershell
python .\clone_hero_sync.py
```

Choose your Clone Hero songs folder, then either:

- `Host`: wait for a friend to connect.
- `Join`: enter your friend's IP address and connect.

## Terminal Sync

Host:

```powershell
python .\clone_hero_sync.py --no-ui --host --library "PATH\TO\YOUR\SONGS"
```

Join:

```powershell
python .\clone_hero_sync.py --no-ui --connect FRIEND_IP --library "PATH\TO\YOUR\SONGS"
```

Optional custom port:

```powershell
python .\clone_hero_sync.py --no-ui --host --library "PATH\TO\YOUR\SONGS" --port 50505
```

## Cleanup Tool

Always run a dry run first:

```powershell
python .\song_cleanup\cleanup_songs.py --library "PATH\TO\YOUR\SONGS"
```

Move duplicate folders into a cleanup folder inside the selected song library:

```powershell
python .\song_cleanup\cleanup_songs.py --library "PATH\TO\YOUR\SONGS" --apply
```

Duplicates are moved to:

```text
PATH\TO\YOUR\SONGS\cleanup\YYYYMMDD_HHMMSS\
```

Permanently delete duplicate folders:

```powershell
python .\song_cleanup\cleanup_songs.py --library "PATH\TO\YOUR\SONGS" --apply --delete-duplicates
```

Rename kept folders to `Artist - Title`:

```powershell
python .\song_cleanup\cleanup_songs.py --library "PATH\TO\YOUR\SONGS" --apply --rename-folders
```

## Tests

Run all tests:

```powershell
python -B -m unittest discover -s tests
```

The `-B` flag avoids writing Python cache files while testing.

The tests cover:

- Song metadata parsing and identity matching.
- Song folder discovery and manifest building.
- Duplicate cleanup planning and apply behavior.
- Socket JSON framing.
- Streamed zip transfer.
- Unsafe zip path rejection.
- CLI safety checks.

## Project Layout

```text
clone_hero_sync.py              Sync entrypoint
ch_sync/
  cli.py                        Sync CLI parsing
  ui.py                         Tkinter UI
  sync.py                       Sync workflow
  transfer.py                   Socket protocol and zip streaming
  songs.py                      Song scanning, metadata, hashing, identity
  cleanup.py                    Cleanup planning and apply logic
  progress.py                   Progress/log helpers
  constants.py                  Shared constants
song_cleanup/
  cleanup_songs.py              Cleanup entrypoint
  README.md                     Cleanup-specific docs
tests/
  README.md                     Test docs
```

## Security Notes

This is intended for trusted LAN use with a friend.

- Sync traffic is not encrypted.
- There is no authentication/passcode yet.
- Do not expose the host port to the public internet.
- Review cleanup dry-run output before using `--apply`.
- Prefer quarantine mode over `--delete-duplicates` unless you are sure.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
