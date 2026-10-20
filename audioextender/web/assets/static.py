"""Avoid stale browser modules when local application files change."""

from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope


class UncachedStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-store"
        return response
