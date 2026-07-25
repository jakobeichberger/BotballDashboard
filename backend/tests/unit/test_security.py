"""Security regression tests — filename sanitisation, path containment,
upload validation, secret-validation, and self-service privilege boundaries."""

import io

import pytest

from core.config import Settings
from core.exceptions import ValidationError
from core.files import ensure_within, safe_filename, validate_pdf


# ── Filename sanitisation / path traversal ──────────────────────────────────
class TestSafeFilename:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("../../etc/passwd", "passwd"),
            ("a/b/../c.pdf", "c.pdf"),
            ("..\\..\\windows\\system32\\evil.dll", "evil.dll"),
            ("....//....//x", "x"),
            ("normal_file.pdf", "normal_file.pdf"),
            ("with space.pdf", "with_space.pdf"),
            ("", "fallback.pdf"),
            (None, "fallback.pdf"),
        ],
    )
    def test_strips_traversal_and_dirs(self, raw, expected):
        assert safe_filename(raw, "fallback.pdf") == expected

    def test_no_separator_survives(self):
        for raw in ["../../../../root/.ssh/authorized_keys", "/etc/shadow", "x/../../y"]:
            out = safe_filename(raw)
            assert "/" not in out and "\\" not in out and ".." not in out

    def test_length_is_bounded(self):
        assert len(safe_filename("a" * 500 + ".pdf")) <= 204


class TestEnsureWithin:
    def test_allows_path_inside_base(self, tmp_path):
        target = tmp_path / "sub" / "file.pdf"
        assert ensure_within(tmp_path, target) == target.resolve()

    def test_rejects_escape(self, tmp_path):
        with pytest.raises(ValidationError):
            ensure_within(tmp_path / "base", tmp_path / "base" / ".." / ".." / "etc" / "x")


class TestValidatePdf:
    def test_accepts_valid_pdf(self):
        validate_pdf(b"%PDF-1.4\nrest")  # no raise

    def test_rejects_non_pdf_magic(self):
        with pytest.raises(ValidationError):
            validate_pdf(b"GIF89a not a pdf")

    def test_rejects_empty(self):
        with pytest.raises(ValidationError):
            validate_pdf(b"")

    def test_rejects_oversized(self):
        with pytest.raises(ValidationError):
            validate_pdf(b"%PDF-" + b"x" * (2 * 1024 * 1024), max_mb=1)


# ── save_file / save_upload reject traversal end-to-end ──────────────────────
class TestUploadTraversal:
    @pytest.mark.asyncio
    async def test_save_file_neutralises_traversal_filename(self, tmp_path, monkeypatch):
        from fastapi import UploadFile

        import modules.paper_review.service as svc

        monkeypatch.setattr(svc.settings, "upload_dir", str(tmp_path))
        pdf = b"%PDF-1.4 data"
        upload = UploadFile(filename="../../../../etc/cron.d/evil", file=io.BytesIO(pdf))
        path, name, size = await svc.save_file(upload, "paper1")

        assert name == "evil"  # basename only, no traversal
        # File must live under the paper's upload dir, never outside it.
        assert str(tmp_path) in path
        assert "/etc/cron.d/" not in path

    @pytest.mark.asyncio
    async def test_save_file_rejects_non_pdf(self, tmp_path, monkeypatch):
        from fastapi import UploadFile

        import modules.paper_review.service as svc

        monkeypatch.setattr(svc.settings, "upload_dir", str(tmp_path))
        upload = UploadFile(filename="evil.pdf", file=io.BytesIO(b"<script>alert(1)</script>"))
        with pytest.raises(ValidationError):
            await svc.save_file(upload, "paper1")


# ── Secret validation in production ──────────────────────────────────────────
class TestSecretValidation:
    def test_production_rejects_default_jwt_secret(self):
        with pytest.raises(Exception):
            Settings(
                app_env="production",
                app_secret_key="a" * 32,
                jwt_secret_key="change-me-jwt",
                _env_file=None,
            )

    def test_production_rejects_short_secret(self):
        with pytest.raises(Exception):
            Settings(
                app_env="production",
                app_secret_key="short",
                jwt_secret_key="b" * 32,
                _env_file=None,
            )

    def test_production_accepts_strong_secrets(self):
        s = Settings(
            app_env="production",
            app_secret_key="A" * 40,
            jwt_secret_key="B" * 40,
            postgres_password="C" * 40,
            printer_credential_encryption_key="D" * 40,
            _env_file=None,
        )
        assert s.app_env == "production"

    def test_development_allows_defaults(self):
        s = Settings(
            app_env="development",
            app_secret_key="change-me",
            jwt_secret_key="change-me-jwt",
            _env_file=None,
        )
        assert s.is_dev


# ── DB constraint violations become a clean 4xx (no 500 / no internals leak) ──
class TestIntegrityHandler:
    @pytest.mark.asyncio
    async def test_integrity_error_mapped_to_409(self):
        from sqlalchemy.exc import IntegrityError

        from main import integrity_error_handler

        exc = IntegrityError("INSERT ...", {}, Exception("FK violation on team_id"))
        resp = await integrity_error_handler(None, exc)
        assert resp.status_code == 409
        # Must not leak the raw DB error / SQL.
        assert b"team_id" not in resp.body and b"INSERT" not in resp.body
