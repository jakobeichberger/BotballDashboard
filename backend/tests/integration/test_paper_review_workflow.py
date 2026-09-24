"""Paper review workflow (audit 2026-09, section C "Paper").

Covers: team feedback visibility, deadline enforcement with admin override,
PDF versioning, one paper per team and season, the status workflow
(under_review / resubmitted / review locking), AI disqualification and format
deductions, reviewer conflict checks, the five spec criteria, mentor linking,
statistics and the per-review CSV export.
"""

import csv
import io
from datetime import UTC, date, datetime, timedelta

import pytest

from modules.paper_review.service import deadline_cutoff
from modules.teams.models import Team, TeamMember
from tests.paper_helpers import (
    FULL_SCORES,
    PDF,
    api_upload,
    api_upload_and_submit,
    headers_for,
    make_user,
)

MENTOR_PERMS = ("papers:read", "papers:write", "teams:read", "teams:write")
SUBMITTABLE = {**FULL_SCORES, "recommendation": "revision_minor"}


async def _mentor(db, team, email="mentor@test.com"):
    user = await make_user(db, email, MENTOR_PERMS)
    db.add(TeamMember(team_id=team.id, user_id=user.id, name="Mentor", role="mentor"))
    await db.commit()
    return user


async def _reviewer(db, email="reviewer@test.com"):
    return await make_user(db, email, ("papers:read", "papers:review"))


