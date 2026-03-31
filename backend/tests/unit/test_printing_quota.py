"""Unit tests for 3D Printing module – quota enforcement and filament tracking."""
import pytest
from modules.printing.service import (
    create_print_job,
    _get_or_create_quota,
    consume_filament,
    create_spool,
    update_print_job,
)
from modules.printing.crypto import encrypt_credential, decrypt_credential
from core.exceptions import ConflictError, NotFoundError


class TestPrintQuota:
    @pytest.mark.asyncio
    async def test_first_job_creates_quota(self, db, season, team, admin_user):
        data = {
            "team_id": team.id,
            "season_id": season.id,
            "file_name": "part1.3mf",
            "material": "PLA",
        }
        await create_print_job(db, data, admin_user.id)
        await db.flush()

        quota = await _get_or_create_quota(db, team.id, season.id)
        assert quota is not None
        assert quota.max_parts == 4  # default

    @pytest.mark.asyncio
    async def test_hard_limit_blocks_job(self, db, season, team, admin_user):
        """Creating more jobs than max_parts should raise ConflictError."""
        # Set quota to max_parts=2 manually
        quota = await _get_or_create_quota(db, team.id, season.id)
        quota.max_parts = 2
        quota.used_parts = 2
        await db.flush()

        data = {
            "team_id": team.id,
            "season_id": season.id,
            "file_name": "overflow.3mf",
            "material": "PLA",
        }
        with pytest.raises(ConflictError, match="Hard print limit reached"):
            await create_print_job(db, data, admin_user.id)

    @pytest.mark.asyncio
    async def test_completed_job_updates_quota(self, db, season, team, admin_user):
        data = {
            "team_id": team.id,
            "season_id": season.id,
            "file_name": "part.3mf",
            "material": "PLA",
        }
        job = await create_print_job(db, data, admin_user.id)
        await db.flush()

        quota_before = await _get_or_create_quota(db, team.id, season.id)
        used_before = quota_before.used_parts

        # Mark as completed with actual grams
        await update_print_job(db, job.id, status="completed", actual_grams=45.5)
        await db.flush()

        quota_after = await _get_or_create_quota(db, team.id, season.id)
        assert quota_after.used_parts == used_before + 1
        assert quota_after.used_grams == 45.5

    @pytest.mark.asyncio
    async def test_soft_limit_does_not_block(self, db, season, team, admin_user):
        """Job at soft limit should succeed (only hard limit blocks)."""
        quota = await _get_or_create_quota(db, team.id, season.id)
        quota.soft_limit_parts = 1
        quota.max_parts = 4
        quota.used_parts = 1  # at soft limit
        await db.flush()

        data = {
            "team_id": team.id,
            "season_id": season.id,
            "file_name": "ok.3mf",
            "material": "PLA",
        }
        # Should NOT raise – only max_parts is enforced as hard stop
        job = await create_print_job(db, data, admin_user.id)
        assert job is not None


class TestFilamentTracking:
    @pytest.mark.asyncio
    async def test_create_spool(self, db):
        spool = await create_spool(db, {
            "material": "PLA",
            "color": "White",
            "brand": "Bambu",
            "initial_grams": 1000.0,
        })
        await db.flush()

        assert spool.remaining_grams == 1000.0
        assert spool.initial_grams == 1000.0

    @pytest.mark.asyncio
    async def test_consume_filament_reduces_remaining(self, db):
        spool = await create_spool(db, {
            "material": "PETG",
            "initial_grams": 500.0,
        })
        await db.flush()

        updated = await consume_filament(db, spool.id, 120.0)
        assert updated.remaining_grams == 380.0

    @pytest.mark.asyncio
    async def test_consume_more_than_remaining_clamps_to_zero(self, db):
        spool = await create_spool(db, {"material": "PLA", "initial_grams": 50.0})
        await db.flush()

        updated = await consume_filament(db, spool.id, 200.0)
        assert updated.remaining_grams == 0.0

    @pytest.mark.asyncio
    async def test_consume_nonexistent_spool_raises(self, db):
        with pytest.raises(NotFoundError):
            await consume_filament(db, "nonexistent-id", 10.0)


class TestCredentialEncryption:
    def test_encrypt_decrypt_roundtrip(self, monkeypatch):
        monkeypatch.setenv("PRINTER_CREDENTIAL_ENCRYPTION_KEY", "")

        # Without key: returns as-is (dev mode)
        assert decrypt_credential(encrypt_credential("mykey")) == "mykey"

    def test_with_fernet_key(self, monkeypatch):
        from cryptography.fernet import Fernet

        key = Fernet.generate_key().decode()
        monkeypatch.setattr("modules.printing.crypto.get_settings",
                            lambda: type("S", (), {"printer_credential_encryption_key": key})())

        encrypted = encrypt_credential("secret-api-key")
        assert encrypted != "secret-api-key"

        decrypted = decrypt_credential(encrypted)
        assert decrypted == "secret-api-key"
