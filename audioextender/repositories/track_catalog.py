"""Compatibility composition for downloaded-track catalog persistence."""

from __future__ import annotations

from audioextender.repositories.recording_families import RecordingFamilyRepositoryMixin
from audioextender.repositories.track_analysis_state import TrackAnalysisStateRepositoryMixin
from audioextender.repositories.track_core import TrackCoreRepositoryMixin
from audioextender.repositories.track_descriptors import TrackDescriptorRepositoryMixin
from audioextender.repositories.track_metadata_state import TrackMetadataStateRepositoryMixin
from audioextender.repositories.track_projections import TrackProjectionRepositoryMixin


class TrackCatalogRepositoryMixin(
    TrackDescriptorRepositoryMixin,
    TrackCoreRepositoryMixin,
    RecordingFamilyRepositoryMixin,
    TrackProjectionRepositoryMixin,
    TrackMetadataStateRepositoryMixin,
    TrackAnalysisStateRepositoryMixin,
):
    """Preserve the historical catalog repository API through focused mixins."""
