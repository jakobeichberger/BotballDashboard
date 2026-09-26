"""Operational hardening of the compose stack (review 2026-09, security notes).

- worker-ocr gets only the environment the ocr queue needs (no JWT, app,
  printer, SMTP or push secrets);
- postgres-exporter logs in with a pg_monitor role instead of the superuser;
- Redis is bounded (maxmemory) without evicting broker data (noeviction);
- application images carry fixed names so update.sh can tag releases.
"""

import re
from pathlib import Path

import pytest

from core.config import Settings

REPO = Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"
SECRET_NAMES = re.compile(
    r"SECRET|JWT|PRINTER_CREDENTIAL|SMTP|SENDGRID|VAPID|^AGE_|^ALERT_", re.IGNORECASE
)


@pytest.fixture(scope="module")
def compose():
    yaml = pytest.importorskip("yaml")
    return yaml.safe_load((REPO / "docker-compose.yml").read_text())


@pytest.fixture
def clean_env(monkeypatch):
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)


# ── worker-ocr ───────────────────────────────────────────────────────────────


def test_ocr_worker_gets_no_application_secrets(compose):
    ocr = compose["services"]["worker-ocr"]
    assert "env_file" not in ocr, "worker-ocr must not read the whole .env"
    environment = ocr["environment"]
    leaked = [name for name in environment if SECRET_NAMES.search(name)]
    assert leaked == []
    assert environment["SERVICE_SCOPE"] == "ocr"
    for needed in ("POSTGRES_PASSWORD", "POSTGRES_HOST", "REDIS_URL", "UPLOAD_DIR", "APP_ENV"):
        assert needed in environment, needed


def test_ocr_scope_starts_in_production_without_app_secrets(clean_env):
    settings = Settings(
        _env_file=None,
        app_env="production",
        service_scope="ocr",
        postgres_password="p" * 32,
    )
    assert settings.service_scope == "ocr"
    # The same environment without the scope is refused, as before.
    with pytest.raises(ValueError, match="JWT_SECRET_KEY"):
        Settings(_env_file=None, app_env="production", postgres_password="p" * 32)


def test_ocr_scope_still_requires_a_real_database_password(clean_env):
    with pytest.raises(ValueError, match="POSTGRES_PASSWORD"):
        Settings(_env_file=None, app_env="production", service_scope="ocr")


def test_ocr_task_code_reads_no_secret_settings():
    """The ocr queue's tasks and what they call touch DB, Redis and files only."""
    files = [
        BACKEND / "modules/scoring/score_sheets/tasks.py",
        BACKEND / "modules/scoring/score_sheets/service.py",
        BACKEND / "modules/scoring/score_sheets/scan_service.py",
        BACKEND / "core/celery_app.py",
        BACKEND / "core/database.py",
    ]
    secret_settings = re.compile(
        r"\.(app_secret_key|jwt_secret_key|printer_credential_encryption_key|smtp_\w+"
        r"|sendgrid_\w+|vapid_\w+)"
    )
    for path in files:
        assert not secret_settings.search(path.read_text()), path
        # No path into auth tokens, printer credentials or notifications.
        text = path.read_text()
        for module in ("core.auth", "modules.printing.crypto", "core.notifications"):
            assert f"import {module}" not in text and f"from {module} " not in text, (
                path,
                module,
            )


# ── postgres-exporter ────────────────────────────────────────────────────────


def test_postgres_exporter_uses_a_pg_monitor_role(compose):
    services = compose["services"]
    exporter = services["postgres-exporter"]
    env = exporter["environment"]
    assert env["DATA_SOURCE_USER"] == "${POSTGRES_MONITOR_USER:-botball_monitor}"
    assert "DATA_SOURCE_PASS" not in env, "the superuser password must not reach the exporter"
    assert env["DATA_SOURCE_PASS_FILE"] == "/secret/password"
    assert (
        exporter["depends_on"]["postgres-monitor-role"]["condition"]
        == "service_completed_successfully"
    )
    init = services["postgres-monitor-role"]
    assert init["profiles"] == ["monitoring"]
    assert init["restart"] == "no"
    assert init["cap_drop"] == ["ALL"] and init["cap_add"] == ["CHOWN"]
    script = (REPO / "monitoring" / "postgres-monitor-role.sh").read_text()
    assert "GRANT pg_monitor TO" in script
    assert "NOSUPERUSER" in script


# ── Redis ────────────────────────────────────────────────────────────────────


def test_redis_is_bounded_without_evicting_broker_data(compose):
    redis = compose["services"]["redis"]
    command = redis["command"]
    assert command[0] == "redis-server"
    assert command[command.index("--maxmemory") + 1] == "${REDIS_MAXMEMORY:-256mb}"
    # Celery keeps its queues in this instance: evicting keys would drop tasks.
    assert command[command.index("--maxmemory-policy") + 1] == "noeviction"
    assert redis["mem_limit"]


# ── Images ───────────────────────────────────────────────────────────────────


def test_backend_image_services_share_one_named_image(compose):
    services = compose["services"]
    built = {
        name: service["image"]
        for name, service in services.items()
        if (service.get("build") or {}).get("context") == "./backend"
    }
    assert set(built.values()) == {"${BOTBALL_IMAGE_PREFIX:-botballdashboard}-backend:local"}
    assert (
        services["frontend"]["image"] == "${BOTBALL_IMAGE_PREFIX:-botballdashboard}-frontend:local"
    )


def test_dev_override_builds_its_own_backend_image():
    yaml = pytest.importorskip("yaml")

    class _ComposeLoader(yaml.SafeLoader):
        pass

    # Compose merge tags (!reset, !override) carry plain values.
    for tag in ("!reset", "!override"):
        _ComposeLoader.add_constructor(
            tag,
            lambda loader, node: (
                loader.construct_sequence(node)
                if isinstance(node, yaml.SequenceNode)
                else loader.construct_scalar(node)
            ),
        )
    dev = yaml.load((REPO / "docker-compose.dev.yml").read_text(), Loader=_ComposeLoader)
    # The development target must not overwrite the production image that
    # worker, beat and backup run.
    assert dev["services"]["backend"]["image"].endswith("-backend-dev:local")
