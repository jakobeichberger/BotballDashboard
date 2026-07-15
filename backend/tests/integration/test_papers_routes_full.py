"""Integration tests for the Paper Review API routes (/api/papers/*).

Exercises every endpoint end-to-end through the ASGI client:
  GET    /api/papers                       (list + filters)
  POST   /api/papers                       (create)
  GET    /api/papers/{id}                   (get)
  PATCH  /api/papers/{id}                   (update)
  POST   /api/papers/{id}/upload            (multipart file upload)
  GET    /api/papers/{id}/download          (file download)
  PUT    /api/papers/{id}/submit            (submit)
  PUT    /api/papers/{id}/status            (admin status change)
  POST   /api/papers/{id}/assignments       (assign reviewer)
  PUT    /api/papers/{id}/reviews           (save / submit review)
  GET    /api/papers/{id}/reviews           (list reviews)

The admin_user fixture is a superuser, so it bypasses all permission checks
(papers:read / write / admin / review).
"""
import pytest


def _paper_body(season, team, **overrides):
    body = {
        "season_id": season.id,
        "team_id": team.id,
        "title": "Autonomous Line Following",
        "abstract": "An exploration of PID line-following controllers.",
    }
    body.update(overrides)
    return body


async def _create_paper(client, auth_headers, season, team, **overrides):
    resp = await client.post(
        "/api/papers",
        headers=auth_headers,
        json=_paper_body(season, team, **overrides),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ── create / get / list ──────────────────────────────────────────────────────

class TestCreateGetList:
    @pytest.mark.asyncio
    async def test_create_paper(self, client, auth_headers, season, team):
        resp = await client.post(
            "/api/papers", headers=auth_headers, json=_paper_body(season, team)
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["title"] == "Autonomous Line Following"
        assert data["status"] == "draft"
        assert data["revision_number"] == 1
        assert data["reviews"] == []
        assert data["assignments"] == []
        assert data["season_id"] == season.id
        assert data["team_id"] == team.id

    @pytest.mark.asyncio
    async def test_create_requires_auth(self, client, season, team):
        resp = await client.post("/api/papers", json=_paper_body(season, team))
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_create_missing_required_field_422(self, client, auth_headers, season):
        # team_id missing
        resp = await client.post(
            "/api/papers",
            headers=auth_headers,
            json={"season_id": season.id, "title": "No team"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_get_paper(self, client, auth_headers, season, team):
        created = await _create_paper(client, auth_headers, season, team)
        resp = await client.get(f"/api/papers/{created['id']}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["id"] == created["id"]

    @pytest.mark.asyncio
    async def test_get_paper_404(self, client, auth_headers):
        resp = await client.get("/api/papers/nope", headers=auth_headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_list_papers(self, client, auth_headers, season, team):
        await _create_paper(client, auth_headers, season, team, title="One")
        await _create_paper(client, auth_headers, season, team, title="Two")
        resp = await client.get("/api/papers", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 2
        # PaperListItem shape – no nested reviews/assignments
        assert "title" in data[0]
        assert "reviews" not in data[0]

    @pytest.mark.asyncio
    async def test_list_filter_by_status(self, client, auth_headers, season, team):
        # Two freshly created papers default to "draft".
        a = await _create_paper(client, auth_headers, season, team, title="Draft A")
        b = await _create_paper(client, auth_headers, season, team, title="Draft B")

        resp = await client.get(
            "/api/papers", headers=auth_headers, params={"status": "draft"}
        )
        assert resp.status_code == 200
        data = resp.json()
        ids = {item["id"] for item in data}
        assert {a["id"], b["id"]} <= ids
        assert all(item["status"] == "draft" for item in data)

        # A status with no matching rows returns an empty list.
        empty = await client.get(
            "/api/papers", headers=auth_headers, params={"status": "rejected"}
        )
        assert empty.status_code == 200
        assert empty.json() == []

    @pytest.mark.asyncio
    async def test_list_filter_by_team(self, client, auth_headers, season, team):
        # create another team via API
        team_resp = await client.post(
            "/api/teams", headers=auth_headers, json={"name": "Other", "country": "DE"}
        )
        other_team_id = team_resp.json()["id"]

        await _create_paper(client, auth_headers, season, team)
        await client.post(
            "/api/papers",
            headers=auth_headers,
            json=_paper_body(season, team, team_id=other_team_id, title="Other team"),
        )

        resp = await client.get(
            "/api/papers", headers=auth_headers, params={"team_id": other_team_id}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["team_id"] == other_team_id


# ── update ───────────────────────────────────────────────────────────────────

class TestUpdate:
    @pytest.mark.asyncio
    async def test_patch_paper(self, client, auth_headers, season, team):
        created = await _create_paper(client, auth_headers, season, team)
        resp = await client.patch(
            f"/api/papers/{created['id']}",
            headers=auth_headers,
            json={"title": "Renamed", "notes": "reviewer note"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Renamed"
        assert data["notes"] == "reviewer note"

    @pytest.mark.asyncio
    async def test_patch_partial_keeps_other_fields(self, client, auth_headers, season, team):
        created = await _create_paper(client, auth_headers, season, team)
        resp = await client.patch(
            f"/api/papers/{created['id']}",
            headers=auth_headers,
            json={"notes": "only notes"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == created["title"]  # unchanged
        assert data["notes"] == "only notes"

    @pytest.mark.asyncio
    async def test_patch_404(self, client, auth_headers):
        resp = await client.patch(
            "/api/papers/missing", headers=auth_headers, json={"title": "x"}
        )
        assert resp.status_code == 404


# ── upload / download ────────────────────────────────────────────────────────

class TestUploadDownload:
    @pytest.mark.asyncio
    async def test_upload_then_download(self, client, auth_headers, season, team):
        created = await _create_paper(client, auth_headers, season, team)
        pid = created["id"]
        content = b"%PDF-1.5 integration test pdf"

        up = await client.post(
            f"/api/papers/{pid}/upload",
            headers=auth_headers,
            files={"file": ("submission.pdf", content, "application/pdf")},
        )
        assert up.status_code == 200, up.text
        data = up.json()
        assert data["file_name"] == "submission.pdf"
        assert data["file_size_bytes"] == len(content)
        assert data["file_url"] == f"/api/papers/{pid}/download"

        dl = await client.get(f"/api/papers/{pid}/download", headers=auth_headers)
        assert dl.status_code == 200
        assert dl.content == content
        assert "application/pdf" in dl.headers["content-type"]

    @pytest.mark.asyncio
    async def test_download_without_upload_404(self, client, auth_headers, season, team):
        created = await _create_paper(client, auth_headers, season, team)
        resp = await client.get(
            f"/api/papers/{created['id']}/download", headers=auth_headers
        )
        assert resp.status_code == 404


# ── submit ───────────────────────────────────────────────────────────────────

class TestSubmit:
    @pytest.mark.asyncio
    async def test_submit_paper(self, client, auth_headers, season, team):
        created = await _create_paper(client, auth_headers, season, team)
        resp = await client.put(
            f"/api/papers/{created['id']}/submit", headers=auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "submitted"
        assert data["submitted_at"] is not None

    @pytest.mark.asyncio
    async def test_double_submit_conflict(self, client, auth_headers, season, team):
        created = await _create_paper(client, auth_headers, season, team)
        await client.put(f"/api/papers/{created['id']}/submit", headers=auth_headers)
        resp = await client.put(
            f"/api/papers/{created['id']}/submit", headers=auth_headers
        )
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_submit_404(self, client, auth_headers):
        resp = await client.put("/api/papers/missing/submit", headers=auth_headers)
        assert resp.status_code == 404


# ── status (admin) ───────────────────────────────────────────────────────────

class TestStatus:
    @pytest.mark.asyncio
    async def test_set_status_accepted(self, client, auth_headers, season, team):
        created = await _create_paper(client, auth_headers, season, team)
        resp = await client.put(
            f"/api/papers/{created['id']}/status",
            headers=auth_headers,
            params={"status": "accepted"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "accepted"

    @pytest.mark.asyncio
    async def test_set_status_revision_requested_bumps_revision(
        self, client, auth_headers, season, team
    ):
        created = await _create_paper(client, auth_headers, season, team)
        assert created["revision_number"] == 1
        resp = await client.put(
            f"/api/papers/{created['id']}/status",
            headers=auth_headers,
            params={"status": "revision_requested"},
        )
        assert resp.status_code == 200
        assert resp.json()["revision_number"] == 2

    @pytest.mark.asyncio
    async def test_status_404(self, client, auth_headers):
        resp = await client.put(
            "/api/papers/missing/status",
            headers=auth_headers,
            params={"status": "accepted"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_status_missing_query_param_422(self, client, auth_headers, season, team):
        created = await _create_paper(client, auth_headers, season, team)
        resp = await client.put(
            f"/api/papers/{created['id']}/status", headers=auth_headers
        )
        assert resp.status_code == 422


# ── reviewer assignments ─────────────────────────────────────────────────────

class TestAssignments:
    @pytest.mark.asyncio
    async def test_assign_reviewer(self, client, auth_headers, season, team, admin_user):
        created = await _create_paper(client, auth_headers, season, team)
        resp = await client.post(
            f"/api/papers/{created['id']}/assignments",
            headers=auth_headers,
            json={"reviewer_id": admin_user.id},
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["reviewer_id"] == admin_user.id
        assert data["paper_id"] == created["id"]

    @pytest.mark.asyncio
    async def test_duplicate_assignment_conflict(
        self, client, auth_headers, season, team, admin_user
    ):
        created = await _create_paper(client, auth_headers, season, team)
        await client.post(
            f"/api/papers/{created['id']}/assignments",
            headers=auth_headers,
            json={"reviewer_id": admin_user.id},
        )
        resp = await client.post(
            f"/api/papers/{created['id']}/assignments",
            headers=auth_headers,
            json={"reviewer_id": admin_user.id},
        )
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_assign_to_missing_paper_404(self, client, auth_headers, admin_user):
        resp = await client.post(
            "/api/papers/missing/assignments",
            headers=auth_headers,
            json={"reviewer_id": admin_user.id},
        )
        assert resp.status_code == 404


# ── reviews ──────────────────────────────────────────────────────────────────

class TestReviews:
    @pytest.mark.asyncio
    async def test_save_review_after_assignment(
        self, client, auth_headers, season, team, admin_user
    ):
        created = await _create_paper(client, auth_headers, season, team)
        await client.post(
            f"/api/papers/{created['id']}/assignments",
            headers=auth_headers,
            json={"reviewer_id": admin_user.id},
        )
        resp = await client.put(
            f"/api/papers/{created['id']}/reviews",
            headers=auth_headers,
            json={
                "score_content": 8.0,
                "score_methodology": 6.0,
                "comments": "Solid",
                "recommendation": "accept",
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["total_score"] == 7.0  # avg(8, 6)
        assert data["comments"] == "Solid"
        assert data["is_submitted"] is False

    @pytest.mark.asyncio
    async def test_review_without_assignment_403(
        self, client, auth_headers, season, team
    ):
        created = await _create_paper(client, auth_headers, season, team)
        # no assignment for the current (admin) user
        resp = await client.put(
            f"/api/papers/{created['id']}/reviews",
            headers=auth_headers,
            json={"score_content": 5.0},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_submit_review_marks_submitted(
        self, client, auth_headers, season, team, admin_user
    ):
        created = await _create_paper(client, auth_headers, season, team)
        await client.post(
            f"/api/papers/{created['id']}/assignments",
            headers=auth_headers,
            json={"reviewer_id": admin_user.id},
        )
        resp = await client.put(
            f"/api/papers/{created['id']}/reviews",
            headers=auth_headers,
            params={"submit": "true"},
            json={"score_content": 9.0, "recommendation": "accept"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_submitted"] is True
        assert data["submitted_at"] is not None
        assert data["total_score"] == 9.0
        assert data["recommendation"] == "accept"

    @pytest.mark.asyncio
    async def test_review_idempotent_update(
        self, client, auth_headers, season, team, admin_user
    ):
        created = await _create_paper(client, auth_headers, season, team)
        await client.post(
            f"/api/papers/{created['id']}/assignments",
            headers=auth_headers,
            json={"reviewer_id": admin_user.id},
        )
        first = await client.put(
            f"/api/papers/{created['id']}/reviews",
            headers=auth_headers,
            json={"score_content": 5.0},
        )
        second = await client.put(
            f"/api/papers/{created['id']}/reviews",
            headers=auth_headers,
            json={"score_methodology": 7.0},
        )
        assert first.json()["id"] == second.json()["id"]
        assert second.json()["total_score"] == 6.0  # avg(5, 7)

    @pytest.mark.asyncio
    async def test_list_reviews(self, client, auth_headers, season, team, admin_user):
        created = await _create_paper(client, auth_headers, season, team)
        await client.post(
            f"/api/papers/{created['id']}/assignments",
            headers=auth_headers,
            json={"reviewer_id": admin_user.id},
        )
        await client.put(
            f"/api/papers/{created['id']}/reviews",
            headers=auth_headers,
            json={"score_content": 8.0},
        )
        resp = await client.get(
            f"/api/papers/{created['id']}/reviews", headers=auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["score_content"] == 8.0

    @pytest.mark.asyncio
    async def test_list_reviews_empty(self, client, auth_headers, season, team):
        created = await _create_paper(client, auth_headers, season, team)
        resp = await client.get(
            f"/api/papers/{created['id']}/reviews", headers=auth_headers
        )
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_list_reviews_404(self, client, auth_headers):
        resp = await client.get("/api/papers/missing/reviews", headers=auth_headers)
        assert resp.status_code == 404


# ── full lifecycle ───────────────────────────────────────────────────────────

class TestFullLifecycle:
    @pytest.mark.asyncio
    async def test_draft_to_accepted_flow(
        self, client, auth_headers, season, team, admin_user
    ):
        # draft
        created = await _create_paper(client, auth_headers, season, team)
        pid = created["id"]
        assert created["status"] == "draft"

        # submit -> submitted
        r = await client.put(f"/api/papers/{pid}/submit", headers=auth_headers)
        assert r.json()["status"] == "submitted"

        # assign + review + submit
        await client.post(
            f"/api/papers/{pid}/assignments",
            headers=auth_headers,
            json={"reviewer_id": admin_user.id},
        )
        rev = await client.put(
            f"/api/papers/{pid}/reviews",
            headers=auth_headers,
            params={"submit": "true"},
            json={"score_content": 8.0, "recommendation": "accept"},
        )
        assert rev.json()["is_submitted"] is True

        # admin moves the paper under review, then accepts it
        ur = await client.put(
            f"/api/papers/{pid}/status",
            headers=auth_headers,
            params={"status": "under_review"},
        )
        assert ur.json()["status"] == "under_review"

        acc = await client.put(
            f"/api/papers/{pid}/status",
            headers=auth_headers,
            params={"status": "accepted"},
        )
        assert acc.json()["status"] == "accepted"
