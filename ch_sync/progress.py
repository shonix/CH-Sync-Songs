from __future__ import annotations

from typing import Callable


ProgressCallback = Callable[[str, int, int | None, str], None]


def log_print(message: str) -> None:
    print(message, flush=True)


def noop_progress(_phase: str, _current: int, _total: int | None, _detail: str) -> None:
    return


def progress_print(phase: str, current: int, total: int | None, detail: str) -> None:
    if not total:
        log_print(f"{phase}: {detail}")
        return

    width = 28
    complete = min(width, int(width * current / total))
    bar = "#" * complete + "-" * (width - complete)
    print(f"\r{phase}: [{bar}] {current}/{total} {detail[:60]:60}", end="", flush=True)
    if current >= total:
        print(flush=True)
