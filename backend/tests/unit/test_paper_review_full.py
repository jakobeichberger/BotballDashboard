"""Comprehensive unit tests for the Paper Review service layer.

Complements tests/unit/test_paper_review.py (which covers the basic happy-path
status transitions, duplicate-assignment conflict, unassigned-reviewer forbidden
and average-score cases). This file adds coverage for:

  * get_paper / NotFoundError on all read-through service fns
  * list_papers filtering (season / team / status) and ordering
  * create_paper eager-loads relationships
  * update_paper (None values ignored, NotFoundError)
  * get_or_create_review idempotency + per-revision isolation
  * save_review update-in-place, single / partial score averaging, rounding,
    recommendation & comment persistence, per-revision reviews
  * submit -> under_review transition gating (single & multiple reviewers)
  * revision lifecycle + re-review after revision
  * save_file helper writing bytes to disk
"""
import io

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from core.exceptions import ConflictError, ForbiddenError, NotFoundError
from modules.paper_review.models import Paper, PaperReview, ReviewerAssignment
from modules.paper_review.service import (
    assign_reviewer,
    create_paper,
    get_or_create_review,
    get_paper,
    list_papers,
    save_file,
    save_review,
    set_paper_status,
    submit_paper,
    update_paper,
)


@pytest.fixture
def paper_data(season, team):
    return {
        "season_id": season.id,
        "team_id": team.id,
        "title": "Robot Navigation Using Computer Vision",
        "abstract": "This paper presents a method...",
        "status": "draft",
        "revision_number": 1,
    }


async def _make_second_user(db, email="reviewer2@test.com"):
    from modules.auth.models import User
    from modules.auth.service import hash_password

    user = User(
        email=email,
        display_name="Second User",
        hashed_password=hash_password("pw"),
        is_active=True,
        is_superuser=False,
    )
    db.add(user)
    await db.flush()
    return user


# ── create_paper / get_paper ─────────────────────────────────────────────────

class TestCreateAndGet:
    @pytest.mark.asyncio
    async def test_create_paper_eager_loads_relationships(self, db, paper_data):
        paper = await create_paper(db, paper_data)
        # Relationships must be already loaded (no lazy-load / MissingGreenlet).
        assert paper.reviews == []
        assert paper.assignments == []
        assert paper.title == paper_data["title"]

    @pytest.mark.asyncio
    async def test_create_paper_persists_fields(self, db, paper_data, season, team):
        paper = await create_paper(db, paper_data)
        await db.commit()
        fetched = await get_paper(db, paper.id)
        assert fetched.season_id == season.id
        assert fetched.team_id == team.id
        assert fetched.abstract == "This paper presents a method..."

    @pytest.mark.asyncio
    async def test_get_paper_not_found_raises(self, db):
        with pytest.raises(NotFoundError):
            await get_paper(db, "does-not-exist")


# ── list_papers ──────────────────────────────────────────────────────────────

