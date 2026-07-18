"""Comprehensive unit tests for the 3D Printing module service + crypto layer.

Complements tests/unit/test_printing_quota.py (which covers the basic quota
creation / hard-limit / soft-limit / completed-job paths and a couple of spool
and crypto smoke tests). This file exercises the rest of the service surface:
printer CRUD + credential handling, print-job listing / filtering / ordering /
status transitions / approval, deeper quota accounting, spool listing + creation
defaults, and the crypto edge cases (env passthrough + InvalidToken).
"""

import pytest
from cryptography.fernet import Fernet

from core.exceptions import ConflictError, NotFoundError
from modules.printing.crypto import decrypt_credential, encrypt_credential
from modules.printing.service import (
    _get_or_create_quota,
    approve_print_job,
    consume_filament,
    create_print_job,
    create_printer,
    create_spool,
    get_print_job,
    get_printer,
    get_printer_api_key,
    get_quota,
    list_print_jobs,
    list_printers,
    list_spools,
    update_print_job,
    update_printer,
)
from modules.scoring.service import get_default_event


def _fernet_settings(key: str):
    """Build a fake get_settings() returning the given encryption key."""
    return lambda: type("S", (), {"printer_credential_encryption_key": key})()


# ── Printers ────────────────────────────────────────────────────────────────


class TestPrinterService:
    @pytest.mark.asyncio
    async def test_create_printer_minimal_flushes_and_refreshes(self, db):
        printer = await create_printer(db, {"name": "Mini"})
        # create_printer flush+refresh => id is populated immediately.
        assert printer.id is not None
        assert printer.name == "Mini"
        assert printer.printer_type == "bambu"  # model default
        assert printer.is_active is True
        assert printer.is_online is False
        assert printer.api_key_encrypted is None

    @pytest.mark.asyncio
    async def test_create_printer_with_api_key_encrypts(self, db, monkeypatch):
        monkeypatch.setattr(
            "modules.printing.crypto.get_settings",
            _fernet_settings(Fernet.generate_key().decode()),
        )
        printer = await create_printer(db, {"name": "Secure", "api_key": "super-secret"})
        # Stored value is encrypted (not the plaintext) and "api_key" was popped.
        assert printer.api_key_encrypted is not None
        assert printer.api_key_encrypted != "super-secret"
        assert not hasattr(printer, "api_key")

    @pytest.mark.asyncio
    async def test_create_printer_with_api_key_dev_passthrough(self, db, monkeypatch):
        monkeypatch.setattr("modules.printing.crypto.get_settings", _fernet_settings(""))
        printer = await create_printer(db, {"name": "Dev", "api_key": "plain"})
        # No key configured => stored as-is (dev only).
        assert printer.api_key_encrypted == "plain"

    @pytest.mark.asyncio
    async def test_get_printer_not_found(self, db):
        with pytest.raises(NotFoundError, match="Printer not found"):
            await get_printer(db, "does-not-exist")

    @pytest.mark.asyncio
    async def test_list_printers_ordered_by_name(self, db):
        await create_printer(db, {"name": "Zebra"})
        await create_printer(db, {"name": "Alpha"})
        await create_printer(db, {"name": "Mango"})
        printers = await list_printers(db)
        assert [p.name for p in printers] == ["Alpha", "Mango", "Zebra"]

    @pytest.mark.asyncio
    async def test_update_printer_sets_fields_and_skips_none(self, db):
        printer = await create_printer(db, {"name": "Orig", "notes": "keep-me"})
        updated = await update_printer(db, printer.id, name="Renamed", notes=None, is_active=False)
        await db.flush()
        assert updated.name == "Renamed"
        # notes=None must NOT overwrite the existing value.
        assert updated.notes == "keep-me"
        assert updated.is_active is False

    @pytest.mark.asyncio
    async def test_update_printer_reencrypts_api_key(self, db, monkeypatch):
        monkeypatch.setattr(
            "modules.printing.crypto.get_settings",
            _fernet_settings(Fernet.generate_key().decode()),
        )
        printer = await create_printer(db, {"name": "P", "api_key": "old"})
        old_blob = printer.api_key_encrypted
        await update_printer(db, printer.id, api_key="new")
        await db.flush()
        assert printer.api_key_encrypted != old_blob
        assert decrypt_credential(printer.api_key_encrypted) == "new"

    @pytest.mark.asyncio
    async def test_update_printer_not_found(self, db):
        with pytest.raises(NotFoundError):
            await update_printer(db, "nope", name="X")

    @pytest.mark.asyncio
    async def test_get_printer_api_key_empty_when_unset(self, db):
        printer = await create_printer(db, {"name": "NoKey"})
        assert await get_printer_api_key(db, printer.id) == ""

    @pytest.mark.asyncio
    async def test_get_printer_api_key_roundtrip(self, db, monkeypatch):
        monkeypatch.setattr(
            "modules.printing.crypto.get_settings",
            _fernet_settings(Fernet.generate_key().decode()),
        )
        printer = await create_printer(db, {"name": "K", "api_key": "abc123"})
        assert await get_printer_api_key(db, printer.id) == "abc123"


