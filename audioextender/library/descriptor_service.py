"""Application service for durable musical-identity descriptor workflows."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from audioextender.library.identity_inference import infer_identity_descriptors


class DescriptorTrackNotFound(LookupError):
    """Raised when a descriptor command targets an unknown catalog track."""


class InvalidVocabularyRule(ValueError):
    """Raised when a vocabulary decision has no usable musical meaning."""


@dataclass(frozen=True)
class DescriptorService:
    repository: Callable[[], Any]
    invalidate_set_catalog: Callable[[], Any]

    def _context(self, repository: Any, track_id: int) -> dict[str, Any] | None:
        context = repository.track_identity_inference_context(track_id)
        if context is not None:
            context["vocabulary_rules"] = repository.identity_vocabulary_rules(status="approved")
        return context

    def get(self, track_id: int) -> dict[str, Any]:
        repository = self.repository()
        if not repository.get_downloaded_track(track_id):
            raise DescriptorTrackNotFound(track_id)
        return {
            "track_id": track_id,
            "descriptors": repository.track_descriptors(track_id),
            **repository.track_identity_inference_status(track_id),
        }

    def update(
        self,
        track_id: int,
        descriptors: list[dict[str, Any]],
        *,
        mode: str,
        protect_from_inference: bool | None,
    ) -> dict[str, Any]:
        repository = self.repository()
        result = repository.update_track_descriptors([track_id], descriptors, mode=mode)
        if result["missing"]:
            raise DescriptorTrackNotFound(track_id)
        protected = protect_from_inference
        if protected is None:
            protected = any(item.get("provenance") == "manual" for item in descriptors)
        repository.set_track_identity_inference_protection([track_id], protected)
        self.invalidate_set_catalog()
        return {
            **result,
            "track_id": track_id,
            "values": repository.track_descriptors(track_id),
            **repository.track_identity_inference_status(track_id),
            "requested_action": f"{mode.title()} musical identity descriptors",
            "written_to": "AudioExtender track catalog",
        }

    def set_protection(self, track_id: int, protected: bool) -> dict[str, Any]:
        repository = self.repository()
        result = repository.set_track_identity_inference_protection([track_id], protected)
        if result["missing"]:
            raise DescriptorTrackNotFound(track_id)
        return {
            **result,
            **repository.track_identity_inference_status(track_id),
            "requested_action": (
                "Protect manual identity from inference" if protected else "Allow identity re-inference"
            ),
            "written_to": "AudioExtender track catalog",
            "survives_restart": True,
        }

    def bulk_update(self, track_ids: list[int], descriptors: list[dict[str, Any]], *, mode: str) -> dict[str, Any]:
        result = self.repository().update_track_descriptors(track_ids, descriptors, mode=mode)
        self.invalidate_set_catalog()
        return {
            **result,
            "requested_action": f"{mode.title()} descriptors on {len(set(track_ids))} tracks",
            "written_to": "AudioExtender track catalog",
            "failed": len(result["missing"]),
        }

    def suggestions(self, track_id: int) -> dict[str, Any]:
        context = self._context(self.repository(), track_id)
        if context is None:
            raise DescriptorTrackNotFound(track_id)
        return {
            "track_id": track_id,
            "suggestions": infer_identity_descriptors(context),
            "playlists_considered": context.get("playlists", []),
            "applied": False,
        }

    def infer(self, track_ids: list[int], *, apply: bool) -> dict[str, Any]:
        repository = self.repository()
        tracks: list[dict[str, Any]] = []
        missing: list[int] = []
        skipped_protected: list[int] = []
        applied = 0
        for track_id in dict.fromkeys(track_ids):
            context = self._context(repository, track_id)
            if context is None:
                missing.append(track_id)
                continue
            suggestions = infer_identity_descriptors(context)
            if apply and suggestions:
                result = repository.replace_inferred_track_descriptors(track_id, suggestions)
                if result.get("skipped_protected"):
                    skipped_protected.append(track_id)
                else:
                    applied += 1
            tracks.append(
                {
                    "track_id": track_id,
                    "suggestions": suggestions,
                    "playlists_considered": context.get("playlists", []),
                }
            )
        if apply:
            self.invalidate_set_catalog()
        return {
            "requested": len(set(track_ids)),
            "processed": len(tracks),
            "applied": applied,
            "missing": missing,
            "skipped_protected": skipped_protected,
            "tracks": tracks,
            "survives_restart": apply,
            "written_to": "AudioExtender track catalog" if apply else "Preview only",
        }

    def infer_missing(self) -> dict[str, Any]:
        return self._infer_catalog(
            self.repository().track_ids_missing_inferred_identity(),
            action="Infer identity for every track without inferred descriptors",
            result_key="applied",
        )

    def reinfer_unprotected(self) -> dict[str, Any]:
        return self._infer_catalog(
            self.repository().track_ids_available_for_identity_inference(),
            action="Re-infer every track not manually approved",
            result_key="updated",
        )

    def _infer_catalog(self, track_ids: list[int], *, action: str, result_key: str) -> dict[str, Any]:
        repository = self.repository()
        updated = 0
        suggestions_added = 0
        no_suggestions: list[int] = []
        for track_id in track_ids:
            suggestions = infer_identity_descriptors(self._context(repository, track_id) or {})
            if not suggestions:
                no_suggestions.append(track_id)
            result = repository.replace_inferred_track_descriptors(track_id, suggestions)
            if not result.get("skipped_protected"):
                updated += 1
                suggestions_added += len(suggestions)
        if updated:
            self.invalidate_set_catalog()
        return {
            "requested": len(track_ids),
            "processed": len(track_ids),
            result_key: updated,
            "suggestions_added": suggestions_added,
            "no_suggestions": no_suggestions,
            "failed": 0,
            "survives_restart": True,
            "written_to": "AudioExtender track catalog",
            "requested_action": action,
        }

    def vocabulary_review(self) -> dict[str, Any]:
        all_items = self.repository().identity_vocabulary_review()
        return {
            "items": [item for item in all_items if not item.get("rule")],
            "unreviewed": sum(1 for item in all_items if not item.get("rule")),
            "approved": sum(1 for item in all_items if (item.get("rule") or {}).get("status") == "approved"),
            "ignored": sum(1 for item in all_items if (item.get("rule") or {}).get("status") == "ignored"),
        }

    def save_vocabulary_rule(self, *, signal: str, category: str, value: str, status: str) -> dict[str, Any]:
        normalized_value = value.strip().casefold()
        field_labels = {
            "context / crate",
            "context or personal crate",
            "cultural / regional",
            "rhythmic influence",
            "sound character",
            "vocal identity",
            "energy / dj role",
            "audience familiarity",
        }
        if status == "approved" and (not category or not normalized_value):
            raise InvalidVocabularyRule("Approved vocabulary requires a category and normalized value")
        if status == "approved" and normalized_value in field_labels:
            raise InvalidVocabularyRule("Choose a specific musical meaning, not a field label")
        repository = self.repository()
        rule = repository.save_identity_vocabulary_rule(
            signal=signal,
            category=category,
            value=value,
            status=status,
            source="manual",
            confidence=1.0,
        )
        affected = repository.track_ids_for_vocabulary_signal(rule["signal"])
        updated = 0
        for track_id in affected:
            result = repository.replace_inferred_track_descriptors(
                track_id,
                infer_identity_descriptors(self._context(repository, track_id) or {}),
            )
            if not result.get("skipped_protected"):
                updated += 1
        if updated:
            self.invalidate_set_catalog()
        return {
            "rule": rule,
            "affected_tracks": len(affected),
            "updated_tracks": updated,
            "requested_action": f"{status.title()} identity vocabulary signal",
            "written_to": "AudioExtender identity vocabulary and track catalog",
            "survives_restart": True,
        }
