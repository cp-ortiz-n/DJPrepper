"""HTTP delivery for process-local runtime diagnostics."""

from fastapi import APIRouter, Response

from audioextender.infrastructure.performance_diagnostics import PerformanceDiagnostics
from audioextender.infrastructure.runtime_revision import RuntimeRevision


def create_diagnostic_router(
    diagnostics: PerformanceDiagnostics,
    runtime_revision: RuntimeRevision | None = None,
) -> APIRouter:
    runtime_revision = runtime_revision or RuntimeRevision.capture()
    router = APIRouter(prefix="/api/diagnostics", tags=["diagnostics"])

    @router.get("/runtime")
    def runtime_identity(response: Response) -> dict[str, object]:
        response.headers["Cache-Control"] = "no-store"
        return {
            "revision": runtime_revision.value,
            "algorithm": "sha256",
            "source_files": runtime_revision.file_count,
        }

    @router.get("/performance")
    def performance_report() -> dict:
        return diagnostics.report()

    return router
