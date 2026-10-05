"""Durable musical-identity descriptor delivery for the local track catalog."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from audioextender.library.identity_inference import infer_identity_descriptors


DESCRIPTOR_CATEGORIES = {
    "cultural", "rhythm", "sound", "vocal", "role", "context", "familiarity"
}


class TrackDescriptor(BaseModel):
    category: str = Field(default="context", max_length=40)
    value: str = Field(min_length=1, max_length=120)
    provenance: Literal["manual", "imported", "inferred", "crate"] = "manual"
    confidence: float = Field(default=1.0, ge=0, le=1)

    @field_validator("category")
    @classmethod
    def valid_category(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if normalized not in DESCRIPTOR_CATEGORIES:
            raise ValueError(f"category must be one of: {', '.join(sorted(DESCRIPTOR_CATEGORIES))}")
        return normalized

    @field_validator("value")
    @classmethod
    def normalized_value(cls, value: str) -> str:
        return value.strip().casefold()


class DescriptorUpdateRequest(BaseModel):
    descriptors: list[TrackDescriptor] = Field(default_factory=list, max_length=100)
    mode: Literal["replace", "add", "remove"] = "replace"
    protect_from_inference: bool | None = None


class BulkDescriptorUpdateRequest(DescriptorUpdateRequest):
    track_ids: list[int] = Field(min_length=1, max_length=5000)


class DescriptorInferenceRequest(BaseModel):
    track_ids: list[int] = Field(min_length=1, max_length=5000)
    apply: bool = False


class InferenceProtectionRequest(BaseModel):
    protected: bool


class VocabularyRuleRequest(BaseModel):
    signal: str = Field(min_length=1, max_length=80)
    category: str = Field(default="", max_length=40)
    value: str = Field(default="", max_length=120)
    status: Literal["approved", "ignored"] = "approved"

    @field_validator("category")
    @classmethod
    def valid_optional_category(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if normalized and normalized not in DESCRIPTOR_CATEGORIES:
            raise ValueError(f"category must be one of: {', '.join(sorted(DESCRIPTOR_CATEGORIES))}")
        return normalized


@dataclass(frozen=True)
class DescriptorRouteDependencies:
    repository: Callable[[], Any]
    invalidate_set_catalog: Callable[[], None]


def create_descriptor_router(deps: DescriptorRouteDependencies) -> APIRouter:
    router = APIRouter(prefix="/api/downloaded-library", tags=["track-descriptors"])

    def inference_context(repository: Any, track_id: int) -> dict[str, Any] | None:
        context = repository.track_identity_inference_context(track_id)
        if context is not None:
            context["vocabulary_rules"] = repository.identity_vocabulary_rules(status="approved")
        return context

    @router.get("/tracks/{track_id}/descriptors")
    def descriptors(track_id: int) -> dict[str, Any]:
        repository = deps.repository()
        if not repository.get_downloaded_track(track_id):
            raise HTTPException(404, "Track not found")
        return {"track_id": track_id, "descriptors": repository.track_descriptors(track_id),
                **repository.track_identity_inference_status(track_id)}

    @router.put("/tracks/{track_id}/descriptors")
    def update_descriptors(track_id: int, request: DescriptorUpdateRequest) -> dict[str, Any]:
        repository = deps.repository()
        result = repository.update_track_descriptors(
            [track_id], [item.model_dump() for item in request.descriptors], mode=request.mode
        )
        if result["missing"]:
            raise HTTPException(404, "Track not found")
        protected = request.protect_from_inference
        if protected is None:
            protected = any(item.provenance == "manual" for item in request.descriptors)
        repository.set_track_identity_inference_protection([track_id], protected)
        deps.invalidate_set_catalog()
        return {
            **result,
            "track_id": track_id,
            "values": repository.track_descriptors(track_id),
            **repository.track_identity_inference_status(track_id),
            "requested_action": f"{request.mode.title()} musical identity descriptors",
            "written_to": "AudioExtender track catalog",
        }

    @router.put("/tracks/{track_id}/inference-protection")
    def update_inference_protection(
        track_id: int, request: InferenceProtectionRequest
    ) -> dict[str, Any]:
        repository = deps.repository()
        result = repository.set_track_identity_inference_protection(
            [track_id], request.protected
        )
        if result["missing"]:
            raise HTTPException(404, "Track not found")
        return {
            **result, **repository.track_identity_inference_status(track_id),
            "requested_action": "Protect manual identity from inference"
            if request.protected else "Allow identity re-inference",
            "written_to": "AudioExtender track catalog",
            "survives_restart": True,
        }

    @router.post("/descriptors/bulk")
    def bulk_update_descriptors(request: BulkDescriptorUpdateRequest) -> dict[str, Any]:
        result = deps.repository().update_track_descriptors(
            request.track_ids,
            [item.model_dump() for item in request.descriptors],
            mode=request.mode,
        )
        deps.invalidate_set_catalog()
        return {
            **result,
            "requested_action": f"{request.mode.title()} descriptors on {len(set(request.track_ids))} tracks",
            "written_to": "AudioExtender track catalog",
            "failed": len(result["missing"]),
        }

    @router.get("/tracks/{track_id}/descriptor-suggestions")
    def descriptor_suggestions(track_id: int) -> dict[str, Any]:
        repository = deps.repository()
        context = inference_context(repository, track_id)
        if context is None:
            raise HTTPException(404, "Track not found")
        suggestions = infer_identity_descriptors(context)
        return {
            "track_id": track_id, "suggestions": suggestions,
            "playlists_considered": context.get("playlists", []),
            "applied": False,
        }

    @router.post("/descriptors/infer")
    def infer_descriptors(request: DescriptorInferenceRequest) -> dict[str, Any]:
        repository = deps.repository()
        tracks: list[dict[str, Any]] = []
        missing: list[int] = []
        skipped_protected: list[int] = []
        applied = 0
        for track_id in dict.fromkeys(request.track_ids):
            context = inference_context(repository, track_id)
            if context is None:
                missing.append(track_id)
                continue
            suggestions = infer_identity_descriptors(context)
            if request.apply and suggestions:
                result = repository.replace_inferred_track_descriptors(track_id, suggestions)
                if result.get("skipped_protected"):
                    skipped_protected.append(track_id)
                else:
                    applied += 1
            tracks.append({
                "track_id": track_id, "suggestions": suggestions,
                "playlists_considered": context.get("playlists", []),
            })
        if request.apply:
            deps.invalidate_set_catalog()
        return {
            "requested": len(set(request.track_ids)), "processed": len(tracks),
            "applied": applied, "missing": missing,
            "skipped_protected": skipped_protected, "tracks": tracks,
            "survives_restart": request.apply,
            "written_to": "AudioExtender track catalog" if request.apply else "Preview only",
        }

    @router.post("/descriptors/infer-missing")
    def infer_missing_descriptors() -> dict[str, Any]:
        repository = deps.repository()
        track_ids = repository.track_ids_missing_inferred_identity()
        applied = 0
        suggestions_added = 0
        no_suggestions: list[int] = []
        for track_id in track_ids:
            context = inference_context(repository, track_id)
            suggestions = infer_identity_descriptors(context or {})
            if not suggestions:
                no_suggestions.append(track_id)
            result = repository.replace_inferred_track_descriptors(track_id, suggestions)
            if result.get("skipped_protected"):
                continue
            applied += 1
            suggestions_added += len(suggestions)
        if applied:
            deps.invalidate_set_catalog()
        return {
            "requested": len(track_ids), "processed": len(track_ids), "applied": applied,
            "suggestions_added": suggestions_added, "no_suggestions": no_suggestions,
            "failed": 0, "survives_restart": True,
            "written_to": "AudioExtender track catalog",
            "requested_action": "Infer identity for every track without inferred descriptors",
        }

    @router.post("/descriptors/reinfer-unprotected")
    def reinfer_unprotected_descriptors() -> dict[str, Any]:
        """Refresh machine identity for every track not manually approved by the DJ."""
        repository = deps.repository()
        track_ids = repository.track_ids_available_for_identity_inference()
        updated = 0
        suggestions_added = 0
        no_suggestions: list[int] = []
        for track_id in track_ids:
            context = inference_context(repository, track_id)
            suggestions = infer_identity_descriptors(context or {})
            if not suggestions:
                no_suggestions.append(track_id)
            result = repository.replace_inferred_track_descriptors(track_id, suggestions)
            if not result.get("skipped_protected"):
                updated += 1
                suggestions_added += len(suggestions)
        if updated:
            deps.invalidate_set_catalog()
        return {
            "requested": len(track_ids), "processed": len(track_ids), "updated": updated,
            "suggestions_added": suggestions_added, "no_suggestions": no_suggestions,
            "failed": 0, "survives_restart": True,
            "written_to": "AudioExtender track catalog",
            "requested_action": "Re-infer every track not manually approved",
        }

    @router.get("/descriptors/vocabulary")
    def vocabulary_review() -> dict[str, Any]:
        repository = deps.repository()
        all_items = repository.identity_vocabulary_review()
        # This endpoint is a work queue: approved and ignored decisions remain
        # durable in the rule table but no longer belong in the review list.
        items = [item for item in all_items if not item.get("rule")]
        return {
            "items": items,
            "unreviewed": sum(1 for item in all_items if not item.get("rule")),
            "approved": sum(1 for item in all_items if (item.get("rule") or {}).get("status") == "approved"),
            "ignored": sum(1 for item in all_items if (item.get("rule") or {}).get("status") == "ignored"),
        }

    @router.post("/descriptors/vocabulary")
    def save_vocabulary_rule(request: VocabularyRuleRequest) -> dict[str, Any]:
        if request.status == "approved" and (not request.category or not request.value.strip()):
            raise HTTPException(422, "Approved vocabulary requires a category and normalized value")
        if request.status == "approved" and request.value.strip().casefold() in {
            "context / crate", "context or personal crate", "cultural / regional",
            "rhythmic influence", "sound character", "vocal identity",
            "energy / dj role", "audience familiarity",
        }:
            raise HTTPException(422, "Choose a specific musical meaning, not a field label")
        repository = deps.repository()
        rule = repository.save_identity_vocabulary_rule(
            signal=request.signal, category=request.category, value=request.value,
            status=request.status, source="manual", confidence=1.0,
        )
        affected = repository.track_ids_for_vocabulary_signal(rule["signal"])
        updated = 0
        for track_id in affected:
            context = inference_context(repository, track_id)
            result = repository.replace_inferred_track_descriptors(
                track_id, infer_identity_descriptors(context or {})
            )
            if not result.get("skipped_protected"):
                updated += 1
        if updated:
            deps.invalidate_set_catalog()
        return {
            "rule": rule, "affected_tracks": len(affected), "updated_tracks": updated,
            "requested_action": f"{request.status.title()} identity vocabulary signal",
            "written_to": "AudioExtender identity vocabulary and track catalog",
            "survives_restart": True,
        }

    return router