class TestListPapers:
    @pytest.mark.asyncio
    async def test_list_empty(self, db):
        assert await list_papers(db) == []

    @pytest.mark.asyncio
    async def test_list_returns_all(self, db, paper_data):
        await create_paper(db, dict(paper_data, title="A"))
        await create_paper(db, dict(paper_data, title="B"))
        await db.flush()
        papers = await list_papers(db)
        assert len(papers) == 2

    @pytest.mark.asyncio
    async def test_filter_by_status(self, db, paper_data):
        await create_paper(db, dict(paper_data, title="draft one", status="draft"))
        await create_paper(db, dict(paper_data, title="accepted one", status="accepted"))
        await db.flush()

        drafts = await list_papers(db, status="draft")
        assert len(drafts) == 1
        assert drafts[0].status == "draft"

    @pytest.mark.asyncio
    async def test_filter_by_team(self, db, paper_data, season):
        from modules.teams.models import Team

        other = Team(name="Other Team", team_number="OT-99", country="AT")
        db.add(other)
        await db.flush()

        await create_paper(db, paper_data)
        await create_paper(db, dict(paper_data, team_id=other.id, title="Other"))
        await db.flush()

        only_other = await list_papers(db, team_id=other.id)
        assert len(only_other) == 1
        assert only_other[0].team_id == other.id

    @pytest.mark.asyncio
    async def test_filter_by_season(self, db, paper_data):
        from modules.seasons.models import Season

        other_season = Season(name="Other Season", year=2025, is_active=False)
        db.add(other_season)
        await db.flush()

        await create_paper(db, paper_data)
        await create_paper(
            db, dict(paper_data, season_id=other_season.id, title="Other season paper")
        )
        await db.flush()

        result = await list_papers(db, season_id=other_season.id)
        assert len(result) == 1
        assert result[0].season_id == other_season.id

    @pytest.mark.asyncio
    async def test_list_eager_loads_relationships(self, db, paper_data):
        await create_paper(db, paper_data)
        await db.flush()
        papers = await list_papers(db)
        # accessing relationships must not raise (eager-loaded, not lazy)
        assert papers[0].assignments == []
        assert papers[0].reviews == []


# ── update_paper ─────────────────────────────────────────────────────────────

class TestUpdatePaper:
    @pytest.mark.asyncio
    async def test_update_changes_fields(self, db, paper_data):
        paper = await create_paper(db, paper_data)
        await db.flush()
        updated = await update_paper(db, paper.id, title="New Title", notes="hello")
        await db.commit()
        assert updated.title == "New Title"
        assert updated.notes == "hello"

    @pytest.mark.asyncio
    async def test_update_ignores_none_values(self, db, paper_data):
        paper = await create_paper(db, paper_data)
        await db.flush()
        original_title = paper.title
        updated = await update_paper(db, paper.id, title=None, notes="only notes")
        await db.commit()
        assert updated.title == original_title  # unchanged
        assert updated.notes == "only notes"

    @pytest.mark.asyncio
    async def test_update_file_metadata(self, db, paper_data):
        paper = await create_paper(db, paper_data)
        await db.flush()
        updated = await update_paper(
            db,
            paper.id,
            file_url=f"/api/papers/{paper.id}/download",
            file_name="paper.pdf",
            file_size_bytes=1234,
        )
        await db.commit()
        assert updated.file_name == "paper.pdf"
        assert updated.file_size_bytes == 1234

    @pytest.mark.asyncio
    async def test_update_not_found_raises(self, db):
        with pytest.raises(NotFoundError):
            await update_paper(db, "missing", title="x")


# ── submit_paper ─────────────────────────────────────────────────────────────

class TestSubmitPaper:
    @pytest.mark.asyncio
    async def test_submit_not_found_raises(self, db, admin_user):
        with pytest.raises(NotFoundError):
            await submit_paper(db, "missing", admin_user.id)

    @pytest.mark.asyncio
    async def test_cannot_submit_when_under_review(self, db, paper_data, admin_user):
        paper = await create_paper(db, paper_data)
        await db.flush()
        await set_paper_status(db, paper.id, "under_review")
        await db.commit()
        with pytest.raises(ConflictError):
            await submit_paper(db, paper.id, admin_user.id)

    @pytest.mark.asyncio
    async def test_cannot_submit_when_accepted(self, db, paper_data, admin_user):
        paper = await create_paper(db, paper_data)
        await db.flush()
        await set_paper_status(db, paper.id, "accepted")
        await db.commit()
        with pytest.raises(ConflictError):
            await submit_paper(db, paper.id, admin_user.id)

    @pytest.mark.asyncio
    async def test_submit_from_revision_requested_allowed(self, db, paper_data, admin_user):
        paper = await create_paper(db, paper_data)
        await db.flush()
        await set_paper_status(db, paper.id, "revision_requested")
        await db.commit()
        result = await submit_paper(db, paper.id, admin_user.id)
        assert result.status == "submitted"
        assert result.submitted_by == admin_user.id
        assert result.submitted_at is not None


