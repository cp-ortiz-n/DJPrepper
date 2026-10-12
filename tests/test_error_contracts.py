import unittest

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel

from audioextender.core.exceptions import ConfigurationError
from audioextender.web.error_contracts import classify_status, install_error_handlers


class RequestBody(BaseModel):
    count: int


def contract_app() -> FastAPI:
    application = FastAPI()
    install_error_handlers(application)

    @application.get("/missing")
    def missing() -> None:
        raise HTTPException(404, "Track not found")

    @application.get("/conflict")
    def conflict() -> None:
        raise HTTPException(409, {"message": "Library is busy", "operation": "relocation"})

    @application.get("/domain")
    def domain() -> None:
        raise ConfigurationError("Unsupported bar count")

    @application.post("/validated")
    def validated(_body: RequestBody) -> dict:
        return {"ok": True}

    @application.get("/unexpected")
    def unexpected() -> None:
        raise RuntimeError("sensitive implementation detail")

    return application


class ErrorContractTests(unittest.TestCase):
    def test_status_vocabulary_is_stable(self) -> None:
        self.assertEqual(classify_status(404), ("not_found", "not_found", False))
        self.assertEqual(classify_status(409), ("conflict", "conflict", False))
        self.assertEqual(classify_status(503), ("resource_unavailable", "unavailable", True))
        self.assertEqual(classify_status(500), ("internal_error", "unexpected", True))

    def test_http_errors_keep_legacy_detail_and_add_machine_contract(self) -> None:
        client = TestClient(contract_app())
        missing = client.get("/missing")
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.json()["detail"], "Track not found")
        self.assertEqual(
            missing.json()["error"],
            {"code": "not_found", "category": "not_found", "message": "Track not found", "retryable": False},
        )
        self.assertEqual(missing.headers["x-audioextender-error-code"], "not_found")

        conflict = client.get("/conflict").json()
        self.assertEqual(conflict["detail"]["operation"], "relocation")
        self.assertEqual(conflict["error"]["message"], "Library is busy")

    def test_validation_and_domain_errors_use_the_same_shape(self) -> None:
        client = TestClient(contract_app())
        validation = client.post("/validated", json={"count": "not-a-number"}).json()
        self.assertIsInstance(validation["detail"], list)
        self.assertEqual(validation["error"]["category"], "validation")

        domain = client.get("/domain").json()
        self.assertEqual(domain["detail"], "Unsupported bar count")
        self.assertEqual(domain["error"]["category"], "validation")

    def test_unexpected_errors_are_logged_without_leaking_exception_text(self) -> None:
        client = TestClient(contract_app(), raise_server_exceptions=False)
        response = client.get("/unexpected")
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("sensitive implementation detail", response.text)
        self.assertEqual(response.json()["error"]["code"], "internal_error")


if __name__ == "__main__":
    unittest.main()