# ── Print jobs ──────────────────────────────────────────────────────────────


class TestPrintJobService:
    async def _job(self, db, team, season, admin_user, **overrides):
        data = {
            "team_id": team.id,
            "season_id": season.id,
            "file_name": overrides.pop("file_name", "part.3mf"),
            "material": "PLA",
            **overrides,
        }
        job = await create_print_job(db, data, admin_user.id)
        await db.flush()
        return job

    async def _queue(self, db, job, admin_user):
        await approve_print_job(db, job.id, admin_user.id)
        await update_print_job(db, job.id, status="queued")

    @pytest.mark.asyncio
    async def test_create_print_job_sets_submitter_and_defaults(self, db, team, season, admin_user):
        job = await self._job(db, team, season, admin_user)
        assert job.id is not None  # flush+refresh
        assert job.submitted_by == admin_user.id
        assert job.status == "pending"
        assert job.priority == 0

    @pytest.mark.asyncio
    async def test_get_print_job_not_found(self, db):
        with pytest.raises(NotFoundError, match="Print job not found"):
            await get_print_job(db, "missing")

    @pytest.mark.asyncio
    async def test_list_jobs_filters_by_team_season_status(self, db, team, season, admin_user):
        from modules.teams.models import Team

        other_team = Team(name="Other", team_number="OT-1", country="DE")
        db.add(other_team)
        await db.flush()

        j1 = await self._job(db, team, season, admin_user, file_name="a.3mf")
        await self._job(db, other_team, season, admin_user, file_name="b.3mf")

        # team filter
        team_jobs = await list_print_jobs(db, team_id=team.id)
        assert [j.id for j in team_jobs] == [j1.id]

        # season filter returns both
        season_jobs = await list_print_jobs(db, season_id=season.id)
        assert len(season_jobs) == 2

        # status filter: nothing is "completed" yet
        assert await list_print_jobs(db, status="completed") == []

    @pytest.mark.asyncio
    async def test_list_jobs_ordered_by_priority_desc_then_created(
        self, db, team, season, admin_user
    ):
        low = await self._job(db, team, season, admin_user, file_name="low.3mf")
        high = await self._job(db, team, season, admin_user, file_name="high.3mf")
        # Bump priority on the second job; it should sort first.
        await update_print_job(db, high.id, priority=10)
        await db.flush()

        jobs = await list_print_jobs(db)
        assert jobs[0].id == high.id
        assert jobs[1].id == low.id

    @pytest.mark.asyncio
    async def test_update_job_to_printing_sets_started_at(self, db, team, season, admin_user):
        job = await self._job(db, team, season, admin_user)
        assert job.started_at is None
        await self._queue(db, job, admin_user)
        updated = await update_print_job(db, job.id, status="printing")
        await db.flush()
        assert updated.status == "printing"
        assert updated.started_at is not None
        assert updated.completed_at is None

    @pytest.mark.asyncio
    async def test_update_job_started_at_not_overwritten_when_already_printing(
        self, db, team, season, admin_user
    ):
        job = await self._job(db, team, season, admin_user)
        await self._queue(db, job, admin_user)
        await update_print_job(db, job.id, status="printing")
        await db.flush()
        first_started = job.started_at
        # Re-applying "printing" must not reset started_at.
        await update_print_job(db, job.id, status="printing", notes="again")
        await db.flush()
        assert job.started_at == first_started

    @pytest.mark.asyncio
    async def test_update_job_completed_without_actual_grams(self, db, team, season, admin_user):
        """Completing a job with no actual_grams still bumps used_parts only."""
        job = await self._job(db, team, season, admin_user)
        await self._queue(db, job, admin_user)
        await update_print_job(db, job.id, status="completed")
        await db.flush()
        quota = await _get_or_create_quota(db, team.id, season.id)
        assert quota.used_parts == 1
        assert quota.used_grams == 0.0
        assert job.completed_at is not None

    @pytest.mark.asyncio
    async def test_update_job_completed_twice_counts_once(self, db, team, season, admin_user):
        """Re-saving an already-completed job must not double count usage."""
        job = await self._job(db, team, season, admin_user)
        await self._queue(db, job, admin_user)
        await update_print_job(db, job.id, status="completed", actual_grams=10.0)
        await db.flush()
        await update_print_job(db, job.id, status="completed", notes="touch")
        await db.flush()
        quota = await _get_or_create_quota(db, team.id, season.id)
        assert quota.used_parts == 1
        assert quota.used_grams == 10.0

    @pytest.mark.asyncio
    async def test_approve_print_job(self, db, team, season, admin_user):
        job = await self._job(db, team, season, admin_user)
        approved = await approve_print_job(db, job.id, admin_user.id)
        await db.flush()
        assert approved.status == "approved"
        assert approved.approved_by == admin_user.id
        assert approved.approved_at is not None

    @pytest.mark.asyncio
    async def test_approve_nonexistent_job_raises(self, db, admin_user):
        with pytest.raises(NotFoundError):
            await approve_print_job(db, "nope", admin_user.id)


