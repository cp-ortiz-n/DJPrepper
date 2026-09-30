"""Web configuration layers: defaults, persisted settings, and named presets."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, Field

from helpers.presets import PRESETS, EditPreset
from settings import (
    DEFAULT_AUTO_BAR_SELECTION,
    DEFAULT_CANDIDATE_COUNT,
    DEFAULT_EXPORT_CUES,
    DEFAULT_INTRO_BARS,
    DEFAULT_MINIMUM_INTRO_LOOP_QUALITY,
    DEFAULT_MINIMUM_OUTRO_LOOP_QUALITY,
    DEFAULT_OUTRO_BARS,
    DEFAULT_PCM_BITS,
    DEFAULT_PRESET,
    DEFAULT_PREVIEW_SECONDS,
    DEFAULT_USE_STEMS,
    INTRO_SEARCH_SECONDS,
    MAXIMUM_BASS_RESET_RISK,
    MAXIMUM_BUILDUP_RISK,
    MAXIMUM_VOCAL_BOUNDARY_RISK,
    MAXIMUM_VOCAL_COVERAGE,
    MINIMUM_CROSSFADE_MS,
    MINIMUM_STEM_CONSTRUCTION_RELIABILITY,
    OUTRO_SEARCH_SECONDS,
    SUPPORTED_BAR_COUNTS,
)

DEFAULT_WEB_LIBRARY_PATH = str(Path.home() / "Music" / "AudioExtender Library")


class SettingsRepository(Protocol):
    def get_settings(self) -> dict[str, Any]: ...
    def replace_settings(self, values: dict[str, Any]) -> None: ...
    def get_system_state(self, key: str) -> str | None: ...
    def set_system_state(self, key: str, value: str) -> None: ...


def web_defaults(default_library: str) -> dict[str, Any]:
    return {
        "music_library_path": default_library,
        "preset": DEFAULT_PRESET or "auto",
        "intro_bars": DEFAULT_INTRO_BARS,
        "outro_bars": DEFAULT_OUTRO_BARS,
        "use_stems": DEFAULT_USE_STEMS,
        "auto_bars": DEFAULT_AUTO_BAR_SELECTION,
        "minimum_intro_loop_quality": DEFAULT_MINIMUM_INTRO_LOOP_QUALITY,
        "minimum_outro_loop_quality": DEFAULT_MINIMUM_OUTRO_LOOP_QUALITY,
        "pcm_bits": DEFAULT_PCM_BITS,
        "preview_seconds": DEFAULT_PREVIEW_SECONDS,
        "export_cues": DEFAULT_EXPORT_CUES,
        "maximum_repetitions": 8,
        "crossfade_ms": MINIMUM_CROSSFADE_MS,
        "candidate_count": DEFAULT_CANDIDATE_COUNT,
        "intro_search_seconds": INTRO_SEARCH_SECONDS,
        "outro_search_seconds": OUTRO_SEARCH_SECONDS,
        "maximum_vocal_coverage_percent": MAXIMUM_VOCAL_COVERAGE * 100,
        "maximum_vocal_boundary_risk_percent": MAXIMUM_VOCAL_BOUNDARY_RISK * 100,
        "maximum_buildup_risk_percent": MAXIMUM_BUILDUP_RISK * 100,
        "maximum_bass_reset_risk_percent": MAXIMUM_BASS_RESET_RISK * 100,
        "minimum_stem_reliability_percent": MINIMUM_STEM_CONSTRUCTION_RELIABILITY * 100,
    }


class WebSettings(BaseModel):
    music_library_path: str = DEFAULT_WEB_LIBRARY_PATH
    preset: str = "auto"
    intro_bars: int = DEFAULT_INTRO_BARS
    outro_bars: int = DEFAULT_OUTRO_BARS
    use_stems: bool = DEFAULT_USE_STEMS
    auto_bars: bool = DEFAULT_AUTO_BAR_SELECTION
    minimum_intro_loop_quality: float = Field(DEFAULT_MINIMUM_INTRO_LOOP_QUALITY, ge=0, le=100)
    minimum_outro_loop_quality: float = Field(DEFAULT_MINIMUM_OUTRO_LOOP_QUALITY, ge=0, le=100)
    pcm_bits: int = DEFAULT_PCM_BITS
    preview_seconds: float = Field(DEFAULT_PREVIEW_SECONDS, gt=0, le=60)
    export_cues: bool = DEFAULT_EXPORT_CUES
    maximum_repetitions: int = Field(8, ge=1, le=8)
    crossfade_ms: float = Field(MINIMUM_CROSSFADE_MS, ge=1, le=100)
    candidate_count: int = Field(DEFAULT_CANDIDATE_COUNT, ge=1, le=8)
    intro_search_seconds: float = Field(INTRO_SEARCH_SECONDS, ge=15, le=600)
    outro_search_seconds: float = Field(OUTRO_SEARCH_SECONDS, ge=15, le=600)
    maximum_vocal_coverage_percent: float = Field(MAXIMUM_VOCAL_COVERAGE * 100, ge=0, le=100)
    maximum_vocal_boundary_risk_percent: float = Field(MAXIMUM_VOCAL_BOUNDARY_RISK * 100, ge=0, le=100)
    maximum_buildup_risk_percent: float = Field(MAXIMUM_BUILDUP_RISK * 100, ge=0, le=100)
    maximum_bass_reset_risk_percent: float = Field(MAXIMUM_BASS_RESET_RISK * 100, ge=0, le=100)
    minimum_stem_reliability_percent: float = Field(MINIMUM_STEM_CONSTRUCTION_RELIABILITY * 100, ge=0, le=100)


class PresetStore:
    def __init__(self, path: Path, built_ins: dict[str, EditPreset] | None = None) -> None:
        self.path = path
        self.built_ins = built_ins if built_ins is not None else PRESETS

    def state(self) -> dict[str, Any]:
        try:
            state = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            state = {}
        return {
            "definitions": dict(state.get("definitions") or {}),
            "hidden": list(state.get("hidden") or []),
        }

    def save(self, state: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(self.path)

    def available(self) -> dict[str, EditPreset]:
        state = self.state()
        available = dict(self.built_ins)
        for name, values in state["definitions"].items():
            try:
                available[name] = EditPreset(**values)
            except (TypeError, ValueError):
                continue
        for name in state["hidden"]:
            available.pop(name, None)
        return available

    def payload(self) -> list[dict[str, Any]]:
        state = self.state()
        return [{
            "name": name,
            **preset.__dict__,
            "built_in": name in self.built_ins,
            "modified": name in state["definitions"],
        } for name, preset in self.available().items()]

    def snapshot(self, name: str) -> dict[str, Any]:
        preset = self.available().get(name)
        return {"preset_definition": preset.__dict__} if preset is not None else {}


class WebConfigurationService:
    """Apply defaults < durable system state < user overrides precedence."""

    def __init__(self, repository: SettingsRepository, defaults: dict[str, Any], presets: PresetStore) -> None:
        self.repository = repository
        self.defaults = defaults
        self.presets = presets

    def effective(self) -> dict[str, Any]:
        overrides = self.repository.get_settings()
        durable_library_path = self.repository.get_system_state("music_library_path")
        return {
            **self.defaults,
            **({"music_library_path": durable_library_path} if durable_library_path else {}),
            **overrides,
        }

    def validate(self, values: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(values)
        library_root = Path(str(normalized["music_library_path"]).strip()).expanduser()
        if not library_root.is_absolute():
            raise ValueError("Music Library Location must be an absolute path")
        normalized["music_library_path"] = str(library_root.resolve())
        if normalized["preset"] != "auto" and normalized["preset"] not in self.presets.available():
            raise ValueError("Unknown preset")
        if normalized["intro_bars"] not in SUPPORTED_BAR_COUNTS or normalized["outro_bars"] not in SUPPORTED_BAR_COUNTS:
            raise ValueError("Unsupported bar count")
        if normalized["pcm_bits"] not in (16, 24):
            raise ValueError("PCM depth must be 16 or 24")
        return normalized

    def persist(self, values: dict[str, Any]) -> dict[str, Any]:
        normalized = self.validate(values)
        overrides = {
            key: value for key, value in normalized.items()
            if value != (
                str(Path(str(self.defaults[key])).expanduser().resolve())
                if key == "music_library_path"
                else self.defaults[key]
            )
        }
        self.repository.replace_settings(overrides)
        self.repository.set_system_state("music_library_path", normalized["music_library_path"])
        return overrides

    def reset(self) -> None:
        self.repository.replace_settings({})
