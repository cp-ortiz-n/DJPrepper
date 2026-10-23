"""Compatibility composition for downloaded-track catalog persistence."""

from __future__ import annotations

from audioextender.persistence.catalog.analysis import TrackAnalysisStateRepositoryMixin
from audioextender.persistence.catalog.core import TrackCoreRepositoryMixin
from audioextender.persistence.catalog.descriptors import TrackDescriptorRepositoryMixin
from audioextender.persistence.catalog.external_ratings import ExternalTrackRatingRepositoryMixin
from audioextender.persistence.catalog.metadata import TrackMetadataStateRepositoryMixin
from audioextender.persistence.catalog.projections import TrackProjectionRepositoryMixin
from audioextender.persistence.catalog.recording_families import RecordingFamilyRepositoryMixin


class TrackCatalogRepositoryMixin(
    TrackDescriptorRepositoryMixin,
    ExternalTrackRatingRepositoryMixin,
    TrackCoreRepositoryMixin,
    RecordingFamilyRepositoryMixin,
    TrackProjectionRepositoryMixin,
    TrackMetadataStateRepositoryMixin,
    TrackAnalysisStateRepositoryMixin,
):
    """Preserve the historical catalog repository API through focused mixins."""
