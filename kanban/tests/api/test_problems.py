"""Unit tests for RFC 7807 problem details and exception handlers (S3.4)."""

from __future__ import annotations

import logging
from typing import Any

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from kanban.api.problems import (
    PROBLEM_MEDIA_TYPE,
    FieldError,
    Problem,
    ProblemException,
    not_found,
    problem_exception_handler,
    starlette_http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from kanban.api.request_id import RequestIdMiddleware


class _SamplePayload(BaseModel):
    name: str = Field(min_length=3, max_length=10)
    count: int = Field(gt=0)


def _build_test_app() -> FastAPI:
    """Build a minimal FastAPI application configured with RFC 7807 problem handlers."""
    test_app = FastAPI(title="Problem Handler Test App")
    test_app.add_middleware(RequestIdMiddleware)

    test_app.add_exception_handler(ProblemException, problem_exception_handler)  # type: ignore[arg-type]
    test_app.add_exception_handler(StarletteHTTPException, starlette_http_exception_handler)  # type: ignore[arg-type]
    test_app.add_exception_handler(Exception, unhandled_exception_handler)
    test_app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]

    @test_app.get("/raise-internal")
    async def raise_internal() -> None:
        err_msg = "SELECT secret FROM x at /srv/app.py"
        raise RuntimeError(err_msg)

    @test_app.post("/validate-input")
    async def validate_input(payload: _SamplePayload) -> dict[str, Any]:
        return {"status": "ok", "name": payload.name}

    @test_app.get("/not-found-route")
    async def not_found_route() -> None:
        not_found()

    @test_app.get("/raise-problem")
    async def raise_problem() -> None:
        raise ProblemException(
            code="RESOURCE_LOCKED",
            status=423,
            title="Resource Locked",
            detail="Item is currently locked by another worker",
            errors=[FieldError(path="lock.owner", message="Held by lease-123")],
        )

    @test_app.get("/raise-http-401")
    async def raise_http_401() -> None:
        raise HTTPException(status_code=401, detail="Bearer token expired")

    @test_app.get("/raise-http-404")
    async def raise_http_404() -> None:
        raise HTTPException(status_code=404, detail="Hidden file path /etc/shadow")

    @test_app.get("/raise-http-403")
    async def raise_http_403() -> None:
        raise HTTPException(status_code=403, detail="Forbidden permission")

    @test_app.get("/raise-http-418")
    async def raise_http_418() -> None:
        raise HTTPException(status_code=418, detail="I'm a teapot")

    return test_app


def test_problem_exception_validation() -> None:
    """Test ProblemException validates error code format strictly."""
    # Valid codes
    exc = ProblemException(code="VALID_CODE", status=400, title="Bad Request")
    assert exc.code == "VALID_CODE"
    assert exc.status == 400
    assert str(exc) == "Bad Request"

    exc_detail = ProblemException(
        code="VALID_CODE_2", status=400, title="Bad Request", detail="More info"
    )
    assert str(exc_detail) == "Bad Request: More info"

    # Invalid codes
    invalid_codes = ["lowercase", "UP", "BAD-DASH", "SPACES IN CODE", "123_START_NUM", ""]
    for bad_code in invalid_codes:
        with pytest.raises(ValueError, match="Invalid problem code"):
            ProblemException(code=bad_code, status=400, title="Test")


def test_not_found_helper() -> None:
    """Test not_found helper raises canonical 404 ProblemException."""
    with pytest.raises(ProblemException) as exc_info:
        not_found()

    exc = exc_info.value
    assert exc.status == 404
    assert exc.code == "NOT_FOUND"
    assert exc.title == "Not Found"
    assert exc.detail is None


def test_problem_model_serialization() -> None:
    """Test Problem Pydantic model serialization and exclude_none behavior."""
    prob = Problem(
        type="urn:kanban:problem:NOT_FOUND",
        title="Not Found",
        status=404,
        code="NOT_FOUND",
        request_id="req-12345678",
    )
    dumped = prob.model_dump(exclude_none=True)
    assert dumped["type"] == "urn:kanban:problem:NOT_FOUND"
    assert dumped["title"] == "Not Found"
    assert dumped["status"] == 404
    assert dumped["code"] == "NOT_FOUND"
    assert dumped["request_id"] == "req-12345678"
    assert "detail" not in dumped
    assert "errors" not in dumped


