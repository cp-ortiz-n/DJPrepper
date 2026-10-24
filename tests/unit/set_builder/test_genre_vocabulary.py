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

    def test_canonical_name_affinity_beats_unrelated_parent_prevalence(self) -> None:
        vocabulary = [
            {"canonical": "House", "aliases": ["Disco"], "count": 500},
            {"canonical": "Disco & Funk", "aliases": ["Disco"], "count": 20},
        ]
        self.assertEqual(explicit_genre_mentions("Disco set", vocabulary), ["disco & funk"])
        self.assertEqual(resolve_catalog_genre("Disco", vocabulary), "disco & funk")

    def test_alias_specific_usage_beats_unrelated_parent_size(self) -> None:
        vocabulary = [
            {
                "canonical": "Hip-Hop & Rap",
                "aliases": ["Afropop"],
                "count": 197,
                "aliasCounts": {"Afropop": 1},
            },
            {
                "canonical": "Afro House",
                "aliases": ["Afropop"],
                "count": 89,
                "aliasCounts": {"Afropop": 3},
            },
            {
                "canonical": "Afro & Amapiano",
                "aliases": ["Afropop"],
                "count": 3,
                "aliasCounts": {"Afropop": 2},
            },
        ]
        self.assertEqual(explicit_genre_mentions("Afropop set", vocabulary), ["afro house"])
        self.assertEqual(resolve_catalog_genre("Afropop", vocabulary), "afro house")

    def test_mixed_set_keeps_catalog_genres_in_written_order(self) -> None:
        vocabulary = [
            {"canonical": "House", "aliases": ["House"], "count": 20},
            {"canonical": "Disco & Funk", "aliases": ["Disco", "Funk"], "count": 12},
            {"canonical": "Hard Techno", "aliases": ["Hard Techno"], "count": 10},
            {"canonical": "Techno", "aliases": ["Techno"], "count": 30},
        ]
        self.assertEqual(
            explicit_genre_mentions("Start with House, move to Disco, finish with Hard Techno", vocabulary),
            ["house", "disco & funk", "hard techno"],
        )


if __name__ == "__main__":
    unittest.main()
