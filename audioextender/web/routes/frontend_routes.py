"""HTTP delivery for the versioned frontend shell."""

from typing import cast

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from audioextender.web.assets.frontend import FrontendAssetService


def create_frontend_router() -> APIRouter:
    router = APIRouter(tags=["frontend"])

    @router.get("/")
    def index(request: Request) -> HTMLResponse:
        shell = cast(FrontendAssetService, request.app.state.frontend_assets).render_index()
        return HTMLResponse(
            shell.html,
            headers={
                "Cache-Control": "no-store",
                "X-DJLS-Asset-Revision": shell.revision,
            },
        )

    return router
