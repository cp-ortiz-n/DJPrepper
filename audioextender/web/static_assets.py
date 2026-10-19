"""Cache policy for application assets that change between local releases."""

from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope


class RevalidatingStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response