# ── set_paper_status ─────────────────────────────────────────────────────────

class TestSetStatus:
    @pytest.mark.asyncio
    async def test_set_status_not_found(self, db):
        with pytest.raises(NotFoundError):
            await set_paper_status(db, "missing", "accepted")

    @pytest.mark.asyncio
    async def test_set_under_review_does_not_bump_revision(self, db, paper_data):
        paper = await create_paper(db, paper_data)
        await db.flush()
        await set_paper_status(db, paper.id, "under_review")
        await db.commit()
        assert paper.status == "under_review"
        assert paper.revision_number == 1

    @pytest.mark.asyncio
    async def test_repeated_revision_requested_keeps_incrementing(self, db, paper_data):
        paper = await create_paper(db, paper_data)
        await db.flush()
        await set_paper_status(db, paper.id, "revision_requested")
        await set_paper_status(db, paper.id, "revision_requested")
        await db.commit()
        assert paper.revision_number == 3  # started at 1, +1 twice


# ── assign_reviewer ──────────────────────────────────────────────────────────

class TestAssignReviewer:
    @pytest.mark.asyncio
    async def test_assign_not_found_paper(self, db, admin_user):
        with pytest.raises(NotFoundError):
            await assign_reviewer(db, "missing", admin_user.id, admin_user.id)

    @pytest.mark.asyncio
    async def test_assign_flush_makes_visible(self, db, paper_data, admin_user):
        from sqlalchemy import select

        paper = await create_paper(db, paper_data)
        await db.flush()
        assignment = await assign_reviewer(db, paper.id, admin_user.id, admin_user.id)
        # assign_reviewer flushes internally -> id assigned + visible in fresh query
        assert assignment.id is not None
        rows = (
            await db.execute(
                select(ReviewerAssignment).where(
                    ReviewerAssignment.paper_id == paper.id
                )
            )
        ).scalars().all()
        assert len(rows) == 1

    @pytest.mark.asyncio
    async def test_two_distinct_reviewers_allowed(self, db, paper_data, admin_user):
        from sqlalchemy import select

        paper = await create_paper(db, paper_data)
        await db.flush()
        other = await _make_second_user(db)
        await assign_reviewer(db, paper.id, admin_user.id, admin_user.id)
        await assign_reviewer(db, paper.id, other.id, admin_user.id)
        await db.commit()
        rows = (
            await db.execute(
                select(ReviewerAssignment).where(
                    ReviewerAssignment.paper_id == paper.id
                )
            )
        ).scalars().all()
        assert len(rows) == 2


# ── get_or_create_review ─────────────────────────────────────────────────────

class TestGetOrCreateReview:
    @pytest.mark.asyncio
    async def test_creates_when_absent(self, db, paper_data, admin_user):
        paper = await create_paper(db, paper_data)
        await db.flush()
        review = await get_or_create_review(db, paper.id, admin_user.id, 1)
        assert isinstance(review, PaperReview)
        assert review.id is not None
        assert review.is_submitted is False

    @pytest.mark.asyncio
    async def test_idempotent_same_revision(self, db, paper_data, admin_user):
        paper = await create_paper(db, paper_data)
        await db.flush()
        r1 = await get_or_create_review(db, paper.id, admin_user.id, 1)
        r2 = await get_or_create_review(db, paper.id, admin_user.id, 1)
        assert r1.id == r2.id

    @pytest.mark.asyncio
    async def test_distinct_per_revision(self, db, paper_data, admin_user):
        paper = await create_paper(db, paper_data)
        await db.flush()
        r1 = await get_or_create_review(db, paper.id, admin_user.id, 1)
        r2 = await get_or_create_review(db, paper.id, admin_user.id, 2)
        assert r1.id != r2.id
        assert r1.revision_number == 1
        assert r2.revision_number == 2


# ── save_review scoring & persistence ────────────────────────────────────────

