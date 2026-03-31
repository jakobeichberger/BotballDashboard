"""Unit tests for Paper Review module – status transitions and review logic."""
import pytest
from modules.paper_review.models import Paper, PaperReview, ReviewerAssignment
from modules.paper_review.service import (
    create_paper,
    submit_paper,
    set_paper_status,
    assign_reviewer,
    save_review,
    get_paper,
)
from core.exceptions import ConflictError, ForbiddenError


@pytest.fixture
def paper_data(season, team):
    return {
        "season_id": season.id,
        "team_id": team.id,
        "title": "Robot Navigation Using Computer Vision",
        "abstract": "This paper presents...",
        "status": "draft",
        "revision_number": 1,
    }


class TestPaperStatusTransitions:
    @pytest.mark.asyncio
    async def test_create_paper_defaults_to_draft(self, db, paper_data):
        paper = await create_paper(db, paper_data)
        await db.commit()
        assert paper.status == "draft"
        assert paper.revision_number == 1

    @pytest.mark.asyncio
    async def test_submit_paper_changes_status(self, db, paper_data, admin_user):
        paper = await create_paper(db, paper_data)
        await db.flush()

        submitted = await submit_paper(db, paper.id, admin_user.id)
        await db.commit()

        assert submitted.status == "submitted"
        assert submitted.submitted_at is not None
        assert submitted.submitted_by == admin_user.id

    @pytest.mark.asyncio
    async def test_cannot_submit_already_submitted_paper(self, db, paper_data, admin_user):
        paper = await create_paper(db, paper_data)
        await db.flush()
        await submit_paper(db, paper.id, admin_user.id)
        await db.commit()

        with pytest.raises(ConflictError):
            await submit_paper(db, paper.id, admin_user.id)

    @pytest.mark.asyncio
    async def test_revision_requested_increments_revision_number(self, db, paper_data):
        paper = await create_paper(db, paper_data)
        await db.flush()

        assert paper.revision_number == 1
        await set_paper_status(db, paper.id, "revision_requested")
        await db.commit()

        assert paper.revision_number == 2

    @pytest.mark.asyncio
    async def test_resubmit_after_revision_allowed(self, db, paper_data, admin_user):
        paper = await create_paper(db, paper_data)
        await db.flush()
        await submit_paper(db, paper.id, admin_user.id)
        await set_paper_status(db, paper.id, "revision_requested")
        await db.commit()

        assert paper.status == "revision_requested"
        # Should now be re-submittable
        resubmitted = await submit_paper(db, paper.id, admin_user.id)
        assert resubmitted.status == "submitted"

    @pytest.mark.asyncio
    async def test_set_status_accepted(self, db, paper_data):
        paper = await create_paper(db, paper_data)
        await db.flush()
        await set_paper_status(db, paper.id, "accepted")
        await db.commit()
        assert paper.status == "accepted"

    @pytest.mark.asyncio
    async def test_set_status_rejected(self, db, paper_data):
        paper = await create_paper(db, paper_data)
        await db.flush()
        await set_paper_status(db, paper.id, "rejected")
        await db.commit()
        assert paper.status == "rejected"


class TestReviewerAssignment:
    @pytest.mark.asyncio
    async def test_assign_reviewer(self, db, paper_data, admin_user):
        paper = await create_paper(db, paper_data)
        await db.flush()

        assignment = await assign_reviewer(db, paper.id, admin_user.id, admin_user.id)
        await db.commit()

        assert assignment.paper_id == paper.id
        assert assignment.reviewer_id == admin_user.id

    @pytest.mark.asyncio
    async def test_duplicate_assignment_raises_conflict(self, db, paper_data, admin_user):
        paper = await create_paper(db, paper_data)
        await db.flush()
        await assign_reviewer(db, paper.id, admin_user.id, admin_user.id)
        await db.commit()

        with pytest.raises(ConflictError):
            await assign_reviewer(db, paper.id, admin_user.id, admin_user.id)

    @pytest.mark.asyncio
    async def test_unassigned_reviewer_cannot_review(self, db, paper_data, admin_user):
        paper = await create_paper(db, paper_data)
        await db.flush()

        # No assignment created → save_review should raise ForbiddenError
        with pytest.raises(ForbiddenError):
            await save_review(db, paper.id, admin_user.id, {"score_content": 8.0})


class TestReviewScores:
    @pytest.mark.asyncio
    async def test_review_total_score_is_average(self, db, paper_data, admin_user):
        paper = await create_paper(db, paper_data)
        await db.flush()
        await assign_reviewer(db, paper.id, admin_user.id, admin_user.id)

        review = await save_review(db, paper.id, admin_user.id, {
            "score_content": 8.0,
            "score_methodology": 6.0,
            "score_presentation": 7.0,
            "score_originality": 9.0,
        })
        await db.commit()

        # avg(8, 6, 7, 9) = 7.5
        assert review.total_score == 7.5

    @pytest.mark.asyncio
    async def test_partial_scores_compute_average_of_filled(self, db, paper_data, admin_user):
        paper = await create_paper(db, paper_data)
        await db.flush()
        await assign_reviewer(db, paper.id, admin_user.id, admin_user.id)

        review = await save_review(db, paper.id, admin_user.id, {
            "score_content": 8.0,
            "score_methodology": 6.0,
        })
        await db.commit()

        # avg(8, 6) = 7.0
        assert review.total_score == 7.0

    @pytest.mark.asyncio
    async def test_submit_review_marks_is_submitted(self, db, paper_data, admin_user):
        paper = await create_paper(db, paper_data)
        await db.flush()
        await assign_reviewer(db, paper.id, admin_user.id, admin_user.id)

        review = await save_review(
            db, paper.id, admin_user.id,
            {"score_content": 7.0, "recommendation": "accept"},
            submit=True,
        )
        await db.commit()

        assert review.is_submitted is True
        assert review.submitted_at is not None
