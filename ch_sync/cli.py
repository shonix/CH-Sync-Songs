from __future__ import annotations

import argparse
from pathlib import Path

from .constants import DEFAULT_PORT
from .progress import log_print, progress_print
from .sync import sync_library
from .ui import run_ui


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync Clone Hero song folders with a friend over TCP.")
    parser.add_argument("--library", "-l", default="", help="Path to your Clone Hero Songs library.")
    parser.add_argument("--port", "-p", type=int, default=DEFAULT_PORT, help=f"TCP port to use. Default: {DEFAULT_PORT}")
    parser.add_argument("--no-ui", action="store_true", help="Run in terminal mode instead of opening the UI.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--host", action="store_true", help="Wait for a friend to connect.")
    group.add_argument("--connect", metavar="IP_OR_HOST", help="Connect to a friend's hosted sync.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.no_ui:
        if not args.library:
            raise SystemExit("--library is required when using --no-ui")
        if args.host:
            mode = "host"
            host = ""
        elif args.connect:
            mode = "join"
            host = args.connect
        else:
            raise SystemExit("Use --host or --connect with --no-ui")
        sync_library(Path(args.library).expanduser(), mode, host, args.port, log_print, progress_print)
        return 0

    run_ui(args.library, args.port)
    return 0
