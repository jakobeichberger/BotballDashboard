"""Integration tests for the 3D Printing API routes (/api/printing/*).

Covers printers CRUD, print jobs CRUD + approve, quota GET, and spool
create / list / consume over HTTP. The shared `admin_user` fixture is a
superuser, so it bypasses all printing:* permission checks; auth-required
behaviour is verified separately by hitting endpoints without a token.
"""

import pytest

# ── Printers ────────────────────────────────────────────────────────────────


class TestPrinterRoutes:
    @pytest.mark.asyncio
    async def test_create_printer(self, client, auth_headers):
        resp = await client.post(
            "/api/printing/printers",
            headers=auth_headers,
            json={"name": "Bambu A", "model": "X1C", "printer_type": "bambu"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Bambu A"
        assert data["model"] == "X1C"
        assert data["printer_type"] == "bambu"
        assert data["is_active"] is True
        # Secret material must never be serialised.
        assert "api_key" not in data
        assert "api_key_encrypted" not in data

    @pytest.mark.asyncio
    async def test_create_printer_with_api_key_not_leaked(self, client, auth_headers):
        resp = await client.post(
            "/api/printing/printers",
            headers=auth_headers,
            json={"name": "Secret", "api_key": "top-secret-token"},
        )
        assert resp.status_code == 201
        body = resp.text
        assert "top-secret-token" not in body
        assert "api_key" not in resp.json()

    @pytest.mark.asyncio
    async def test_list_printers(self, client, auth_headers):
        await client.post("/api/printing/printers", headers=auth_headers, json={"name": "Zed"})
        await client.post("/api/printing/printers", headers=auth_headers, json={"name": "Abe"})
        resp = await client.get("/api/printing/printers", headers=auth_headers)
        assert resp.status_code == 200
        names = [p["name"] for p in resp.json()]
        assert names == ["Abe", "Zed"]  # ordered by name

    @pytest.mark.asyncio
    async def test_update_printer(self, client, auth_headers):
        create = await client.post(
            "/api/printing/printers",
            headers=auth_headers,
            json={"name": "Before", "notes": "keep"},
        )
        printer_id = create.json()["id"]
        resp = await client.patch(
            f"/api/printing/printers/{printer_id}",
            headers=auth_headers,
            json={"name": "After", "is_active": False},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "After"
        assert data["is_active"] is False
        assert data["notes"] == "keep"  # untouched

    @pytest.mark.asyncio
    async def test_update_printer_not_found(self, client, auth_headers):
        resp = await client.patch(
            "/api/printing/printers/missing-id",
            headers=auth_headers,
            json={"name": "X"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_printers_require_auth(self, client):
        assert (await client.get("/api/printing/printers")).status_code == 401
        assert (await client.post("/api/printing/printers", json={"name": "X"})).status_code == 401


# ── Print jobs ──────────────────────────────────────────────────────────────


class TestPrintJobRoutes:
    async def _create_job(self, client, auth_headers, team, season, **overrides):
        payload = {
            "team_id": team.id,
            "season_id": season.id,
            "file_name": overrides.pop("file_name", "robot.3mf"),
            "material": "PLA",
            **overrides,
        }
        return await client.post("/api/printing/jobs", headers=auth_headers, json=payload)

    @pytest.mark.asyncio
    async def test_create_job(self, client, auth_headers, team, season, admin_user):
        resp = await self._create_job(client, auth_headers, team, season)
        assert resp.status_code == 201
        data = resp.json()
        assert data["team_id"] == team.id
        assert data["season_id"] == season.id
        assert data["file_name"] == "robot.3mf"
        assert data["status"] == "pending"
        assert data["submitted_by"] == admin_user.id

    @pytest.mark.asyncio
    async def test_create_job_validation_error(self, client, auth_headers):
        # Missing required team_id/season_id/file_name => 422.
        resp = await client.post(
            "/api/printing/jobs", headers=auth_headers, json={"material": "PLA"}
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_job_blocked_by_hard_limit(self, client, auth_headers, team, season):
        # Drive the quota up to the hard limit, then expect a 409.
        for i in range(4):  # default max_parts == 4
            r = await self._create_job(client, auth_headers, team, season, file_name=f"p{i}.3mf")
            job_id = r.json()["id"]
            await client.put(f"/api/printing/jobs/{job_id}/approve", headers=auth_headers)
            await client.patch(
                f"/api/printing/jobs/{job_id}",
                headers=auth_headers,
                json={"status": "queued"},
            )
            await client.patch(
                f"/api/printing/jobs/{job_id}",
                headers=auth_headers,
                json={"status": "completed", "actual_grams": 5.0},
            )
        resp = await self._create_job(client, auth_headers, team, season, file_name="over.3mf")
        assert resp.status_code == 409
        assert "Hard print limit reached" in resp.json()["message"]

    @pytest.mark.asyncio
    async def test_list_jobs_and_filter(self, client, auth_headers, team, season):
        await self._create_job(client, auth_headers, team, season, file_name="x.3mf")
        all_resp = await client.get("/api/printing/jobs", headers=auth_headers)
        assert all_resp.status_code == 200
        assert len(all_resp.json()) == 1

        filtered = await client.get(
            "/api/printing/jobs",
            headers=auth_headers,
            params={"team_id": team.id, "status": "pending"},
        )
        assert filtered.status_code == 200
        assert len(filtered.json()) == 1

        none = await client.get(
            "/api/printing/jobs", headers=auth_headers, params={"status": "completed"}
        )
        assert none.json() == []

    @pytest.mark.asyncio
    async def test_update_job_status_to_printing(self, client, auth_headers, team, season):
        create = await self._create_job(client, auth_headers, team, season)
        job_id = create.json()["id"]
        await client.put(f"/api/printing/jobs/{job_id}/approve", headers=auth_headers)
        await client.patch(
            f"/api/printing/jobs/{job_id}",
            headers=auth_headers,
            json={"status": "queued"},
        )
        resp = await client.patch(
            f"/api/printing/jobs/{job_id}",
            headers=auth_headers,
            json={"status": "printing"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "printing"
        assert data["started_at"] is not None

    @pytest.mark.asyncio
    async def test_update_job_not_found(self, client, auth_headers):
        resp = await client.patch(
            "/api/printing/jobs/nope", headers=auth_headers, json={"status": "queued"}
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_approve_job(self, client, auth_headers, team, season, admin_user):
        create = await self._create_job(client, auth_headers, team, season)
        job_id = create.json()["id"]
        resp = await client.put(f"/api/printing/jobs/{job_id}/approve", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "approved"
        assert data["approved_by"] == admin_user.id
        assert data["approved_at"] is not None

    @pytest.mark.asyncio
    async def test_approve_job_not_found(self, client, auth_headers):
        resp = await client.put("/api/printing/jobs/missing/approve", headers=auth_headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_jobs_require_auth(self, client):
        assert (await client.get("/api/printing/jobs")).status_code == 401


# ── Quotas ──────────────────────────────────────────────────────────────────


class TestQuotaRoutes:
    @pytest.mark.asyncio
    async def test_get_quota_creates_default(self, client, auth_headers, team, season):
        resp = await client.get(
            "/api/printing/quotas",
            headers=auth_headers,
            params={"team_id": team.id, "season_id": season.id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["team_id"] == team.id
        assert data["season_id"] == season.id
        assert data["max_parts"] == 4
        assert data["soft_limit_parts"] == 3
        assert data["used_parts"] == 0

    @pytest.mark.asyncio
    async def test_get_quota_requires_params(self, client, auth_headers, team):
        # season_id is a required query param.
        resp = await client.get(
            "/api/printing/quotas", headers=auth_headers, params={"team_id": team.id}
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_quota_reflects_completed_usage(self, client, auth_headers, team, season):
        create = await client.post(
            "/api/printing/jobs",
            headers=auth_headers,
            json={
                "team_id": team.id,
                "season_id": season.id,
                "file_name": "u.3mf",
                "material": "PLA",
            },
        )
        job_id = create.json()["id"]
        await client.put(f"/api/printing/jobs/{job_id}/approve", headers=auth_headers)
        await client.patch(
            f"/api/printing/jobs/{job_id}",
            headers=auth_headers,
            json={"status": "queued"},
        )
        await client.patch(
            f"/api/printing/jobs/{job_id}",
            headers=auth_headers,
            json={"status": "completed", "actual_grams": 33.0},
        )
        resp = await client.get(
            "/api/printing/quotas",
            headers=auth_headers,
            params={"team_id": team.id, "season_id": season.id},
        )
        data = resp.json()
        assert data["used_parts"] == 1
        assert data["used_grams"] == 33.0

    @pytest.mark.asyncio
    async def test_quota_requires_auth(self, client, team, season):
        resp = await client.get(
            "/api/printing/quotas",
            params={"team_id": team.id, "season_id": season.id},
        )
        assert resp.status_code == 401


# ── Filament spools ─────────────────────────────────────────────────────────


class TestSpoolRoutes:
    @pytest.mark.asyncio
    async def test_create_spool_defaults_remaining(self, client, auth_headers):
        resp = await client.post(
            "/api/printing/spools",
            headers=auth_headers,
            json={"material": "PLA", "color": "Black", "initial_grams": 800.0},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["initial_grams"] == 800.0
        # remaining_grams defaults to initial_grams on a fresh spool.
        assert data["remaining_grams"] == 800.0
        assert data["is_active"] is True

    @pytest.mark.asyncio
    async def test_list_spools(self, client, auth_headers):
        await client.post(
            "/api/printing/spools",
            headers=auth_headers,
            json={"material": "PLA", "initial_grams": 1000.0},
        )
        resp = await client.get("/api/printing/spools", headers=auth_headers)
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    @pytest.mark.asyncio
    async def test_list_spools_filter_by_printer(self, client, auth_headers):
        printer = (
            await client.post("/api/printing/printers", headers=auth_headers, json={"name": "PF"})
        ).json()
        await client.post(
            "/api/printing/spools",
            headers=auth_headers,
            json={"material": "PLA", "initial_grams": 1000.0, "printer_id": printer["id"]},
        )
        await client.post(
            "/api/printing/spools",
            headers=auth_headers,
            json={"material": "PLA", "initial_grams": 1000.0},
        )
        resp = await client.get(
            "/api/printing/spools",
            headers=auth_headers,
            params={"printer_id": printer["id"]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["printer_id"] == printer["id"]

    @pytest.mark.asyncio
    async def test_consume_filament(self, client, auth_headers):
        create = await client.post(
            "/api/printing/spools",
            headers=auth_headers,
            json={"material": "PETG", "initial_grams": 500.0},
        )
        spool_id = create.json()["id"]
        # `grams` is a QUERY param.
        resp = await client.post(
            f"/api/printing/spools/{spool_id}/consume",
            headers=auth_headers,
            params={"grams": 120.5},
        )
        assert resp.status_code == 200
        assert resp.json()["remaining_grams"] == pytest.approx(379.5)

    @pytest.mark.asyncio
    async def test_consume_clamps_to_zero(self, client, auth_headers):
        create = await client.post(
            "/api/printing/spools",
            headers=auth_headers,
            json={"material": "PLA", "initial_grams": 40.0},
        )
        spool_id = create.json()["id"]
        resp = await client.post(
            f"/api/printing/spools/{spool_id}/consume",
            headers=auth_headers,
            params={"grams": 999.0},
        )
        assert resp.status_code == 200
        assert resp.json()["remaining_grams"] == 0.0

    @pytest.mark.asyncio
    async def test_consume_requires_positive_grams(self, client, auth_headers):
        create = await client.post(
            "/api/printing/spools",
            headers=auth_headers,
            json={"material": "PLA", "initial_grams": 100.0},
        )
        spool_id = create.json()["id"]
        # grams must be > 0 (Query gt=0).
        resp = await client.post(
            f"/api/printing/spools/{spool_id}/consume",
            headers=auth_headers,
            params={"grams": 0},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_consume_nonexistent_spool(self, client, auth_headers):
        resp = await client.post(
            "/api/printing/spools/missing/consume",
            headers=auth_headers,
            params={"grams": 10.0},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_spools_require_auth(self, client):
        assert (await client.get("/api/printing/spools")).status_code == 401