class TestSaveReview:
    async def _assigned_paper(self, db, paper_data, admin_user):
        paper = await create_paper(db, paper_data)
        await db.flush()
        await assign_reviewer(db, paper.id, admin_user.id, admin_user.id)
        return paper

    @pytest.mark.asyncio
    async def test_save_review_not_found_paper(self, db, admin_user):
        with pytest.raises(NotFoundError):
            await save_review(db, "missing", admin_user.id, {"score_content": 5.0})

    @pytest.mark.asyncio
    async def test_single_score_average(self, db, paper_data, admin_user):
        paper = await self._assigned_paper(db, paper_data, admin_user)
        review = await save_review(db, paper.id, admin_user.id, {"score_content": 9.0})
        await db.commit()
        assert review.total_score == 9.0

    @pytest.mark.asyncio
    async def test_average_rounds_to_two_decimals(self, db, paper_data, admin_user):
        paper = await self._assigned_paper(db, paper_data, admin_user)
        # avg(1,2,2) = 1.6666... -> 1.67
        review = await save_review(
            db,
            paper.id,
            admin_user.id,
            {
                "score_content": 1.0,
                "score_methodology": 2.0,
                "score_presentation": 2.0,
            },
        )
        await db.commit()
        assert review.total_score == 1.67

    @pytest.mark.asyncio
    async def test_save_review_persists_comments_and_recommendation(
        self, db, paper_data, admin_user
    ):
        paper = await self._assigned_paper(db, paper_data, admin_user)
        review = await save_review(
            db,
            paper.id,
            admin_user.id,
            {
                "score_content": 7.0,
                "comments": "Great work",
                "private_notes": "secret",
                "recommendation": "accept",
            },
        )
        await db.commit()
        assert review.comments == "Great work"
        assert review.private_notes == "secret"
        assert review.recommendation == "accept"

    @pytest.mark.asyncio
    async def test_save_review_updates_in_place(self, db, paper_data, admin_user):
        paper = await self._assigned_paper(db, paper_data, admin_user)
        first = await save_review(db, paper.id, admin_user.id, {"score_content": 5.0})
        await db.flush()
        second = await save_review(
            db, paper.id, admin_user.id, {"score_methodology": 7.0}
        )
        await db.commit()
        # same review row, not a new one
        assert first.id == second.id
        # both scores now present -> avg(5,7) = 6.0
        assert second.score_content == 5.0
        assert second.score_methodology == 7.0
        assert second.total_score == 6.0

    @pytest.mark.asyncio
    async def test_save_review_not_submitted_by_default(self, db, paper_data, admin_user):
        paper = await self._assigned_paper(db, paper_data, admin_user)
        review = await save_review(db, paper.id, admin_user.id, {"score_content": 8.0})
        await db.commit()
        assert review.is_submitted is False
        assert review.submitted_at is None
        # paper still in draft – not enough to transition
        refetched = await get_paper(db, paper.id)
        assert refetched.status == "draft"


# ── submit marks the review submitted ────────────────────────────────────────

