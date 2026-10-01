from __future__ import annotations

import unittest
from collections.abc import Callable
from unittest.mock import Mock

from audioextender.imports.playlist_match import PlaylistMatchNotFoundError, PlaylistMatchService


class PlaylistMatchServiceTests(unittest.TestCase):
    def test_worker_progress_and_results_share_one_state_store(self) -> None:
        worker = Mock()

        def matcher(tracks: list[dict], progress: Callable[..., None]) -> list[dict]:
            progress(stage="Matching 1 of 1", progress=100, matched=1, total=1)
            return [{**tracks[0], "youtube_url": "https://youtube.com/watch?v=one"}]

        service = PlaylistMatchService(matcher, thread_factory=lambda **_kwargs: worker)
        started = service.start([{"title": "One", "artist": "Artist"}], "Playlist")
        service.run(started["match_id"], [{"title": "One", "artist": "Artist"}])
        state = service.status(started["match_id"])
        self.assertEqual(state["status"], "complete")
        self.assertEqual(state["matched"], 1)
        self.assertEqual(state["results"][0]["youtube_url"], "https://youtube.com/watch?v=one")

    def test_clear_removes_transient_match_state(self) -> None:
        service = PlaylistMatchService(lambda _tracks, _progress: [], thread_factory=lambda **_kwargs: Mock())
        started = service.start([{"title": "One"}], "Playlist")
        service.clear()
        with self.assertRaises(PlaylistMatchNotFoundError):
            service.status(started["match_id"])


if __name__ == "__main__":
    unittest.main()
