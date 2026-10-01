"""Compatibility entry point for DJ Library Studio.

The assembled FastAPI application lives in :mod:`audioextender.web.application`.
Aliasing the module preserves existing callers that import or patch ``web_app``.
"""

from __future__ import annotations

import sys

from audioextender.web import application as _application

sys.modules[__name__] = _application


if __name__ == "__main__":
    _application.uvicorn.run(
        "audioextender.web.application:app",
        host="127.0.0.1",
        port=8765,
        reload=False,
    )