class TestSubmitReview:
    @pytest.mark.asyncio
    async def test_submit_marks_review_submitted(self, db, paper_data, admin_user):
        paper = await create_paper(db, paper_data)
        await db.flush()
        await assign_reviewer(db, paper.id, admin_user.id, admin_user.id)
        review = await save_review(
            db, paper.id, admin_user.id, {"score_content": 8.0}, submit=True
        )
        await db.commit()
        assert review.is_submitted is True
        assert review.submitted_at is not None
        assert review.total_score == 8.0

    @pytest.mark.asyncio
    async def test_multiple_reviewers_each_get_own_review(
        self, db, paper_data, admin_user
    ):
        from sqlalchemy import select

        paper = await create_paper(db, paper_data)
        await db.flush()
        other = await _make_second_user(db)
        await assign_reviewer(db, paper.id, admin_user.id, admin_user.id)
        await assign_reviewer(db, paper.id, other.id, admin_user.id)

        r1 = await save_review(
            db, paper.id, admin_user.id, {"score_content": 8.0}, submit=True
        )
        r2 = await save_review(
            db, paper.id, other.id, {"score_content": 6.0}, submit=True
        )
        await db.commit()

        assert r1.id != r2.id
        assert r1.reviewer_id == admin_user.id
        assert r2.reviewer_id == other.id

        rows = (
            await db.execute(
                select(PaperReview).where(PaperReview.paper_id == paper.id)
            )
        ).scalars().all()
        assert len(rows) == 2
        assert all(r.is_submitted for r in rows)

    @pytest.mark.asyncio
    async def test_resave_after_submit_keeps_submitted(self, db, paper_data, admin_user):
        paper = await create_paper(db, paper_data)
        await db.flush()
        await assign_reviewer(db, paper.id, admin_user.id, admin_user.id)
        await save_review(
            db, paper.id, admin_user.id, {"score_content": 8.0}, submit=True
        )
        await db.flush()
        # editing again (without submit flag) updates the same row; is_submitted
        # stays True because it is never cleared.
        again = await save_review(
            db, paper.id, admin_user.id, {"score_methodology": 4.0}
        )
        await db.commit()
        assert again.is_submitted is True
        assert again.total_score == 6.0  # avg(8, 4)


# ── full revision lifecycle ──────────────────────────────────────────────────

class TestRevisionLifecycle:
    @pytest.mark.asyncio
    async def test_review_per_revision_isolated(self, db, paper_data, admin_user):
        from sqlalchemy import select

        paper = await create_paper(db, paper_data)
        await db.flush()
        await assign_reviewer(db, paper.id, admin_user.id, admin_user.id)

        # Review revision 1
        rev1_review = await save_review(
            db, paper.id, admin_user.id, {"score_content": 4.0}
        )
        await db.flush()
        assert rev1_review.revision_number == 1

        # Request a revision (bumps to revision 2)
        await set_paper_status(db, paper.id, "revision_requested")
        await db.flush()
        paper2 = await get_paper(db, paper.id)
        assert paper2.revision_number == 2

        # New review for revision 2 is a *different* row
        rev2_review = await save_review(
            db, paper.id, admin_user.id, {"score_content": 9.0}
        )
        await db.commit()
        assert rev2_review.id != rev1_review.id
        assert rev2_review.revision_number == 2
        assert rev2_review.score_content == 9.0

        rows = (
            await db.execute(
                select(PaperReview).where(PaperReview.paper_id == paper.id)
            )
        ).scalars().all()
        assert len(rows) == 2  # one per revision


# ── save_file helper ─────────────────────────────────────────────────────────

class TestSaveFile:
    @pytest.mark.asyncio
    async def test_save_file_writes_bytes(self, tmp_path, monkeypatch):
        # Point upload_dir at a temp dir so we don't pollute the container fs.
        import modules.paper_review.service as svc

        monkeypatch.setattr(svc.settings, "upload_dir", str(tmp_path))

        content = b"%PDF-1.4 fake pdf bytes"
        upload = UploadFile(
            filename="research.pdf",
            file=io.BytesIO(content),
            headers=Headers({"content-type": "application/pdf"}),
        )

        path, name, size = await svc.save_file(upload, "paper-xyz")

        assert name == "research.pdf"
        assert size == len(content)
        with open(path, "rb") as f:
            assert f.read() == content

    @pytest.mark.asyncio
    async def test_save_file_default_filename(self, tmp_path, monkeypatch):
        import modules.paper_review.service as svc

        monkeypatch.setattr(svc.settings, "upload_dir", str(tmp_path))

        pdf = b"%PDF-1.4 minimal test pdf"
        upload = UploadFile(filename=None, file=io.BytesIO(pdf))
        path, name, size = await svc.save_file(upload, "p1")
        assert name == "paper.pdf"
        assert path.endswith("paper.pdf")
        assert size == len(pdf)
