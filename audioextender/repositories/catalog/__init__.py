"""Compatibility composition for downloaded-track catalog persistence."""

from __future__ import annotations

from audioextender.repositories.catalog.analysis import TrackAnalysisStateRepositoryMixin
from audioextender.repositories.catalog.core import TrackCoreRepositoryMixin
from audioextender.repositories.catalog.descriptors import TrackDescriptorRepositoryMixin
from audioextender.repositories.catalog.metadata import TrackMetadataStateRepositoryMixin
from audioextender.repositories.catalog.projections import TrackProjectionRepositoryMixin
from audioextender.repositories.catalog.recording_families import RecordingFamilyRepositoryMixin


class TrackCatalogRepositoryMixin(
    TrackDescriptorRepositoryMixin,
    TrackCoreRepositoryMixin,
    RecordingFamilyRepositoryMixin,
    TrackProjectionRepositoryMixin,
    TrackMetadataStateRepositoryMixin,
    TrackAnalysisStateRepositoryMixin,
):
    """Preserve the historical catalog repository API through focused mixins."""
