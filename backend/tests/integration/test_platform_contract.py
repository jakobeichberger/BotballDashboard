"""Cross-cutting API contract and defensive middleware coverage."""

import pytest


@pytest.mark.asyncio
async def test_validation_errors_use_the_unified_contract(client, auth_headers, season):
    response = await client.post(
        "/api/v1/events",
        headers={**auth_headers, "X-Request-ID": "contract-test"},
        json={"season_id": season.id, "name": "x", "slug": "INVALID SLUG"},
    )
    assert response.status_code == 422
    assert response.headers["x-request-id"] == "contract-test"
    assert response.json()["code"] == "validation_error"
    assert response.json()["requestId"] == "contract-test"
    assert response.json()["fieldErrors"]


@pytest.mark.asyncio
async def test_security_headers_are_applied(client):
    response = await client.get("/api/system/health")
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"


@pytest.mark.asyncio
async def test_oversized_mutation_is_rejected_before_body_parsing(client):
    response = await client.post(
        "/api/auth/login",
        headers={"Content-Length": str(22 * 1024 * 1024)},
        content=b"{}",
    )
    assert response.status_code == 413
    assert response.json()["code"] == "request_too_large"


@pytest.mark.asyncio
async def test_metrics_are_prometheus_compatible(client):
    await client.get("/api/system/health")
    response = await client.get("/api/system/metrics")
    assert response.status_code == 200
    assert "botball_http_requests_total" in response.text
