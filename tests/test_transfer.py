from __future__ import annotations

import socket
import threading
import unittest
import zipfile

from ch_sync.songs import Song
from ch_sync.transfer import extract_song_zip, receive_chunked_file, recv_json, send_json, stream_song_zip

from tests.helpers import make_song, workspace_tempdir


class TransferTests(unittest.TestCase):
    def test_json_round_trip_over_socket(self) -> None:
        left, right = socket.socketpair()
        try:
            send_json(left, {"type": "manifest", "songs": {"abc": {"title": "Song"}}})

            self.assertEqual(recv_json(right), {"type": "manifest", "songs": {"abc": {"title": "Song"}}})
        finally:
            left.close()
            right.close()

    def test_stream_song_zip_round_trip(self) -> None:
        with workspace_tempdir() as root:
            folder = make_song(root, "Artist - Song", name="Song", artist="Artist")
            song = Song("hash", folder, folder.name, "Song", "song|artist|tester", 0, 2)
            out_zip = root / "received.zip"
            left, right = socket.socketpair()

            try:
                thread = threading.Thread(target=lambda: stream_song_zip(left, song, lambda _n: None))
                thread.start()
                receive_chunked_file(right, out_zip, lambda _n: None)
                thread.join(timeout=5)
                self.assertFalse(thread.is_alive())

                with zipfile.ZipFile(out_zip) as archive:
                    self.assertEqual(sorted(archive.namelist()), ["notes.chart", "song.ini"])
            finally:
                left.close()
                right.close()

    def test_extract_song_zip_rejects_path_traversal(self) -> None:
        with workspace_tempdir() as root:
            zip_path = root / "bad.zip"
            destination = root / "dest"
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr("../outside.txt", "nope")

            with self.assertRaises(ValueError):
                extract_song_zip(zip_path, destination)

            self.assertFalse((root / "outside.txt").exists())
            self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
