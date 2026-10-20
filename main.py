"""Compatibility launcher for the package-owned AudioExtender CLI."""

from audioextender.cli import (
    _discover_inputs,
    _format_duration,
    _output_path,
    _parser,
    main,
    run,
)

__all__ = ["_discover_inputs", "_format_duration", "_output_path", "_parser", "main", "run"]


if __name__ == "__main__":
    raise SystemExit(main())