@pytest.mark.asyncio
async def test_case_5_security_error_disclosure(caplog: pytest.LogCaptureFixture) -> None:
    """Test Case 5: Route raising internal error returns 500 without leaking exception internals."""
    app = _build_test_app()
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    caplog.set_level(logging.ERROR)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/raise-internal")
        assert response.status_code == 500
        assert response.headers.get("content-type") == PROBLEM_MEDIA_TYPE

        data = response.json()
        assert data["code"] == "INTERNAL_ERROR"
        assert data["status"] == 500
        assert data["title"] == "Internal Server Error"
        assert data["type"] == "urn:kanban:problem:INTERNAL_ERROR"
        assert "request_id" in data
        assert response.headers.get("x-request-id") == data["request_id"]

        # Ensure no sensitive strings leaked into response body
        raw_text = response.text
        assert "SELECT" not in raw_text
        assert "/srv/" not in raw_text
        assert "RuntimeError" not in raw_text
        assert "Traceback" not in raw_text
        assert "secret" not in raw_text


@pytest.mark.asyncio
async def test_case_6_security_validation_echo() -> None:
    """Test Case 6: 422 validation error does not echo user input."""
    app = _build_test_app()
    transport = httpx.ASGITransport(app=app)
    hostile_input = "<script>alert(1)</script>"

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/validate-input",
            json={"name": hostile_input, "count": -5},
        )
        assert response.status_code == 422
        assert response.headers.get("content-type") == PROBLEM_MEDIA_TYPE

        data = response.json()
        assert data["code"] == "VALIDATION_FAILED"
        assert data["status"] == 422
        assert data["title"] == "Validation Failed"
        assert data["type"] == "urn:kanban:problem:VALIDATION_FAILED"
        assert data["detail"] == "Request validation failed"
        assert isinstance(data["errors"], list)
        assert len(data["errors"]) >= 1

        # Hostile script payload must NOT be present anywhere in the response body
        assert hostile_input not in response.text
        assert "alert(1)" not in response.text

        # Verify FieldErrors only contain path and constraint message
        for err in data["errors"]:
            assert "path" in err
            assert "message" in err
            assert "input" not in err


@pytest.mark.asyncio
async def test_not_found_endpoint() -> None:
    """Test endpoint calling not_found() returns canonical 404 problem."""
    app = _build_test_app()
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/not-found-route")
        assert response.status_code == 404
        assert response.headers.get("content-type") == PROBLEM_MEDIA_TYPE

        data = response.json()
        assert data["code"] == "NOT_FOUND"
        assert data["status"] == 404
        assert data["title"] == "Not Found"
        assert data["type"] == "urn:kanban:problem:NOT_FOUND"
        assert "detail" not in data


@pytest.mark.asyncio
async def test_explicit_problem_exception() -> None:
    """Test endpoint raising explicit ProblemException with custom errors."""
    app = _build_test_app()
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/raise-problem")
        assert response.status_code == 423
        assert response.headers.get("content-type") == PROBLEM_MEDIA_TYPE

        data = response.json()
        assert data["code"] == "RESOURCE_LOCKED"
        assert data["status"] == 423
        assert data["title"] == "Resource Locked"
        assert data["type"] == "urn:kanban:problem:RESOURCE_LOCKED"
        assert data["detail"] == "Item is currently locked by another worker"
        assert data["errors"] == [{"path": "lock.owner", "message": "Held by lease-123"}]


@pytest.mark.asyncio
async def test_starlette_http_exception_mappings() -> None:
    """Test Starlette HTTP exception mapping for 401, 404, 403, and unmapped codes."""
    app = _build_test_app()
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 401 strips detail
        res_401 = await client.get("/raise-http-401")
        assert res_401.status_code == 401
        data_401 = res_401.json()
        assert data_401["code"] == "AUTHENTICATION_REQUIRED"
        assert "detail" not in data_401

        # 404 strips detail
        res_404 = await client.get("/raise-http-404")
        assert res_404.status_code == 404
        data_404 = res_404.json()
        assert data_404["code"] == "NOT_FOUND"
        assert "detail" not in data_404

        # 403 retains safe detail
        res_403 = await client.get("/raise-http-403")
        assert res_403.status_code == 403
        data_403 = res_403.json()
        assert data_403["code"] == "FORBIDDEN"
        assert data_403["detail"] == "Forbidden permission"

        # 418 unmapped code
        res_418 = await client.get("/raise-http-418")
        assert res_418.status_code == 418
        data_418 = res_418.json()
        assert data_418["code"] == "HTTP_418"
        assert data_418["title"] == "HTTP Error"
        assert data_418["detail"] == "I'm a teapot"
