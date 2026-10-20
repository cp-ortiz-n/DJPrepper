"""HTTP delivery for process-local performance diagnostics."""

from fastapi import APIRouter

from audioextender.infrastructure.performance_diagnostics import PerformanceDiagnostics


def create_diagnostic_router(diagnostics: PerformanceDiagnostics) -> APIRouter:
    router = APIRouter(prefix="/api/diagnostics", tags=["diagnostics"])

    @router.get("/performance")
    def performance_report() -> dict:
        return diagnostics.report()

    return router
