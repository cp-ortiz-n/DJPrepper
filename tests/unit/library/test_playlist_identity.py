from __future__ import annotations

import unittest

from audioextender.library.playlist_identity import (
    catalog_genre_terms,
    playlist_genre_identity_tags,
    playlist_identity_projection,
)


class PlaylistIdentityTests(unittest.TestCase):
    def test_compound_playlist_identity_uses_catalog_vocabulary_without_retagging(self) -> None:
        vocabulary = catalog_genre_terms(
            [
                {"category": "Latin / Reggaeton", "detail_genre": "Neoperreo, Guaracha"},
                {"category": "Electronic / Techno / Techno", "detail_genre": "Bounce, Techno"},
            ]
        )

        tags = playlist_genre_identity_tags(["LATIN_bounce_TECHNO_Rave_Edition"], vocabulary)
        by_value = {tag["value"]: tag for tag in tags}

        self.assertIn("latin techno", by_value)
        self.assertIn("latin bounce techno", by_value)
        self.assertEqual(by_value["latin techno"]["source"], "LATIN_bounce_TECHNO_Rave_Edition")
        self.assertEqual(by_value["latin techno"]["provenance"], "playlist")

    def test_unknown_promotional_words_do_not_become_genre_identity(self) -> None:
        tags = playlist_genre_identity_tags(
            ["Best Summer Workout Hits 2026"],
            ["house", "techno", "reggaeton"],
        )

        self.assertEqual([], tags)

    def test_catalog_identity_matches_reordered_playlist_words_and_conservative_inflections(self) -> None:
        tags = playlist_genre_identity_tags(
            ["💽🌶️Techno_Latino"],
            ["latin", "techno", "latin techno"],
        )

        by_value = {tag["value"]: tag for tag in tags}
        self.assertIn("latin techno", by_value)
        self.assertEqual(by_value["latin techno"]["source"], "💽🌶️Techno_Latino")

    def test_catalog_identity_requires_every_compound_word(self) -> None:
        tags = playlist_genre_identity_tags(
            ["Techno Rave"],
            ["latin techno"],
        )

        self.assertEqual([], tags)

    def test_catalog_identity_does_not_apply_broad_stemming(self) -> None:
        tags = playlist_genre_identity_tags(
            ["Technology Showcase"],
            ["techno"],
        )

        self.assertEqual([], tags)

    def test_projection_ignores_valid_json_that_is_not_a_playlist_list(self) -> None:
        projection = playlist_identity_projection('{"playlist": "Latin Techno"}', ["latin", "techno"])

        self.assertEqual({"playlists": [], "playlist_identity": []}, projection)


if __name__ == "__main__":
    unittest.main()
