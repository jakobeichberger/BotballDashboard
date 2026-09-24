"""Paper leftovers: deadline types (official vs internal), deadline reminders,
automatic reviewer assignment and the version diff."""

import io
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select

from modules.dashboard.models import NotificationEvent
from modules.paper_review.deadlines import queue_paper_deadline_reminders
from modules.paper_review.models import Paper, PaperDeadline, ReviewerAssignment
from modules.teams.models import Team, TeamMember, TeamSeasonRegistration
from tests.paper_helpers import PDF, api_upload, headers_for, make_user

MENTOR_PERMS = ("papers:read", "papers:write", "teams:read", "teams:write")


async def _mentor(db, team, email="mentor@test.com"):
    user = await make_user(db, email, MENTOR_PERMS)
    db.add(TeamMember(team_id=team.id, user_id=user.id, name="Mentor", role="mentor"))
    await db.commit()
    return user


async def _create(client, headers, season, team, title="Swarm"):
    resp = await client.post(
        "/api/papers",
        headers=headers,
        json={"season_id": season.id, "team_id": team.id, "title": title},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _pdf_with_text(*lines: str) -> bytes:
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    y = 800
    for line in lines:
        pdf.drawString(72, y, line)
        y -= 20
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


# ── Deadline types ────────────────────────────────────────────────────────────


class TestDeadlineTypes:
    @pytest.mark.asyncio
    async def test_crud_and_validation(self, client, db, auth_headers, season, team):
        body = {
            "season_id": season.id,
            "deadline_type": "internal_draft",
            "due_date": "2026-03-01",
            "label": "Erster Entwurf",
        }
        created = await client.post("/api/papers/deadlines", headers=auth_headers, json=body)
        assert created.status_code == 201, created.text
        deadline_id = created.json()["id"]

        internal_block = await client.post(
            "/api/papers/deadlines", headers=auth_headers, json={**body, "is_hard_block": True}
        )
        assert internal_block.status_code == 422
        unknown = await client.post(
            "/api/papers/deadlines", headers=auth_headers, json={**body, "deadline_type": "x"}
        )
        assert unknown.status_code == 422

        mentor = await _mentor(db, team)
        denied = await client.post("/api/papers/deadlines", headers=headers_for(mentor), json=body)
        assert denied.status_code == 403
        listed = await client.get(
            "/api/papers/deadlines", headers=headers_for(mentor), params={"season_id": season.id}
        )
        assert [d["label"] for d in listed.json()] == ["Erster Entwurf"]

        patched = await client.patch(
            f"/api/papers/deadlines/{deadline_id}",
            headers=auth_headers,
            json={"due_date": "2026-03-02"},
        )
        assert patched.json()["due_date"] == "2026-03-02"
        blocked = await client.patch(
            f"/api/papers/deadlines/{deadline_id}",
            headers=auth_headers,
            json={"is_hard_block": True},
        )
        assert blocked.status_code == 422
        deleted = await client.delete(f"/api/papers/deadlines/{deadline_id}", headers=auth_headers)
        assert deleted.status_code == 204

    @pytest.mark.asyncio
    async def test_official_hard_block_locks_upload(self, client, db, auth_headers, season, team):
        mentor = await _mentor(db, team)
        paper = await _create(client, headers_for(mentor), season, team)
        db.add(
            PaperDeadline(
                season_id=season.id,
                deadline_type="official_submission",
                due_date=date.today() - timedelta(days=1),
                is_hard_block=True,
            )
        )
        await db.commit()
        upload = await client.post(
            f"/api/papers/{paper['id']}/upload",
            headers=headers_for(mentor),
            files={"file": ("p.pdf", PDF, "application/pdf")},
        )
        assert upload.status_code == 403
        # Organizers still override.
        await api_upload(client, auth_headers, paper["id"])

    @pytest.mark.asyncio
    async def test_internal_deadline_only_warns(self, client, db, season, team):
        mentor = await _mentor(db, team)
        paper = await _create(client, headers_for(mentor), season, team)
        db.add(
            PaperDeadline(
                season_id=season.id,
                deadline_type="internal_draft",
                due_date=date.today() - timedelta(days=3),
                label="Entwurf",
            )
        )
        await db.commit()
        await api_upload(client, headers_for(mentor), paper["id"])
        info = (
            await client.get(
                "/api/papers/deadline", headers=headers_for(mentor), params={"season_id": season.id}
            )
        ).json()
        assert info["locked"] is False
        assert [(d["label"], d["passed"]) for d in info["deadlines"]] == [("Entwurf", True)]

    @pytest.mark.asyncio
    async def test_official_final_blocks_revisions(self, client, db, auth_headers, season, team):
        mentor = await _mentor(db, team)
        paper = await _create(client, headers_for(mentor), season, team)
        await api_upload(client, headers_for(mentor), paper["id"])
        assert (
            await client.put(f"/api/papers/{paper['id']}/submit", headers=headers_for(mentor))
        ).status_code == 200
        await client.put(
            f"/api/papers/{paper['id']}/status",
            headers=auth_headers,
            params={"status": "revision_requested"},
        )
        db.add(
            PaperDeadline(
                season_id=season.id,
                deadline_type="official_final",
                due_date=date.today() - timedelta(days=1),
                is_hard_block=True,
            )
        )
        await db.commit()
        upload = await client.post(
            f"/api/papers/{paper['id']}/upload",
            headers=headers_for(mentor),
            files={"file": ("p.pdf", PDF, "application/pdf")},
        )
        assert upload.status_code == 403
        assert "final" in upload.json()["message"]


# ── Reminders ─────────────────────────────────────────────────────────────────


async def _reminders(db):
    rows = await db.execute(
        select(NotificationEvent).where(NotificationEvent.event_type == "paper_deadline_reminder")
    )
    return list(rows.scalars())


class TestDeadlineReminders:
    @pytest.fixture
    async def teams(self, db, season):
        """Three registered teams: no paper, draft paper, submitted paper."""
        rows = []
        for index, status in enumerate((None, "draft", "submitted")):
            team = Team(name=f"Team {index}", country="AT")
            db.add(team)
            await db.flush()
            user = await make_user(db, f"m{index}@test.com", ("papers:read",))
            db.add(TeamMember(team_id=team.id, user_id=user.id, name="M", role="mentor"))
            db.add(TeamSeasonRegistration(team_id=team.id, season_id=season.id))
            if status:
                db.add(Paper(season_id=season.id, team_id=team.id, title="P", status=status))
            rows.append((team, user))
        await db.commit()
        return rows

    @pytest.mark.asyncio
    async def test_submission_reminder_only_to_teams_without_paper(self, db, season, teams):
        today = date(2026, 3, 8)
        db.add(
            PaperDeadline(
                season_id=season.id, deadline_type="official_submission", due_date=date(2026, 3, 15)
            )
        )
        await db.commit()
        assert await queue_paper_deadline_reminders(db, today) == 2
        notified = {uid for r in await _reminders(db) for uid in r.payload["userIds"]}
        assert notified == {teams[0][1].id, teams[1][1].id}
        assert "in 7 days" in (await _reminders(db))[0].payload["title"]
        # Idempotent: a second run the same day queues nothing.
        assert await queue_paper_deadline_reminders(db, today) == 0
        # 3 and 1 day(s) before are reminded again, other days are not.
        assert await queue_paper_deadline_reminders(db, date(2026, 3, 10)) == 0
        assert await queue_paper_deadline_reminders(db, date(2026, 3, 12)) == 2
        assert await queue_paper_deadline_reminders(db, date(2026, 3, 14)) == 2

    @pytest.mark.asyncio
    async def test_season_field_fallback(self, db, season, teams):
        season.paper_submission_deadline = date(2026, 3, 15)
        await db.commit()
        assert await queue_paper_deadline_reminders(db, date(2026, 3, 14)) == 2
        assert "tomorrow" in (await _reminders(db))[0].payload["title"]

    @pytest.mark.asyncio
    async def test_unrequired_paper_not_reminded(self, db, season, teams):
        reg = (
            await db.execute(
                select(TeamSeasonRegistration).where(
                    TeamSeasonRegistration.team_id == teams[0][0].id
                )
            )
        ).scalar_one()
        reg.paper_required = False
        season.paper_submission_deadline = date(2026, 3, 15)
        await db.commit()
        assert await queue_paper_deadline_reminders(db, date(2026, 3, 14)) == 1

    @pytest.mark.asyncio
    async def test_revision_deadline_targets_revision_requested(self, db, season, teams):
        paper = (
            await db.execute(select(Paper).where(Paper.team_id == teams[2][0].id))
        ).scalar_one()
        paper.status = "revision_requested"
        db.add(
            PaperDeadline(
                season_id=season.id, deadline_type="internal_revision", due_date=date(2026, 3, 20)
            )
        )
        await db.commit()
        assert await queue_paper_deadline_reminders(db, date(2026, 3, 17)) == 1
        [reminder] = await _reminders(db)
        assert reminder.payload["userIds"] == [teams[2][1].id]
        assert "revised version" in reminder.payload["message"]

    @pytest.mark.asyncio
    async def test_review_deadline_targets_open_reviewers(self, db, season, teams):
        paper = (
            await db.execute(select(Paper).where(Paper.team_id == teams[2][0].id))
        ).scalar_one()
        busy = await make_user(db, "busy@test.com", ("papers:review",))
        done = await make_user(db, "done@test.com", ("papers:review",))
        db.add(ReviewerAssignment(paper_id=paper.id, reviewer_id=busy.id, status="pending"))
        db.add(ReviewerAssignment(paper_id=paper.id, reviewer_id=done.id, status="completed"))
        db.add(
            PaperDeadline(
                season_id=season.id, deadline_type="internal_review", due_date=date(2026, 3, 11)
            )
        )
        await db.commit()
        assert await queue_paper_deadline_reminders(db, date(2026, 3, 10)) == 1
        [reminder] = await _reminders(db)
        assert reminder.payload["userId"] == busy.id


# ── Automatic reviewer assignment ─────────────────────────────────────────────


class TestAutoAssign:
    @pytest.fixture
    async def setup(self, db, season):
        teams = []
        for index, school in enumerate(("HTL Wien", "BG Graz", "HTL Linz")):
            team = Team(name=f"Team {index}", school=school, country="AT")
            db.add(team)
            await db.flush()
            teams.append(team)
            db.add(
                Paper(
                    season_id=season.id,
                    team_id=team.id,
                    title=f"Paper {index}",
                    status="submitted",
                    current_version=1,
                    created_at=datetime.now(UTC) + timedelta(seconds=index),
                )
            )
        await db.commit()
        reviewers = [
            await make_user(db, f"r{index}@test.com", ("papers:review",)) for index in range(3)
        ]
        # Reviewer 0 mentors a team of HTL Wien's school (another team there).
        wien2 = Team(name="Wien 2", school="htl wien ", country="AT")
        db.add(wien2)
        await db.flush()
        db.add(TeamMember(team_id=wien2.id, user_id=reviewers[0].id, name="R0", role="mentor"))
        await db.commit()
        return teams, reviewers

    async def _papers(self, db):
        return {p.id: p for p in (await db.execute(select(Paper))).scalars()}

    @pytest.mark.asyncio
    async def test_balanced_and_conflict_free(self, client, db, auth_headers, season, setup):
        teams, reviewers = setup
        resp = await client.post(
            "/api/papers/auto-assign",
            headers=auth_headers,
            json={"season_id": season.id, "reviewers_per_paper": 2},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["unfilled"] == []
        assert len(data["assignments"]) == 6

        rows = list((await db.execute(select(ReviewerAssignment))).scalars())
        per_reviewer: dict[str, int] = {}
        per_paper: dict[str, set] = {}
        for row in rows:
            per_reviewer[row.reviewer_id] = per_reviewer.get(row.reviewer_id, 0) + 1
            per_paper.setdefault(row.paper_id, set()).add(row.reviewer_id)
        assert sorted(per_reviewer.values()) == [2, 2, 2]
        assert all(len(r) == 2 for r in per_paper.values())
        wien_paper = next(p for p in (await self._papers(db)).values() if p.team_id == teams[0].id)
        assert reviewers[0].id not in per_paper[wien_paper.id]
        assert wien_paper.status == "under_review"

    @pytest.mark.asyncio
    async def test_dry_run_creates_nothing(self, client, db, auth_headers, season, setup):
        resp = await client.post(
            "/api/papers/auto-assign",
            headers=auth_headers,
            json={"season_id": season.id, "reviewers_per_paper": 1, "dry_run": True},
        )
        assert resp.json()["dry_run"] is True
        assert len(resp.json()["assignments"]) == 3
        assert list((await db.execute(select(ReviewerAssignment))).scalars()) == []

    @pytest.mark.asyncio
    async def test_existing_assignments_count(self, client, db, auth_headers, season, setup):
        teams, reviewers = setup
        papers = list((await self._papers(db)).values())
        # Reviewer 1 already has an open review elsewhere: gets fewer new ones.
        db.add(ReviewerAssignment(paper_id=papers[1].id, reviewer_id=reviewers[1].id))
        await db.commit()
        resp = await client.post(
            "/api/papers/auto-assign",
            headers=auth_headers,
            json={"season_id": season.id, "reviewers_per_paper": 1},
        )
        assigned = [a["reviewer_id"] for a in resp.json()["assignments"]]
        assert len(assigned) == 2  # papers[1] was already covered
        assert reviewers[1].id not in assigned

    @pytest.mark.asyncio
    async def test_unfilled_when_pool_too_small(self, client, auth_headers, season, setup):
        teams, reviewers = setup
        resp = await client.post(
            "/api/papers/auto-assign",
            headers=auth_headers,
            json={
                "season_id": season.id,
                "reviewers_per_paper": 2,
                "reviewer_ids": [reviewers[0].id],
            },
        )
        data = resp.json()
        # Reviewer 0 takes two papers; the Wien paper cannot get anyone.
        assert len(data["assignments"]) == 2
        missing = {u["paper_title"]: u["missing"] for u in data["unfilled"]}
        assert missing == {"Paper 0": 2, "Paper 1": 1, "Paper 2": 1}

    @pytest.mark.asyncio
    async def test_pool_validation_and_permission(self, client, db, auth_headers, season, setup):
        outsider = await make_user(db, "outsider@test.com", ("papers:read",))
        resp = await client.post(
            "/api/papers/auto-assign",
            headers=auth_headers,
            json={"season_id": season.id, "reviewer_ids": [outsider.id]},
        )
        assert resp.status_code == 422
        denied = await client.post(
            "/api/papers/auto-assign",
            headers=headers_for(outsider),
            json={"season_id": season.id},
        )
        assert denied.status_code == 403


# ── Version diff ──────────────────────────────────────────────────────────────


class TestVersionDiff:
    @pytest.mark.asyncio
    async def test_text_diff_between_versions(self, client, db, season, team):
        mentor = await _mentor(db, team)
        headers = headers_for(mentor)
        paper = await _create(client, headers, season, team)
        await api_upload(
            client,
            headers,
            paper["id"],
            _pdf_with_text("Abstract", "We built a robot.", "Results are good."),
        )
        await api_upload(
            client,
            headers,
            paper["id"],
            _pdf_with_text("Abstract", "We built two robots.", "Results are good."),
        )
        resp = await client.get(f"/api/papers/{paper['id']}/versions/diff", headers=headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["text_available"] is True
        assert data["from_version"]["version_number"] == 1
        assert data["to_version"]["version_number"] == 2
        assert data["to_version"]["pages"] == 1
        assert "-We built a robot." in data["diff"]
        assert "+We built two robots." in data["diff"]
        assert (data["added"], data["removed"]) == (1, 1)

    @pytest.mark.asyncio
    async def test_no_text_falls_back_to_metadata(self, client, auth_headers, season, team):
        paper = await _create(client, auth_headers, season, team)
        await api_upload(client, auth_headers, paper["id"])
        await api_upload(client, auth_headers, paper["id"], PDF + b" v2", name="v2.pdf")
        resp = await client.get(
            f"/api/papers/{paper['id']}/versions/diff",
            headers=auth_headers,
            params={"from_version": 1, "to_version": 2},
        )
        data = resp.json()
        assert data["text_available"] is False
        assert data["reason"]
        assert data["to_version"]["file_name"] == "v2.pdf"
        assert data["diff"] == []

    @pytest.mark.asyncio
    async def test_validation_and_access(self, client, db, auth_headers, season, team):
        paper = await _create(client, auth_headers, season, team)
        await api_upload(client, auth_headers, paper["id"])
        url = f"/api/papers/{paper['id']}/versions/diff"
        same = await client.get(url, headers=auth_headers, params={"from_version": 1})
        assert same.status_code == 422
        only_one = await client.get(url, headers=auth_headers)
        assert only_one.status_code == 404

        rival = Team(name="Rival", country="AT")
        db.add(rival)
        await db.commit()
        mentor = await _mentor(db, rival, "rival@test.com")
        denied = await client.get(url, headers=headers_for(mentor))
        assert denied.status_code in (403, 404)
