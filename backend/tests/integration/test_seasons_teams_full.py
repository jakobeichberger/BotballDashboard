"""Integration tests for the seasons and teams API routes.

Routes are mounted under the /api prefix. The admin user is a superuser and
bypasses every permission check, so auth_headers can hit every route.

Covers happy paths, edge cases, and error cases (404/409/422/401) for:
- /api/seasons  (CRUD, activate season, activate phase, active, competition-levels)
- /api/teams    (CRUD, members, registrations, confirm, duplicate guard)
"""

import pytest

# ══════════════════════════════════════════════════════════════════════════════
# Seasons routes
# ══════════════════════════════════════════════════════════════════════════════


class TestSeasonRoutes:
    @pytest.mark.asyncio
    async def test_create_minimal(self, client, auth_headers):
        resp = await client.post(
            "/api/seasons", headers=auth_headers, json={"name": "S 2030", "year": 2030}
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "S 2030"
        assert body["year"] == 2030
        assert body["is_active"] is False
        assert body["phases"] == []

    @pytest.mark.asyncio
    async def test_create_with_phases(self, client, auth_headers, db):
        resp = await client.post(
            "/api/seasons",
            headers=auth_headers,
            json={
                "name": "Phased",
                "year": 2031,
                "phases": [
                    {"name": "Seeding", "phase_type": "seeding", "sort_order": 0},
                    {"name": "Finals", "phase_type": "final", "sort_order": 1},
                ],
            },
        )
        assert resp.status_code == 201
        sid = resp.json()["id"]
        # Commit the shared session to mirror the real per-request commit so
        # the nested phases are visible on a subsequent fetch.
        await db.commit()
        refetch = await client.get(f"/api/seasons/{sid}", headers=auth_headers)
        phases = refetch.json()["phases"]
        assert len(phases) == 2
        assert phases[0]["name"] == "Seeding"

    @pytest.mark.asyncio
    async def test_create_with_modules(self, client, auth_headers):
        resp = await client.post(
            "/api/seasons",
            headers=auth_headers,
            json={
                "name": "Mods",
                "year": 2032,
                "use_double_elimination": True,
                "active_categories": ["botball", "aerial"],
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["use_double_elimination"] is True
        assert body["active_categories"] == ["botball", "aerial"]

    @pytest.mark.asyncio
    async def test_create_missing_required_field_422(self, client, auth_headers):
        # Missing `year`
        resp = await client.post("/api/seasons", headers=auth_headers, json={"name": "NoYear"})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_phase_missing_phase_type_422(self, client, auth_headers):
        resp = await client.post(
            "/api/seasons",
            headers=auth_headers,
            json={
                "name": "BadPhase",
                "year": 2033,
                "phases": [{"name": "OnlyName"}],
            },
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_list(self, client, auth_headers):
        await client.post("/api/seasons", headers=auth_headers, json={"name": "L1", "year": 2034})
        resp = await client.get("/api/seasons", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert any(s["name"] == "L1" for s in data)

    @pytest.mark.asyncio
    async def test_get_one(self, client, auth_headers):
        created = await client.post(
            "/api/seasons", headers=auth_headers, json={"name": "G1", "year": 2035}
        )
        sid = created.json()["id"]
        resp = await client.get(f"/api/seasons/{sid}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["id"] == sid

    @pytest.mark.asyncio
    async def test_get_one_404(self, client, auth_headers):
        resp = await client.get("/api/seasons/missing", headers=auth_headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update(self, client, auth_headers):
        created = await client.post(
            "/api/seasons", headers=auth_headers, json={"name": "U1", "year": 2036}
        )
        sid = created.json()["id"]
        resp = await client.patch(
            f"/api/seasons/{sid}",
            headers=auth_headers,
            json={"name": "U1-renamed", "game_theme": "Theme"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "U1-renamed"
        assert body["game_theme"] == "Theme"

    @pytest.mark.asyncio
    async def test_update_404(self, client, auth_headers):
        resp = await client.patch("/api/seasons/missing", headers=auth_headers, json={"name": "x"})
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_activate(self, client, auth_headers):
        created = await client.post(
            "/api/seasons", headers=auth_headers, json={"name": "Act", "year": 2037}
        )
        sid = created.json()["id"]
        resp = await client.put(f"/api/seasons/{sid}/activate", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["is_active"] is True

    @pytest.mark.asyncio
    async def test_activate_deactivates_previous(self, client, auth_headers, db):
        first = (
            await client.post(
                "/api/seasons", headers=auth_headers, json={"name": "First", "year": 2038}
            )
        ).json()
        second = (
            await client.post(
                "/api/seasons", headers=auth_headers, json={"name": "Second", "year": 2039}
            )
        ).json()
        await db.commit()
        await client.put(f"/api/seasons/{first['id']}/activate", headers=auth_headers)
        await db.commit()
        await client.put(f"/api/seasons/{second['id']}/activate", headers=auth_headers)
        await db.commit()

        active = (await client.get("/api/seasons/active", headers=auth_headers)).json()
        assert active["id"] == second["id"]
        refetch = (await client.get(f"/api/seasons/{first['id']}", headers=auth_headers)).json()
        assert refetch["is_active"] is False

    @pytest.mark.asyncio
    async def test_activate_404(self, client, auth_headers):
        resp = await client.put("/api/seasons/missing/activate", headers=auth_headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_active_null_when_none(self, client, auth_headers):
        resp = await client.get("/api/seasons/active", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() is None

    @pytest.mark.asyncio
    async def test_get_active_with_fixture(self, client, auth_headers, season):
        resp = await client.get("/api/seasons/active", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["id"] == season.id

    @pytest.mark.asyncio
    async def test_delete_inactive(self, client, auth_headers, db):
        created = await client.post(
            "/api/seasons", headers=auth_headers, json={"name": "Del", "year": 2040}
        )
        sid = created.json()["id"]
        await db.commit()
        resp = await client.delete(f"/api/seasons/{sid}", headers=auth_headers)
        assert resp.status_code == 204
        await db.commit()
        # Now gone
        assert (await client.get(f"/api/seasons/{sid}", headers=auth_headers)).status_code == 404

    @pytest.mark.asyncio
    async def test_delete_active_409(self, client, auth_headers):
        created = await client.post(
            "/api/seasons", headers=auth_headers, json={"name": "ActiveDel", "year": 2041}
        )
        sid = created.json()["id"]
        await client.put(f"/api/seasons/{sid}/activate", headers=auth_headers)
        resp = await client.delete(f"/api/seasons/{sid}", headers=auth_headers)
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_delete_404(self, client, auth_headers):
        resp = await client.delete("/api/seasons/missing", headers=auth_headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_activate_phase(self, client, auth_headers, db):
        created = await client.post(
            "/api/seasons",
            headers=auth_headers,
            json={
                "name": "PhaseSeason",
                "year": 2042,
                "phases": [
                    {"name": "Seeding", "phase_type": "seeding", "sort_order": 0},
                    {"name": "Finals", "phase_type": "final", "sort_order": 1},
                ],
            },
        )
        sid = created.json()["id"]
        await db.commit()
        # Phase IDs are not in the create response under the shared-session
        # harness, so read them from a committed refetch.
        phases = (await client.get(f"/api/seasons/{sid}", headers=auth_headers)).json()["phases"]
        seeding_id = phases[0]["id"]
        finals_id = phases[1]["id"]

        r1 = await client.put(
            f"/api/seasons/{sid}/phases/{seeding_id}/activate", headers=auth_headers
        )
        assert r1.status_code == 200
        assert r1.json()["is_active"] is True
        await db.commit()

        # Activating finals deactivates seeding
        await client.put(f"/api/seasons/{sid}/phases/{finals_id}/activate", headers=auth_headers)
        await db.commit()
        refetch = (await client.get(f"/api/seasons/{sid}", headers=auth_headers)).json()
        active = [p for p in refetch["phases"] if p["is_active"]]
        assert len(active) == 1
        assert active[0]["id"] == finals_id

    @pytest.mark.asyncio
    async def test_activate_phase_404(self, client, auth_headers):
        created = await client.post(
            "/api/seasons", headers=auth_headers, json={"name": "NoPhase", "year": 2043}
        )
        sid = created.json()["id"]
        resp = await client.put(f"/api/seasons/{sid}/phases/missing/activate", headers=auth_headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_competition_levels(self, client, auth_headers, db):
        from modules.seasons.models import CompetitionLevel

        db.add_all(
            [
                CompetitionLevel(name="ECER", code="ecer", is_active=True),
                CompetitionLevel(name="Hidden", code="hidden", is_active=False),
            ]
        )
        await db.commit()
        resp = await client.get("/api/seasons/competition-levels/all", headers=auth_headers)
        assert resp.status_code == 200
        codes = [lvl["code"] for lvl in resp.json()]
        assert "ecer" in codes
        assert "hidden" not in codes

    @pytest.mark.asyncio
    async def test_requires_auth(self, client):
        resp = await client.get("/api/seasons")
        assert resp.status_code == 401


# ══════════════════════════════════════════════════════════════════════════════
# Teams routes
# ══════════════════════════════════════════════════════════════════════════════


class TestTeamRoutes:
    @pytest.mark.asyncio
    async def test_create_minimal(self, client, auth_headers):
        resp = await client.post("/api/teams", headers=auth_headers, json={"name": "T1"})
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "T1"
        assert body["country"] == "DE"
        assert body["is_active"] is True
        assert body["members"] == []

    @pytest.mark.asyncio
    async def test_create_with_members(self, client, auth_headers, db):
        resp = await client.post(
            "/api/teams",
            headers=auth_headers,
            json={
                "name": "TM",
                "country": "AT",
                "members": [
                    {"name": "Alice", "role": "mentor"},
                    {"name": "Bob"},
                ],
            },
        )
        assert resp.status_code == 201
        tid = resp.json()["id"]
        await db.commit()
        members = (await client.get(f"/api/teams/{tid}", headers=auth_headers)).json()["members"]
        assert len(members) == 2
        # default role applied
        roles = {m["name"]: m["role"] for m in members}
        assert roles["Bob"] == "member"

    @pytest.mark.asyncio
    async def test_create_missing_name_422(self, client, auth_headers):
        resp = await client.post("/api/teams", headers=auth_headers, json={"country": "DE"})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_list(self, client, auth_headers):
        await client.post("/api/teams", headers=auth_headers, json={"name": "LT"})
        resp = await client.get("/api/teams", headers=auth_headers)
        assert resp.status_code == 200
        assert any(t["name"] == "LT" for t in resp.json())

    @pytest.mark.asyncio
    async def test_list_filter_by_season(self, client, auth_headers, db):
        season = (
            await client.post(
                "/api/seasons", headers=auth_headers, json={"name": "FS", "year": 2050}
            )
        ).json()
        reg_team = (
            await client.post("/api/teams", headers=auth_headers, json={"name": "Reg"})
        ).json()
        await client.post("/api/teams", headers=auth_headers, json={"name": "NoReg"})
        await client.post(
            "/api/teams/registrations",
            headers=auth_headers,
            json={"team_id": reg_team["id"], "season_id": season["id"]},
        )
        await db.commit()

        resp = await client.get(f"/api/teams?season_id={season['id']}", headers=auth_headers)
        assert resp.status_code == 200
        names = [t["name"] for t in resp.json()]
        assert names == ["Reg"]

    @pytest.mark.asyncio
    async def test_get_one(self, client, auth_headers):
        created = await client.post("/api/teams", headers=auth_headers, json={"name": "GT"})
        tid = created.json()["id"]
        resp = await client.get(f"/api/teams/{tid}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["id"] == tid

    @pytest.mark.asyncio
    async def test_get_one_404(self, client, auth_headers):
        resp = await client.get("/api/teams/missing", headers=auth_headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update(self, client, auth_headers):
        created = await client.post("/api/teams", headers=auth_headers, json={"name": "Old"})
        tid = created.json()["id"]
        resp = await client.patch(
            f"/api/teams/{tid}", headers=auth_headers, json={"name": "New", "city": "Graz"}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "New"
        assert body["city"] == "Graz"

    @pytest.mark.asyncio
    async def test_update_is_active_false(self, client, auth_headers):
        created = await client.post("/api/teams", headers=auth_headers, json={"name": "Deact"})
        tid = created.json()["id"]
        resp = await client.patch(
            f"/api/teams/{tid}", headers=auth_headers, json={"is_active": False}
        )
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False

    @pytest.mark.asyncio
    async def test_update_404(self, client, auth_headers):
        resp = await client.patch("/api/teams/missing", headers=auth_headers, json={"name": "x"})
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete(self, client, auth_headers, db):
        created = await client.post("/api/teams", headers=auth_headers, json={"name": "Del"})
        tid = created.json()["id"]
        await db.commit()
        resp = await client.delete(f"/api/teams/{tid}", headers=auth_headers)
        assert resp.status_code == 204
        await db.commit()
        assert (await client.get(f"/api/teams/{tid}", headers=auth_headers)).status_code == 404

    @pytest.mark.asyncio
    async def test_delete_404(self, client, auth_headers):
        resp = await client.delete("/api/teams/missing", headers=auth_headers)
        assert resp.status_code == 404

    # ── members ───────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_add_member(self, client, auth_headers):
        created = await client.post("/api/teams", headers=auth_headers, json={"name": "MemTeam"})
        tid = created.json()["id"]
        resp = await client.post(
            f"/api/teams/{tid}/members",
            headers=auth_headers,
            json={"name": "Carol", "role": "mentor"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "Carol"
        assert body["role"] == "mentor"

    @pytest.mark.asyncio
    async def test_add_member_team_404(self, client, auth_headers):
        resp = await client.post(
            "/api/teams/missing/members", headers=auth_headers, json={"name": "X"}
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_add_member_missing_name_422(self, client, auth_headers):
        created = await client.post("/api/teams", headers=auth_headers, json={"name": "MemTeam2"})
        tid = created.json()["id"]
        resp = await client.post(
            f"/api/teams/{tid}/members", headers=auth_headers, json={"role": "member"}
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_remove_member(self, client, auth_headers, db):
        created = await client.post("/api/teams", headers=auth_headers, json={"name": "RemTeam"})
        tid = created.json()["id"]
        # Add via the dedicated endpoint, whose response carries the member id.
        member = (
            await client.post(
                f"/api/teams/{tid}/members", headers=auth_headers, json={"name": "ToRemove"}
            )
        ).json()
        mid = member["id"]
        await db.commit()

        resp = await client.delete(f"/api/teams/{tid}/members/{mid}", headers=auth_headers)
        assert resp.status_code == 204
        await db.commit()
        # confirm gone
        refetch = (await client.get(f"/api/teams/{tid}", headers=auth_headers)).json()
        assert refetch["members"] == []

    @pytest.mark.asyncio
    async def test_remove_member_404(self, client, auth_headers):
        created = await client.post("/api/teams", headers=auth_headers, json={"name": "RemTeam2"})
        tid = created.json()["id"]
        resp = await client.delete(f"/api/teams/{tid}/members/missing", headers=auth_headers)
        assert resp.status_code == 404

    # ── registrations ─────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_register(self, client, auth_headers):
        season = (
            await client.post(
                "/api/seasons", headers=auth_headers, json={"name": "RS", "year": 2060}
            )
        ).json()
        team = (await client.post("/api/teams", headers=auth_headers, json={"name": "RT"})).json()
        resp = await client.post(
            "/api/teams/registrations",
            headers=auth_headers,
            json={"team_id": team["id"], "season_id": season["id"]},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["confirmed"] is False
        assert body["team_id"] == team["id"]

    @pytest.mark.asyncio
    async def test_register_with_notes(self, client, auth_headers):
        season = (
            await client.post(
                "/api/seasons", headers=auth_headers, json={"name": "RS2", "year": 2061}
            )
        ).json()
        team = (await client.post("/api/teams", headers=auth_headers, json={"name": "RT2"})).json()
        resp = await client.post(
            "/api/teams/registrations",
            headers=auth_headers,
            json={
                "team_id": team["id"],
                "season_id": season["id"],
                "notes": "hello",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["notes"] == "hello"

    @pytest.mark.asyncio
    async def test_register_duplicate_409(self, client, auth_headers):
        season = (
            await client.post(
                "/api/seasons", headers=auth_headers, json={"name": "DupS", "year": 2062}
            )
        ).json()
        team = (await client.post("/api/teams", headers=auth_headers, json={"name": "DupT"})).json()
        payload = {"team_id": team["id"], "season_id": season["id"]}
        first = await client.post("/api/teams/registrations", headers=auth_headers, json=payload)
        assert first.status_code == 201
        second = await client.post("/api/teams/registrations", headers=auth_headers, json=payload)
        assert second.status_code == 409

    @pytest.mark.asyncio
    async def test_register_missing_fields_422(self, client, auth_headers):
        resp = await client.post(
            "/api/teams/registrations", headers=auth_headers, json={"team_id": "abc"}
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_list_registrations(self, client, auth_headers):
        season = (
            await client.post(
                "/api/seasons", headers=auth_headers, json={"name": "LRS", "year": 2063}
            )
        ).json()
        team = (await client.post("/api/teams", headers=auth_headers, json={"name": "LRT"})).json()
        await client.post(
            "/api/teams/registrations",
            headers=auth_headers,
            json={"team_id": team["id"], "season_id": season["id"]},
        )

        resp = await client.get(
            f"/api/teams/registrations?season_id={season['id']}", headers=auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["team_id"] == team["id"]

    @pytest.mark.asyncio
    async def test_list_registrations_filter_by_team(self, client, auth_headers):
        season = (
            await client.post(
                "/api/seasons", headers=auth_headers, json={"name": "LRS2", "year": 2064}
            )
        ).json()
        team_a = (await client.post("/api/teams", headers=auth_headers, json={"name": "A"})).json()
        team_b = (await client.post("/api/teams", headers=auth_headers, json={"name": "B"})).json()
        await client.post(
            "/api/teams/registrations",
            headers=auth_headers,
            json={"team_id": team_a["id"], "season_id": season["id"]},
        )
        await client.post(
            "/api/teams/registrations",
            headers=auth_headers,
            json={"team_id": team_b["id"], "season_id": season["id"]},
        )

        resp = await client.get(
            f"/api/teams/registrations?team_id={team_a['id']}", headers=auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["team_id"] == team_a["id"]

    @pytest.mark.asyncio
    async def test_confirm_registration(self, client, auth_headers):
        season = (
            await client.post(
                "/api/seasons", headers=auth_headers, json={"name": "CRS", "year": 2065}
            )
        ).json()
        team = (await client.post("/api/teams", headers=auth_headers, json={"name": "CRT"})).json()
        reg = (
            await client.post(
                "/api/teams/registrations",
                headers=auth_headers,
                json={"team_id": team["id"], "season_id": season["id"]},
            )
        ).json()
        resp = await client.put(
            f"/api/teams/registrations/{reg['id']}/confirm", headers=auth_headers
        )
        assert resp.status_code == 200
        assert resp.json()["confirmed"] is True

    @pytest.mark.asyncio
    async def test_confirm_registration_404(self, client, auth_headers):
        resp = await client.put("/api/teams/registrations/missing/confirm", headers=auth_headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_requires_auth(self, client):
        resp = await client.get("/api/teams")
        assert resp.status_code == 401
