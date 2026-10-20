from __future__ import annotations

import unittest

from audioextender.persistence.catalog import TrackCatalogRepositoryMixin
from audioextender.persistence.catalog.analysis import TrackAnalysisStateRepositoryMixin
from audioextender.persistence.catalog.core import TrackCoreRepositoryMixin
from audioextender.persistence.catalog.descriptors import TrackDescriptorRepositoryMixin
from audioextender.persistence.catalog.metadata import TrackMetadataStateRepositoryMixin
from audioextender.persistence.catalog.projections import TrackProjectionRepositoryMixin
from audioextender.persistence.catalog.recording_families import RecordingFamilyRepositoryMixin

CATALOG_MIXINS = (
    TrackDescriptorRepositoryMixin,
    TrackCoreRepositoryMixin,
    RecordingFamilyRepositoryMixin,
    TrackProjectionRepositoryMixin,
    TrackMetadataStateRepositoryMixin,
    TrackAnalysisStateRepositoryMixin,
)


class TrackCatalogCompositionTests(unittest.TestCase):
    def test_compatibility_mixin_composes_each_catalog_responsibility(self) -> None:
        for mixin in CATALOG_MIXINS:
            with self.subTest(mixin=mixin.__name__):
                self.assertTrue(issubclass(TrackCatalogRepositoryMixin, mixin))

    def test_catalog_responsibility_mixins_do_not_redefine_methods(self) -> None:
        owners: dict[str, str] = {}
        duplicates: dict[str, set[str]] = {}
        for mixin in CATALOG_MIXINS:
            for name, value in mixin.__dict__.items():
                if name.startswith("_") or not callable(value):
                    continue
                if name in owners:
                    duplicates.setdefault(name, {owners[name]}).add(mixin.__name__)
                owners[name] = mixin.__name__
        self.assertEqual({}, duplicates)

    def test_historical_catalog_entry_points_remain_available(self) -> None:
        expected = {
            "upsert_downloaded_track",
            "list_downloaded_tracks",
            "get_downloaded_track",
            "page_downloaded_tracks",
            "downloaded_catalog_facets",
            "track_descriptors",
            "update_track_descriptors",
            "recording_family",
            "link_recording_version",
            "update_downloaded_track_artwork",
            "update_downloaded_track_metadata",
            "update_downloaded_track_key_analysis",
            "update_audio_quality",
            "audio_quality_summary",
            "delete_downloaded_track",
        }
        self.assertEqual([], sorted(name for name in expected if not hasattr(TrackCatalogRepositoryMixin, name)))


if __name__ == "__main__":
    unittest.main()
