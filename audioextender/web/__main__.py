"""Run DJ Library Studio with ``python -m audioextender.web``."""

import uvicorn


def main() -> None:
    """Start the package-owned FastAPI application."""
    uvicorn.run(
        "audioextender.web.application:create_app",
        host="127.0.0.1",
        port=8765,
        reload=False,
        factory=True,
    )


if __name__ == "__main__":
    main()
