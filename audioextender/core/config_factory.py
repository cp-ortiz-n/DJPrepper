"""Build validated edit configuration from CLI values and preset policy."""

from __future__ import annotations

import argparse

from audioextender.core.config import EditConfig
from audioextender.core.presets import get_preset
from settings import (
    DEFAULT_CACHE_ENABLED,
    DEFAULT_CANDIDATE_COUNT,
    DEFAULT_INTRO_BARS,
    DEFAULT_OUTRO_BARS,
    DEFAULT_USE_STEMS,
    INTERACTIVE_CANDIDATE_POOL,
)


class ConfigFactory:
    """Centralize CLI → preset → application-default precedence."""

    @staticmethod
    def from_arguments(args: argparse.Namespace) -> EditConfig:
        preset = get_preset(args.preset)
        config = EditConfig(
            intro_bars=(
                args.intro_bars if args.intro_bars is not None
                else preset.intro_bars if preset is not None
                else DEFAULT_INTRO_BARS
            ),
            outro_bars=(
                args.outro_bars if args.outro_bars is not None
                else preset.outro_bars if preset is not None
                else DEFAULT_OUTRO_BARS
            ),
            use_stems=(
                args.use_stems if args.use_stems is not None
                else preset.use_stems if preset is not None
                else DEFAULT_USE_STEMS
            ),
            pcm_bits=args.bit_depth,
            minimum_loop_quality=preset.minimum_loop_quality if preset else 0.0,
            maximum_repetitions=preset.maximum_repetitions if preset else 8,
            preset_name=args.preset,
            intro_bars_locked=args.intro_bars is not None,
            outro_bars_locked=args.outro_bars is not None,
            stems_locked=args.use_stems is not None,
            cache_directory=str(args.cache_dir.expanduser().resolve()),
            cache_enabled=(DEFAULT_CACHE_ENABLED and not args.no_cache)
            or args.refresh_cache,
            refresh_cache=args.refresh_cache,
            create_previews=args.previews or args.preview_only or args.review,
            preview_only=args.preview_only,
            preview_seconds=args.preview_seconds,
            candidate_count=(
                INTERACTIVE_CANDIDATE_POOL
                if args.choose_candidates else DEFAULT_CANDIDATE_COUNT
            ),
            intro_candidate=args.intro_candidate,
            outro_candidate=args.outro_candidate,
            choose_candidates=args.choose_candidates or args.review,
            review_mode=args.review,
            auto_select_bar_lengths=args.auto_bars,
            export_cues=args.cues,
        )
        config.validate()
        ConfigFactory.validate_boundaries(args)
        return config

    @staticmethod
    def validate_boundaries(args: argparse.Namespace) -> None:
        for option in ("intro_before", "outro_after", "outro_before"):
            value = getattr(args, option)
            if value is not None and value <= 0:
                raise ValueError(
                    f"--{option.replace('_', '-')} must be greater than zero"
                )
