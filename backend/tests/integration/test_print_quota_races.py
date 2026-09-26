"""Print quota: a retry cannot bypass the hard limit, submissions are serialised.

* A failed job does not count as open. With ``max_parts=1`` a team could let
  job A fail, submit job B, and have A retried (failed → queued) without any
  check: two parts printed. The retry now checks the hard limit like a new
  submission and needs ``quota_override`` (audited) beyond it.
* The hard-limit check reads the team's quota row with ``FOR UPDATE``
  (PostgreSQL), so two concurrent submissions (a double click) are checked
  one after the other instead of both passing.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql import Select

from core.audit import AuditLog
from modules.printing import service
from modules.printing.models import PrintJob, TeamSeasonPrintQuota


async def _create(client, headers, team, season, **extra):
    payload = {"team_id": team.id, "season_id": season.id, "file_name": "part.stl", **extra}
    resp = await client.post("/api/printing/jobs", headers=headers, json=payload)
    return resp


async def _patch(client, headers, job_id, **body):
    return await client.patch(f"/api/printing/jobs/{job_id}", headers=headers, json=body)


async def _failed_job(client, headers, team, season) -> str:
    job_id = (await _create(client, headers, team, season)).json()["id"]
    await client.put(f"/api/printing/jobs/{job_id}/approve", headers=headers)
    assert (await _patch(client, headers, job_id, status="queued")).status_code == 200
    assert (await _patch(client, headers, job_id, status="failed")).status_code == 200
    return job_id


@pytest.fixture
async def one_part(client, auth_headers, team, season):
    resp = await client.put(
        "/api/printing/quotas",
        headers=auth_headers,
        json={"team_id": team.id, "season_id": season.id, "max_parts": 1, "soft_limit_parts": 1},
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
@pytest.mark.usefixtures("one_part")
async def test_retry_of_a_failed_job_respects_the_hard_limit(
    client, db, auth_headers, team, season
):
    failed = await _failed_job(client, auth_headers, team, season)
    # The failed job frees its slot, so B is accepted ...
    other = await _create(client, auth_headers, team, season)
    assert other.status_code == 201, other.text
    # ... and A cannot be retried on top of it.
    retry = await _patch(client, auth_headers, failed, status="queued")
    assert retry.status_code == 409, retry.text
    assert "Hard print limit reached" in retry.json()["message"]
    job = (await db.execute(select(PrintJob).where(PrintJob.id == failed))).scalar_one()
    assert job.status == "failed"


@pytest.mark.asyncio
@pytest.mark.usefixtures("one_part")
async def test_retry_beyond_the_limit_needs_an_audited_override(
    client, db, auth_headers, team, season
):
    failed = await _failed_job(client, auth_headers, team, season)
    assert (await _create(client, auth_headers, team, season)).status_code == 201
    retry = await _patch(client, auth_headers, failed, status="queued", quota_override=True)
    assert retry.status_code == 200, retry.text
    assert retry.json()["status"] == "queued"
    assert retry.json()["quota_override"] is True
    await db.flush()
    audit = (
        await db.execute(select(AuditLog).where(AuditLog.action == "printing.quota_override"))
    ).scalar_one()
    assert audit.resource_id == failed
    assert audit.detail["reason"].startswith("Hard print limit reached")


@pytest.mark.asyncio
@pytest.mark.usefixtures("one_part")
async def test_retry_within_the_limit_needs_no_override(client, auth_headers, team, season):
    failed = await _failed_job(client, auth_headers, team, season)
    retry = await _patch(client, auth_headers, failed, status="queued")
    assert retry.status_code == 200, retry.text
    assert retry.json()["quota_override"] is False


def _locks_quota_row(statements) -> bool:
    for statement in statements:
        if not isinstance(statement, Select):
            continue
        if TeamSeasonPrintQuota.__table__ not in statement.get_final_froms():
            continue
        if "FOR UPDATE" in str(statement.compile(dialect=postgresql.dialect())):
            return True
    return False


@pytest.fixture
def statements(db, monkeypatch):
    seen: list = []
    execute = db.execute

    async def spy(statement, *args, **kwargs):
        seen.append(statement)
        return await execute(statement, *args, **kwargs)

    monkeypatch.setattr(db, "execute", spy)
    return seen


@pytest.mark.asyncio
async def test_submission_locks_the_quota_row(client, auth_headers, team, season, statements):
    assert (await _create(client, auth_headers, team, season)).status_code == 201
    assert _locks_quota_row(statements)


@pytest.mark.asyncio
async def test_retry_locks_the_quota_row(client, db, auth_headers, team, season, monkeypatch):
    failed = await _failed_job(client, auth_headers, team, season)
    seen: list = []
    execute = db.execute

    async def spy(statement, *args, **kwargs):
        seen.append(statement)
        return await execute(statement, *args, **kwargs)

    monkeypatch.setattr(db, "execute", spy)
    assert (await _patch(client, auth_headers, failed, status="queued")).status_code == 200
    assert _locks_quota_row(seen)


@pytest.mark.asyncio
async def test_poller_transitions_are_not_quota_checked(db, client, auth_headers, team, season):
    # Only the failed → queued retry reopens a job; the other transitions
    # (printer poller included) are not held up by the quota.
    job_id = (await _create(client, auth_headers, team, season)).json()["id"]
    await client.put(f"/api/printing/jobs/{job_id}/approve", headers=auth_headers)
    await _patch(client, auth_headers, job_id, status="queued")
    job = await service.update_print_job(db, job_id, status="printing")
    assert job.status == "printing"