# ── Quotas ──────────────────────────────────────────────────────────────────


class TestQuotaService:
    @pytest.mark.asyncio
    async def test_get_quota_is_idempotent(self, db, team, season):
        q1 = await get_quota(db, team.id, season.id)
        q2 = await get_quota(db, team.id, season.id)
        assert q1.id == q2.id  # same row, not a duplicate

    @pytest.mark.asyncio
    async def test_quota_defaults(self, db, team, season):
        quota = await get_quota(db, team.id, season.id)
        assert quota.max_parts == 4
        assert quota.soft_limit_parts == 3
        assert quota.used_parts == 0
        assert quota.used_grams == 0.0

    @pytest.mark.asyncio
    async def test_used_grams_accumulate_across_completed_jobs(self, db, team, season, admin_user):
        for grams in (12.5, 7.5):
            data = {
                "team_id": team.id,
                "season_id": season.id,
                "file_name": "g.3mf",
                "material": "PLA",
            }
            job = await create_print_job(db, data, admin_user.id)
            await db.flush()
            await approve_print_job(db, job.id, admin_user.id)
            await update_print_job(db, job.id, status="queued")
            await update_print_job(db, job.id, status="completed", actual_grams=grams)
            await db.flush()
        quota = await _get_or_create_quota(db, team.id, season.id)
        assert quota.used_parts == 2
        assert quota.used_grams == 20.0

    @pytest.mark.asyncio
    async def test_hard_limit_at_exact_max_blocks(self, db, team, season, admin_user):
        """used_parts == max_parts (not just >) must block the next job."""
        event = await get_default_event(db, season.id)
        quota = await _get_or_create_quota(db, team.id, season.id, event.id)
        quota.max_parts = 3
        quota.used_parts = 3
        await db.flush()
        data = {
            "team_id": team.id,
            "season_id": season.id,
            "file_name": "blocked.3mf",
            "material": "PLA",
        }
        with pytest.raises(ConflictError, match="Hard print limit reached"):
            await create_print_job(db, data, admin_user.id)


