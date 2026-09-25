"""Who sees practice runs and match notes.

Practice runs are a team's internal training data, and match notes carry the
jurors' remarks or a team's own strategy notes. Organizers and jurors
(scoring:admin) see everything; everyone else with scoring:read — mentors,
guests — sees official runs of every team, but practice runs and notes only of
their own teams. The dedicated analytics routes already worked that way; the
raw match lists, the score history and the CSV exports now do too.
"""

from sqlalchemy import ColumnElement, false, or_

from core.auth import has_elevated_access, own_team_ids
from core.exceptions import NotFoundError
from modules.scoring.models import Match, ScoreRevision
from modules.scoring.schemas import MatchListItem, MatchResponse, ScoreRevisionResponse

#: Permission that sees every team's practice runs and notes.
PRACTICE_ELEVATED = "scoring:admin"


async def team_scope(db, user) -> set[str] | None:
    """Teams whose practice runs and notes `user` sees; None means all teams."""
    if await has_elevated_access(db, user, PRACTICE_ELEVATED):
        return None
    return await own_team_ids(db, user)


def visible_matches_clause(scope: set[str] | None) -> ColumnElement[bool] | None:
    """WHERE clause hiding foreign practice runs (None: no restriction)."""
    if scope is None:
        return None
    own = Match.team_id.in_(scope) if scope else false()
    return or_(Match.is_practice.is_(False), own)


def visible_revisions_clause(scope: set[str] | None) -> ColumnElement[bool] | None:
    """Score history of foreign practice runs is hidden as well. Revisions whose
    kind is unknown (is_practice NULL: written before the flag existed, match
    since deleted) count as practice."""
    if scope is None:
        return None
    own = ScoreRevision.team_id.in_(scope) if scope else false()
    return or_(ScoreRevision.is_practice.is_(False), own)


def assert_match_visible(match: Match, scope: set[str] | None) -> None:
    """404 — not 403 — for a foreign practice run: its existence is private too."""
    if scope is not None and match.is_practice and match.team_id not in scope:
        raise NotFoundError("Match not found")


def assert_revisions_visible(revisions: list[ScoreRevision], scope: set[str] | None) -> None:
    if scope is None or not revisions:
        return
    last = revisions[-1]
    if last.team_id not in scope and last.is_practice is not False:
        raise NotFoundError("Match not found")


def match_view(match: Match, scope: set[str] | None) -> MatchResponse:
    """Response for `match` with the notes removed unless the caller may read them."""
    view = MatchResponse.model_validate(match)
    if scope is not None and match.team_id not in scope:
        view.notes = None
    return view


def match_list_item(match: Match, scope: set[str] | None) -> MatchListItem:
    """Like match_view, for lists: without the schema snapshot (never copied)."""
    view = MatchListItem.model_validate(match)
    if scope is not None and match.team_id not in scope:
        view.notes = None
    return view


def revision_view(revision: ScoreRevision, scope: set[str] | None) -> ScoreRevisionResponse:
    view = ScoreRevisionResponse.model_validate(revision)
    if scope is not None and revision.team_id not in scope:
        view.previous_value = _without_notes(view.previous_value)
        view.new_value = _without_notes(view.new_value) or {}
    return view


def _without_notes(state: dict | None) -> dict | None:
    if state is None:
        return None
    return {key: value for key, value in state.items() if key != "notes"}