async def _create(client, headers, season, team, **extra):
    resp = await client.post(
        "/api/papers",
        headers=headers,
        json={"season_id": season.id, "team_id": team.id, "title": "Swarm", **extra},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _assign(client, auth_headers, pid, reviewer_id):
    return await client.post(
        f"/api/papers/{pid}/assignments", headers=auth_headers, json={"reviewer_id": reviewer_id}
    )


async def _review(client, headers, pid, body=None, submit=True):
    return await client.put(
        f"/api/papers/{pid}/reviews",
        headers=headers,
        params={"submit": str(submit).lower()},
        json=body if body is not None else SUBMITTABLE,
    )


async def _set_status(client, auth_headers, pid, status, **params):
    resp = await client.put(
        f"/api/papers/{pid}/status", headers=auth_headers, params={"status": status, **params}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.fixture
async def submitted(client, auth_headers, season, team):
    paper = await _create(client, auth_headers, season, team)
    await api_upload_and_submit(client, auth_headers, paper["id"])
    return paper["id"]


# ── 1. Team feedback ──────────────────────────────────────────────────────────


class TestTeamFeedback:
    @pytest.mark.asyncio
    async def test_feedback_hidden_until_decided_then_anonymous(
        self, client, db, auth_headers, season, team, submitted
    ):
        mentor = await _mentor(db, team)
        r1, r2 = await _reviewer(db, "r1@test.com"), await _reviewer(db, "r2@test.com")
        for r in (r1, r2):
            assert (await _assign(client, auth_headers, submitted, r.id)).status_code == 201
        body = {**SUBMITTABLE, "comment_results": "Needs data", "revision_notes": "Add plots"}
        assert (await _review(client, headers_for(r1), submitted, body)).status_code == 200
        # r2 only saves a draft: drafts are never shown to the team.
        await _review(client, headers_for(r2), submitted, {"comments": "DRAFT"}, submit=False)

        before = await client.get(f"/api/papers/{submitted}", headers=headers_for(mentor))
        assert before.status_code == 200
        assert before.json()["feedback"] == []
        feedback = await client.get(
            f"/api/papers/{submitted}/feedback", headers=headers_for(mentor)
        )
        assert feedback.json() == []

        await _set_status(client, auth_headers, submitted, "revision_requested")

        after = (await client.get(f"/api/papers/{submitted}", headers=headers_for(mentor))).json()
        assert after["reviews"] == []
        assert len(after["feedback"]) == 1
        item = after["feedback"][0]
        assert item["comment_results"] == "Needs data"
        assert item["revision_notes"] == "Add plots"
        assert item["score_format"] == FULL_SCORES["score_format"]
        assert "reviewer_id" not in item
        assert "private_notes" not in item

        # Earlier rounds stay visible while the next round is under review.
        await api_upload_and_submit(client, headers_for(mentor), submitted)
        again = (await client.get(f"/api/papers/{submitted}", headers=headers_for(mentor))).json()
        assert again["status"] == "resubmitted"
        assert len(again["feedback"]) == 1

    @pytest.mark.asyncio
    async def test_other_teams_cannot_read_feedback(
        self, client, db, auth_headers, season, team, submitted
    ):
        other = Team(name="Other", country="AT")
        db.add(other)
        await db.commit()
        outsider = await _mentor(db, other, "outsider@test.com")
        resp = await client.get(f"/api/papers/{submitted}/feedback", headers=headers_for(outsider))
        assert resp.status_code == 403


# ── 2. Deadline ───────────────────────────────────────────────────────────────


class TestDeadline:
    def test_cutoff_is_end_of_day_in_event_timezone(self):
        # 15 March 2026 in Vienna (CET, UTC+1) ends at 23:00 UTC.
        assert deadline_cutoff(date(2026, 3, 15), "Europe/Vienna") == datetime(
            2026, 3, 15, 23, 0, tzinfo=UTC
        )
        # Summer time (CEST, UTC+2).
        assert deadline_cutoff(date(2026, 7, 1), "Europe/Vienna") == datetime(
            2026, 7, 1, 22, 0, tzinfo=UTC
        )
        # Unknown zones fall back to the default instead of failing.
        assert deadline_cutoff(date(2026, 3, 15), "Nowhere/Nope").hour == 23

    @pytest.mark.asyncio
    async def test_after_deadline_team_is_locked_admin_overrides(
        self, client, db, auth_headers, season, team
    ):
        mentor = await _mentor(db, team)
        paper = await _create(client, headers_for(mentor), season, team)
        season.paper_submission_deadline = date.today() - timedelta(days=2)
        await db.commit()

        info = await client.get(
            "/api/papers/deadline", headers=headers_for(mentor), params={"season_id": season.id}
        )
        assert info.status_code == 200
        assert info.json()["passed"] is True
        assert info.json()["locked"] is True
        detail = (
            await client.get(f"/api/papers/{paper['id']}", headers=headers_for(mentor))
        ).json()
        assert detail["deadline"]["locked"] is True

        upload = await client.post(
            f"/api/papers/{paper['id']}/upload",
            headers=headers_for(mentor),
            files={"file": ("p.pdf", PDF, "application/pdf")},
        )
        assert upload.status_code == 403
        assert "deadline" in upload.json()["message"]

        # papers:admin overrides the cut-off.
        admin_info = await client.get(
            "/api/papers/deadline", headers=auth_headers, params={"season_id": season.id}
        )
        assert admin_info.json()["locked"] is False
        await api_upload(client, auth_headers, paper["id"])
        submit = await client.put(f"/api/papers/{paper['id']}/submit", headers=headers_for(mentor))
        assert submit.status_code == 403
        assert (
            await client.put(f"/api/papers/{paper['id']}/submit", headers=auth_headers)
        ).status_code == 200

    @pytest.mark.asyncio
    async def test_create_after_deadline_rejected_for_team(self, client, db, season, team):
        mentor = await _mentor(db, team)
        season.paper_submission_deadline = date.today() - timedelta(days=2)
        await db.commit()
        resp = await client.post(
            "/api/papers",
            headers=headers_for(mentor),
            json={"season_id": season.id, "team_id": team.id, "title": "Late"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_requested_revision_is_not_blocked_by_deadline(
        self, client, db, auth_headers, season, team, submitted
    ):
        mentor = await _mentor(db, team)
        await _set_status(client, auth_headers, submitted, "revision_requested")
        season.paper_submission_deadline = date.today() - timedelta(days=2)
        await db.commit()
        resubmitted = await api_upload_and_submit(client, headers_for(mentor), submitted)
        assert resubmitted["status"] == "resubmitted"


# ── 3. Versioning ─────────────────────────────────────────────────────────────


class TestVersioning:
    @pytest.mark.asyncio
    async def test_each_upload_is_a_new_version(self, client, auth_headers, season, team):
        paper = await _create(client, auth_headers, season, team)
        pid = paper["id"]
        await api_upload(client, auth_headers, pid, b"%PDF-1 first", "first.pdf")
        data = await api_upload(client, auth_headers, pid, b"%PDF-1 second", "second.pdf")
        assert data["current_version"] == 2
        assert [v["version_number"] for v in data["versions"]] == [1, 2]

        versions = await client.get(f"/api/papers/{pid}/versions", headers=auth_headers)
        assert [v["file_name"] for v in versions.json()] == ["first.pdf", "second.pdf"]

        latest = await client.get(f"/api/papers/{pid}/download", headers=auth_headers)
        assert latest.content == b"%PDF-1 second"
        first = await client.get(
            f"/api/papers/{pid}/download", headers=auth_headers, params={"version": 1}
        )
        assert first.content == b"%PDF-1 first"
        missing = await client.get(
            f"/api/papers/{pid}/download", headers=auth_headers, params={"version": 9}
        )
        assert missing.status_code == 404

    @pytest.mark.asyncio
    async def test_no_upload_while_under_review(self, client, auth_headers, submitted):
        resp = await client.post(
            f"/api/papers/{submitted}/upload",
            headers=auth_headers,
            files={"file": ("p.pdf", PDF, "application/pdf")},
        )
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_review_records_the_version(self, client, db, auth_headers, submitted):
        reviewer = await _reviewer(db)
        await _assign(client, auth_headers, submitted, reviewer.id)
        await _set_status(client, auth_headers, submitted, "revision_requested")
        await api_upload_and_submit(client, auth_headers, submitted)
        review = await _review(client, headers_for(reviewer), submitted)
        assert review.json()["version_number"] == 2
        assert review.json()["revision_number"] == 2


# ── 4. One paper per team and season ──────────────────────────────────────────


class TestOnePaperPerTeam:
    @pytest.mark.asyncio
    async def test_second_paper_conflicts(self, client, auth_headers, season, team):
        await _create(client, auth_headers, season, team)
        resp = await client.post(
            "/api/papers",
            headers=auth_headers,
            json={"season_id": season.id, "team_id": team.id, "title": "Again"},
        )
        assert resp.status_code == 409


# ── 5. Workflow ───────────────────────────────────────────────────────────────


class TestWorkflow:
    @pytest.mark.asyncio
    async def test_first_assignment_starts_review(self, client, db, auth_headers, submitted):
        reviewer = await _reviewer(db)
        await _assign(client, auth_headers, submitted, reviewer.id)
        paper = (await client.get(f"/api/papers/{submitted}", headers=auth_headers)).json()
        assert paper["status"] == "under_review"
        assert paper["assignments"][0]["status"] == "pending"
        assert paper["assignments"][0]["version_number"] == 1

    @pytest.mark.asyncio
    async def test_resubmission_resets_assignments(self, client, db, auth_headers, submitted):
        reviewer = await _reviewer(db)
        await _assign(client, auth_headers, submitted, reviewer.id)
        await _review(client, headers_for(reviewer), submitted)
        paper = (await client.get(f"/api/papers/{submitted}", headers=auth_headers)).json()
        assert paper["assignments"][0]["status"] == "completed"

        await _set_status(client, auth_headers, submitted, "revision_requested")
        resubmitted = await api_upload_and_submit(client, auth_headers, submitted)
        assert resubmitted["status"] == "resubmitted"
        assignment = resubmitted["assignments"][0]
        assert (assignment["status"], assignment["version_number"]) == ("pending", 2)
        assert assignment["completed_at"] is None

        # Starting the new review moves the paper under review again.
        await _review(client, headers_for(reviewer), submitted, {"score_content": 5}, False)
        paper = (await client.get(f"/api/papers/{submitted}", headers=auth_headers)).json()
        assert paper["status"] == "under_review"
        assert paper["assignments"][0]["status"] == "in_progress"

    @pytest.mark.asyncio
    async def test_submitted_review_locked_until_reopened(
        self, client, db, auth_headers, submitted
    ):
        reviewer = await _reviewer(db)
        await _assign(client, auth_headers, submitted, reviewer.id)
        review = (await _review(client, headers_for(reviewer), submitted)).json()

        locked = await _review(client, headers_for(reviewer), submitted, {"score_content": 1})
        assert locked.status_code == 409

        reopened = await client.post(
            f"/api/papers/{submitted}/reviews/{review['id']}/reopen", headers=auth_headers
        )
        assert reopened.status_code == 200
        assert reopened.json()["is_submitted"] is False
        edited = await _review(
            client, headers_for(reviewer), submitted, {"score_content": 1}, False
        )
        assert edited.status_code == 200
        assert edited.json()["score_content"] == 1

    @pytest.mark.asyncio
    async def test_reviews_locked_after_finalize(self, client, db, auth_headers, submitted):
        reviewer = await _reviewer(db)
        await _assign(client, auth_headers, submitted, reviewer.id)
        review = (await _review(client, headers_for(reviewer), submitted)).json()
        assert (
            await client.post(f"/api/papers/{submitted}/finalize", headers=auth_headers)
        ).status_code == 200

        reopen = await client.post(
            f"/api/papers/{submitted}/reviews/{review['id']}/reopen", headers=auth_headers
        )
        assert reopen.status_code == 409

    @pytest.mark.asyncio
    async def test_reviewer_cannot_reopen(self, client, db, auth_headers, submitted):
        reviewer = await _reviewer(db)
        await _assign(client, auth_headers, submitted, reviewer.id)
        review = (await _review(client, headers_for(reviewer), submitted)).json()
        resp = await client.post(
            f"/api/papers/{submitted}/reviews/{review['id']}/reopen",
            headers=headers_for(reviewer),
        )
        assert resp.status_code == 403


# ── 6. AI misuse and format deductions ────────────────────────────────────────


class TestOutcomes:
    @pytest.mark.asyncio
    async def test_disqualified_ai_scores_zero_and_blocks_revision(
        self, client, db, auth_headers, submitted
    ):
        paper = await _set_status(
            client, auth_headers, submitted, "disqualified_ai", reason="Generated text"
        )
        assert paper["status"] == "disqualified_ai"
        assert paper["final_score"] == 0.0
        assert paper["paper_rank"] == 1
        upload = await client.post(
            f"/api/papers/{submitted}/upload",
            headers=auth_headers,
            files={"file": ("p.pdf", PDF, "application/pdf")},
        )
        assert upload.status_code == 409
        history = (
            await client.get(f"/api/papers/{submitted}/history", headers=auth_headers)
        ).json()
        assert history[-1]["reason"] == "Generated text"
        # Finalizing keeps the verdict at 0.
        final = await client.post(f"/api/papers/{submitted}/finalize", headers=auth_headers)
        assert final.json()["final_score"] == 0.0

    @pytest.mark.asyncio
    async def test_format_deduction_applied_on_finalize(self, client, db, auth_headers, submitted):
        reviewer = await _reviewer(db)
        await _assign(client, auth_headers, submitted, reviewer.id)
        await _review(client, headers_for(reviewer), submitted)  # mean 8.0 -> 0.8
        score = await client.put(
            f"/api/papers/{submitted}/score",
            headers=auth_headers,
            json={"format_deduction": 20, "format_deduction_reason": "6 pages"},
        )
        assert score.status_code == 200
        assert score.json()["format_deduction_reason"] == "6 pages"
        final = await client.post(f"/api/papers/{submitted}/finalize", headers=auth_headers)
        assert final.json()["final_score"] == pytest.approx(0.6)

    @pytest.mark.asyncio
    async def test_deduction_cannot_push_below_zero(self, client, db, auth_headers, submitted):
        reviewer = await _reviewer(db)
        await _assign(client, auth_headers, submitted, reviewer.id)
        await _review(client, headers_for(reviewer), submitted)
        await client.put(
            f"/api/papers/{submitted}/score", headers=auth_headers, json={"format_deduction": 100}
        )
        final = await client.post(f"/api/papers/{submitted}/finalize", headers=auth_headers)
        assert final.json()["final_score"] == 0.0

    @pytest.mark.asyncio
    async def test_deduction_is_bounded(self, client, auth_headers, submitted):
        resp = await client.put(
            f"/api/papers/{submitted}/score", headers=auth_headers, json={"format_deduction": 150}
        )
        assert resp.status_code == 422


# ── 7. Reviewer assignment checks ─────────────────────────────────────────────


class TestReviewerChecks:
    @pytest.mark.asyncio
    async def test_reviewer_needs_papers_review(self, client, db, auth_headers, submitted):
        plain = await make_user(db, "plain@test.com", ("papers:read",))
        resp = await _assign(client, auth_headers, submitted, plain.id)
        assert resp.status_code == 422
        assert "papers:review" in resp.json()["message"]

    @pytest.mark.asyncio
    async def test_team_member_cannot_review_own_paper(
        self, client, db, auth_headers, team, submitted
    ):
        reviewer = await _reviewer(db)
        db.add(TeamMember(team_id=team.id, user_id=reviewer.id, name="R", role="mentor"))
        await db.commit()
        resp = await _assign(client, auth_headers, submitted, reviewer.id)
        assert resp.status_code == 409
        assert "member of the paper's team" in resp.json()["message"]

    @pytest.mark.asyncio
    async def test_same_school_conflict(self, client, db, auth_headers, team, submitted):
        team.school = "HTL Wien West"
        sibling = Team(name="Sibling", country="AT", school="  htl wien west ")
        db.add(sibling)
        await db.flush()
        reviewer = await _reviewer(db)
        db.add(TeamMember(team_id=sibling.id, user_id=reviewer.id, name="R", role="mentor"))
        await db.commit()
        resp = await _assign(client, auth_headers, submitted, reviewer.id)
        assert resp.status_code == 409
        assert "same school" in resp.json()["message"]

    @pytest.mark.asyncio
    async def test_other_school_is_fine(self, client, db, auth_headers, team, submitted):
        team.school = "HTL Wien West"
        other = Team(name="Other", country="AT", school="BRG Linz")
        db.add(other)
        await db.flush()
        reviewer = await _reviewer(db)
        db.add(TeamMember(team_id=other.id, user_id=reviewer.id, name="R", role="mentor"))
        await db.commit()
        assert (await _assign(client, auth_headers, submitted, reviewer.id)).status_code == 201


# ── 8. Criteria and finalize ──────────────────────────────────────────────────


class TestCriteriaFinalize:
    @pytest.mark.asyncio
    async def test_finalize_averages_five_criteria_over_reviewers(
        self, client, db, auth_headers, submitted
    ):
        r1, r2 = await _reviewer(db, "r1@test.com"), await _reviewer(db, "r2@test.com")
        for r in (r1, r2):
            await _assign(client, auth_headers, submitted, r.id)
        # r1: mean(10, 10, 10, 10, 5) = 9.0; r2: mean(6, 6, 6, 6, 6) = 6.0
        await _review(
            client,
            headers_for(r1),
            submitted,
            {**{k: 10 for k in FULL_SCORES}, "score_format": 5, "recommendation": "accept"},
        )
        await _review(
            client,
            headers_for(r2),
            submitted,
            {**{k: 6 for k in FULL_SCORES}, "recommendation": "accept"},
        )
        final = await client.post(f"/api/papers/{submitted}/finalize", headers=auth_headers)
        assert final.json()["final_score"] == pytest.approx(0.75)
        assert final.json()["finalized_at"] is not None


# ── 9. Mentor linking ─────────────────────────────────────────────────────────


class TestMentorLinking:
    @pytest.mark.asyncio
    async def test_admin_links_and_unlinks_account(self, client, db, auth_headers, team):
        member = TeamMember(team_id=team.id, name="Ms Mentor", role="mentor")
        db.add(member)
        await db.commit()
        account = await make_user(db, "linked@test.com", MENTOR_PERMS)

        linked = await client.patch(
            f"/api/teams/{team.id}/members/{member.id}",
            headers=auth_headers,
            json={"user_id": account.id},
        )
        assert linked.status_code == 200, linked.text
        assert linked.json()["user_id"] == account.id
        mine = await client.get("/api/teams/mine", headers=headers_for(account))
        assert [t["id"] for t in mine.json()] == [team.id]

        unlinked = await client.patch(
            f"/api/teams/{team.id}/members/{member.id}",
            headers=auth_headers,
            json={"user_id": None},
        )
        assert unlinked.json()["user_id"] is None
        assert unlinked.json()["name"] == "Ms Mentor"

    @pytest.mark.asyncio
    async def test_link_validation(self, client, db, auth_headers, team):
        a = TeamMember(team_id=team.id, name="A", role="mentor")
        b = TeamMember(team_id=team.id, name="B", role="member")
        db.add_all([a, b])
        await db.commit()
        account = await make_user(db, "dup@test.com")

        unknown = await client.patch(
            f"/api/teams/{team.id}/members/{a.id}", headers=auth_headers, json={"user_id": "nope"}
        )
        assert unknown.status_code == 422
        ok = await client.patch(
            f"/api/teams/{team.id}/members/{a.id}",
            headers=auth_headers,
            json={"user_id": account.id},
        )
        assert ok.status_code == 200
        dup = await client.patch(
            f"/api/teams/{team.id}/members/{b.id}",
            headers=auth_headers,
            json={"user_id": account.id},
        )
        assert dup.status_code == 409
        missing = await client.patch(
            f"/api/teams/{team.id}/members/missing", headers=auth_headers, json={"name": "x"}
        )
        assert missing.status_code == 404

    @pytest.mark.asyncio
    async def test_mentor_cannot_link_accounts(self, client, db, team):
        mentor = await _mentor(db, team)
        member = TeamMember(team_id=team.id, name="Student", role="member")
        db.add(member)
        await db.commit()
        stranger = await make_user(db, "stranger@test.com")

        link = await client.patch(
            f"/api/teams/{team.id}/members/{member.id}",
            headers=headers_for(mentor),
            json={"user_id": stranger.id},
        )
        assert link.status_code == 403
        add = await client.post(
            f"/api/teams/{team.id}/members",
            headers=headers_for(mentor),
            json={"name": "Sneaky", "user_id": stranger.id},
        )
        assert add.status_code == 403
        # Renaming their own member is still fine.
        rename = await client.patch(
            f"/api/teams/{team.id}/members/{member.id}",
            headers=headers_for(mentor),
            json={"name": "Student B"},
        )
        assert rename.status_code == 200
        assert rename.json()["name"] == "Student B"


# ── 10. Statistics and export ─────────────────────────────────────────────────


class TestStatsAndExport:
    @pytest.mark.asyncio
    async def test_stats(self, client, db, auth_headers, season, team, submitted):
        other = Team(name="Other", country="AT")
        db.add(other)
        await db.commit()
        second = await _create(client, auth_headers, season, other)
        await api_upload_and_submit(client, auth_headers, second["id"])

        reviewer = await _reviewer(db)
        await _assign(client, auth_headers, submitted, reviewer.id)
        await _review(client, headers_for(reviewer), submitted)
        await client.post(f"/api/papers/{submitted}/finalize", headers=auth_headers)
        await _set_status(client, auth_headers, submitted, "accepted")
        await _set_status(client, auth_headers, second["id"], "rejected")

        stats = await client.get(
            "/api/papers/stats", headers=auth_headers, params={"season_id": season.id}
        )
        assert stats.status_code == 200
        data = stats.json()
        assert data["total"] == 2
        assert data["by_status"] == {"accepted": 1, "rejected": 1}
        assert data["acceptance_rate"] == 0.5
        assert data["average_final_score"] == 0.8
        assert data["average_review_score"] == 8.0
        assert data["criterion_averages"]["format"] == 10.0
        assert data["reviews_submitted"] == 1

    @pytest.mark.asyncio
    async def test_stats_admin_only(self, client, db, team):
        mentor = await _mentor(db, team)
        assert (
            await client.get("/api/papers/stats", headers=headers_for(mentor))
        ).status_code == 403

    @pytest.mark.asyncio
    async def test_reviews_csv(self, client, db, auth_headers, season, team, submitted):
        reviewer = await _reviewer(db)
        await _assign(client, auth_headers, submitted, reviewer.id)
        await _review(
            client,
            headers_for(reviewer),
            submitted,
            {**SUBMITTABLE, "comment_language": "=HYPERLINK()", "private_notes": "internal"},
        )
        resp = await client.get(
            f"/api/exports/seasons/{season.id}/reviews.csv", headers=auth_headers
        )
        assert resp.status_code == 200
        rows = list(csv.reader(io.StringIO(resp.content.decode("utf-8-sig"))))
        header, row = rows[0], rows[1]
        record = dict(zip(header, row, strict=True))
        assert record["Team"] == team.name
        assert record["Reviewer E-Mail"] == "reviewer@test.com"
        assert record["Version"] == "1"
        assert record["Score format"] == "10.0"
        assert record["Kommentar language"] == "'=HYPERLINK()"  # formula neutralised
        assert record["Private Notizen"] == "internal"

        mentor = await _mentor(db, team)
        denied = await client.get(
            f"/api/exports/seasons/{season.id}/reviews.csv", headers=headers_for(mentor)
        )
        assert denied.status_code == 403
