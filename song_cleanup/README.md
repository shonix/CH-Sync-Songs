# Clone Hero Song Cleanup

This helper scans a Clone Hero song library for duplicate folders and optional folder-name cleanup.

It is conservative by default:

- Dry run unless `--apply` is passed.
- Duplicate folders are moved to a quarantine folder, not deleted.
- Permanent duplicate deletion is opt-in with `--delete-duplicates`.
- Folder renaming is opt-in with `--rename-folders`.

## Dry Run

```powershell
python .\song_cleanup\cleanup_songs.py --library "D:\Clone Hero\Songs"
```

## Quarantine Duplicates

```powershell
python .\song_cleanup\cleanup_songs.py --library "D:\Clone Hero\Songs" --apply
```

Duplicates are moved into:

```text
D:\Clone Hero\Songs\_cleanup_duplicates\YYYYMMDD_HHMMSS\
```

## Delete Duplicates

Run a dry run first without delete:

```powershell
python .\song_cleanup\cleanup_songs.py --library "D:\Clone Hero\Songs"
```

Then permanently delete the duplicate folders:

```powershell
python .\song_cleanup\cleanup_songs.py --library "D:\Clone Hero\Songs" --apply --delete-duplicates
```

This removes duplicate folders from disk. Use quarantine mode if you want an easy restore path.

## Quarantine Duplicates And Rename Kept Folders

```powershell
python .\song_cleanup\cleanup_songs.py --library "D:\Clone Hero\Songs" --apply --rename-folders
```

Kept folders are renamed to:

```text
Artist - Title
```

When no artist exists in `song.ini`, the folder is renamed to just the song title.

## How Duplicates Are Detected

Songs are grouped by normalized `song.ini` metadata:

- `name`
- `artist`
- `album`
- `year`
- `charter` or `frets`

The tool keeps one folder from each group and quarantines the rest. The keeper is chosen by preferring folders without duplicate-style suffixes like `(2)`, then by larger file count and size.
