from __future__ import annotations

import unittest

from audioextender.set_builder.genre_vocabulary import (
    canonical_genres,
    explicit_genre_mentions,
    normalize_genre_vocabulary,
    resolve_catalog_genre,
)


class GenreVocabularyTests(unittest.TestCase):
    def test_catalog_alias_resolves_without_global_hard_coding(self) -> None:
        vocabulary = [
            {"canonical": "Disco & Funk", "aliases": ["Disco", "Nu Disco"], "count": 42},
            {"canonical": "Techno", "aliases": ["Peak-Time Techno"], "count": 18},
        ]
        self.assertEqual(explicit_genre_mentions("Create a disco set", vocabulary), ["disco & funk"])
        self.assertEqual(resolve_catalog_genre("Nu Disco", vocabulary), "disco & funk")

    def test_vocabulary_is_deduplicated_and_ranked_by_catalog_prevalence(self) -> None:
        result = normalize_genre_vocabulary(
            [
                {"canonical": "House", "aliases": ["Classic House"], "count": 3},
                {"canonical": "house", "aliases": ["Piano House"], "count": 4},
                "Techno",
            ]
        )
        self.assertEqual(result[0]["canonical"], "house")
        self.assertEqual(result[0]["count"], 7)
        self.assertEqual(set(result[0]["aliases"]), {"house", "classic house", "piano house"})
        self.assertEqual(canonical_genres(result), ["house", "techno"])

    def test_legacy_string_vocabulary_still_resolves_exact_names(self) -> None:
        self.assertEqual(
            explicit_genre_mentions("Start Techno, end Latin Techno", ["Techno", "Latin Techno"]),
            [
                "techno",
                "latin techno",
            ],
        )


if __name__ == "__main__":
    unittest.main()
