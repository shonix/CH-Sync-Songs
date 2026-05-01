from __future__ import annotations

import shutil
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


TEST_TMP_ROOT = Path(__file__).resolve().parents[1] / "tests_tmp"


@contextmanager
def workspace_tempdir() -> Iterator[Path]:
    TEST_TMP_ROOT.mkdir(exist_ok=True)
    temp = TEST_TMP_ROOT / f"case_{uuid.uuid4().hex}"
    temp.mkdir()
    try:
        yield temp
    finally:
        if temp.exists():
            shutil.rmtree(temp)


def make_song(
    root: Path,
    folder_name: str,
    *,
    name: str,
    artist: str = "Artist",
    charter: str = "Tester",
    chart_text: str = "notes",
) -> Path:
    folder = root / folder_name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "song.ini").write_text(
        f"name = {name}\nartist = {artist}\ncharter = {charter}\n",
        encoding="utf-8",
    )
    (folder / "notes.chart").write_text(chart_text, encoding="utf-8")
    return folder
