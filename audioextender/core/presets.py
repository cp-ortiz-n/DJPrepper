"""Named editing strategies for common DJ use cases."""

from __future__ import annotations

from dataclasses import dataclass

from settings import PRESET_DEFINITIONS, SUPPORTED_BAR_COUNTS


@dataclass(frozen=True)
class EditPreset:
    """Named editing strategy for common DJ use cases."""

    intro_bars: int
    outro_bars: int
    use_stems: bool
    minimum_loop_quality: float
    maximum_repetitions: int


def _load_presets() -> dict[str, EditPreset]:
    presets: dict[str, EditPreset] = {}
    required = {
        "intro_bars",
        "outro_bars",
        "use_stems",
        "minimum_loop_quality",
        "maximum_repetitions",
    }
    for name, values in PRESET_DEFINITIONS.items():
        if not isinstance(name, str) or not name:
            raise ValueError("Preset names must be non-empty strings")
        if not isinstance(values, dict) or set(values) != required:
            raise ValueError(f"Preset {name!r} must define exactly: {sorted(required)}")
        preset = EditPreset(
            intro_bars=int(values["intro_bars"]),
            outro_bars=int(values["outro_bars"]),
            use_stems=bool(values["use_stems"]),
            minimum_loop_quality=float(values["minimum_loop_quality"]),
            maximum_repetitions=int(values["maximum_repetitions"]),
        )
        if preset.intro_bars not in SUPPORTED_BAR_COUNTS:
            raise ValueError(f"Preset {name!r} has unsupported intro_bars")
        if preset.outro_bars not in SUPPORTED_BAR_COUNTS:
            raise ValueError(f"Preset {name!r} has unsupported outro_bars")
        if not 0.0 <= preset.minimum_loop_quality <= 100.0:
            raise ValueError(f"Preset {name!r} quality must be between 0 and 100")
        if preset.maximum_repetitions < 1:
            raise ValueError(f"Preset {name!r} repetitions must be at least 1")
        presets[name] = preset
    return presets


PRESETS = _load_presets()


def get_preset(name: str | None) -> EditPreset | None:
    """Return the named preset, or None if no name is provided."""
    return PRESETS.get(name) if name is not None else None