# ── Filament spools ─────────────────────────────────────────────────────────


class TestSpoolService:
    @pytest.mark.asyncio
    async def test_create_spool_defaults_remaining_to_initial(self, db):
        spool = await create_spool(db, {"material": "PLA", "initial_grams": 750.0})
        await db.flush()
        assert spool.remaining_grams == 750.0
        assert spool.initial_grams == 750.0

    @pytest.mark.asyncio
    async def test_create_spool_without_initial_uses_default(self, db):
        spool = await create_spool(db, {"material": "PETG"})
        await db.flush()
        # No initial_grams provided => model default 1000 for initial, and the
        # service sets remaining to the same 1000.
        assert spool.initial_grams == 1000.0
        assert spool.remaining_grams == 1000.0

    @pytest.mark.asyncio
    async def test_create_spool_respects_explicit_remaining(self, db):
        spool = await create_spool(
            db, {"material": "PLA", "initial_grams": 1000.0, "remaining_grams": 250.0}
        )
        await db.flush()
        assert spool.remaining_grams == 250.0

    @pytest.mark.asyncio
    async def test_list_spools_only_active(self, db):
        active = await create_spool(db, {"material": "PLA", "initial_grams": 1000.0})
        inactive = await create_spool(db, {"material": "PLA", "initial_grams": 1000.0})
        inactive.is_active = False
        await db.flush()
        spools = await list_spools(db)
        ids = {s.id for s in spools}
        assert active.id in ids
        assert inactive.id not in ids

    @pytest.mark.asyncio
    async def test_list_spools_filters_by_printer(self, db):
        printer = await create_printer(db, {"name": "P"})
        on_printer = await create_spool(
            db, {"material": "PLA", "initial_grams": 1000.0, "printer_id": printer.id}
        )
        await create_spool(db, {"material": "PLA", "initial_grams": 1000.0})
        await db.flush()
        spools = await list_spools(db, printer_id=printer.id)
        assert [s.id for s in spools] == [on_printer.id]

    @pytest.mark.asyncio
    async def test_consume_exact_remaining_hits_zero(self, db):
        spool = await create_spool(db, {"material": "PLA", "initial_grams": 100.0})
        await db.flush()
        updated = await consume_filament(db, spool.id, 100.0)
        assert updated.remaining_grams == 0.0


# ── Crypto edge cases ───────────────────────────────────────────────────────


class TestCrypto:
    def test_env_empty_key_passthrough(self, monkeypatch):
        """Empty PRINTER_CREDENTIAL_ENCRYPTION_KEY env => dev passthrough."""
        monkeypatch.setattr("modules.printing.crypto.get_settings", _fernet_settings(""))
        token = encrypt_credential("hello")
        assert token == "hello"
        assert decrypt_credential(token) == "hello"

    def test_real_fernet_roundtrip(self, monkeypatch):
        key = Fernet.generate_key().decode()
        monkeypatch.setattr("modules.printing.crypto.get_settings", _fernet_settings(key))
        token = encrypt_credential("api-token")
        assert token != "api-token"
        assert decrypt_credential(token) == "api-token"

    def test_decrypt_invalid_token_returns_empty(self, monkeypatch):
        key = Fernet.generate_key().decode()
        monkeypatch.setattr("modules.printing.crypto.get_settings", _fernet_settings(key))
        # A token encrypted with a *different* key cannot be decrypted.
        other = Fernet(Fernet.generate_key()).encrypt(b"x").decode()
        assert decrypt_credential(other) == ""

    def test_decrypt_garbage_returns_empty(self, monkeypatch):
        key = Fernet.generate_key().decode()
        monkeypatch.setattr("modules.printing.crypto.get_settings", _fernet_settings(key))
        assert decrypt_credential("not-a-fernet-token") == ""
