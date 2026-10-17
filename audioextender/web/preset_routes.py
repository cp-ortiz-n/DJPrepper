"""Persistent preset state and HTTP routes."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from audioextender.core.presets import EditPreset


class PresetRequest(BaseModel):
    name: str = Field(min_length=1, max_length=40, pattern=r"^[a-z0-9][a-z0-9-]*$")
    intro_bars: int
    outro_bars: int
    use_stems: bool = False
    minimum_loop_quality: float = Field(ge=0, le=100)
    maximum_repetitions: int = Field(ge=1, le=8)


@dataclass(frozen=True)
class PresetRouteDependencies:
    state_path: Callable[[], Path]
    built_in_presets: Mapping[str, EditPreset]
    supported_bar_counts: frozenset[int]


class PresetService:
    """Own custom preset persistence and the effective preset projection."""

    def __init__(self, dependencies: PresetRouteDependencies) -> None:
        self._dependencies = dependencies

    def state(self) -> dict:
        try:
            raw = json.loads(self._dependencies.state_path().read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            raw = {}
        return {
            "definitions": dict(raw.get("definitions") or {}),
            "hidden": list(raw.get("hidden") or []),
        }

    def save_state(self, state: dict) -> None:
        destination = self._dependencies.state_path()
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(destination)

    def available(self) -> dict[str, EditPreset]:
        state = self.state()
        available = dict(self._dependencies.built_in_presets)
        for name, values in state["definitions"].items():
            try:
                available[name] = EditPreset(**values)
            except (TypeError, ValueError):
                continue
        for name in state["hidden"]:
            available.pop(name, None)
        return available

    def payload(self) -> list[dict]:
        state = self.state()
        return [
            {
                "name": name,
                **preset.__dict__,
                "built_in": name in self._dependencies.built_in_presets,
                "modified": name in state["definitions"],
            }
            for name, preset in self.available().items()
        ]

    def snapshot(self, name: str) -> dict:
        preset = self.available().get(name)
        return {"preset_definition": preset.__dict__} if preset is not None else {}

    def save(self, current_name: str, request: PresetRequest) -> list[dict]:
        if (
            request.intro_bars not in self._dependencies.supported_bar_counts
            or request.outro_bars not in self._dependencies.supported_bar_counts
        ):
            raise HTTPException(400, "Unsupported bar count")
        state = self.state()
        if current_name != request.name and request.name in self.available():
            raise HTTPException(409, "A preset with that name already exists")
        if current_name != request.name:
            state["definitions"].pop(current_name, None)
            if current_name in self._dependencies.built_in_presets and current_name not in state["hidden"]:
                state["hidden"].append(current_name)
        state["hidden"] = [name for name in state["hidden"] if name != request.name]
        state["definitions"][request.name] = {
            key: value for key, value in request.model_dump().items() if key != "name"
        }
        self.save_state(state)
        return self.payload()

    def delete(self, name: str) -> list[dict]:
        if name not in self.available():
            raise HTTPException(404, "Preset not found")
        state = self.state()
        state["definitions"].pop(name, None)
        if name in self._dependencies.built_in_presets and name not in state["hidden"]:
            state["hidden"].append(name)
        self.save_state(state)
        return self.payload()

    def restore(self) -> list[dict]:
        self.save_state({"definitions": {}, "hidden": []})
        return self.payload()


def create_preset_router(service: PresetService) -> APIRouter:
    router = APIRouter()

    @router.get("/api/presets")
    def list_presets() -> dict:
        return {"presets": service.payload()}

    @router.put("/api/presets/{current_name}")
    def save_preset(current_name: str, request: PresetRequest) -> dict:
        return {"presets": service.save(current_name, request)}

    @router.delete("/api/presets/{name}")
    def delete_preset(name: str) -> dict:
        return {"presets": service.delete(name)}

    @router.post("/api/presets/restore")
    def restore_presets() -> dict:
        return {"presets": service.restore()}

    return router
