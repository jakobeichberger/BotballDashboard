"""Deployment configuration: .env.example, docker-compose.yml and Settings.

These guard the operational contract: a copy of .env.example with the
required secrets filled in must start in production mode, every variable the
backend reads must be documented, and the compose file must keep the services,
profiles and log rotation the docs describe.
"""

import re
import uuid
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from dotenv import dotenv_values

from core.config import Settings

REPO = Path(__file__).resolve().parents[3]
ENV_EXAMPLE = REPO / ".env.example"
COMPOSE = REPO / "docker-compose.yml"

REQUIRED_SECRETS = {
    "APP_SECRET_KEY": "a" * 40,
    "JWT_SECRET_KEY": "b" * 40,
    "POSTGRES_PASSWORD": "c" * 40,
}


@pytest.fixture
def clean_env(monkeypatch):
    """Remove Settings-related variables set by the test runner (e.g. JWT_SECRET_KEY)."""
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)


def _filled_env(tmp_path: Path, **overrides: str) -> Path:
    lines = []
    replacements = {
        **REQUIRED_SECRETS,
        "PRINTER_CREDENTIAL_ENCRYPTION_KEY": Fernet.generate_key().decode(),
        **overrides,
    }
    for line in ENV_EXAMPLE.read_text().splitlines():
        key = line.split("=", 1)[0]
        if not line.startswith("#") and key in replacements:
            line = f"{key}={replacements.pop(key)}"
        lines.append(line)
    assert not replacements, f"not in .env.example: {sorted(replacements)}"
    text = "\n".join(lines).replace("botball.example.com", "botball.school.test")
    env = tmp_path / ".env"
    env.write_text(text + "\n")
    return env


def test_env_example_documents_every_setting():
    values = dotenv_values(ENV_EXAMPLE)
    missing = [name.upper() for name in Settings.model_fields if name.upper() not in values]
    assert missing == []


def test_env_example_has_compose_variables_and_no_unused_database_url():
    text = ENV_EXAMPLE.read_text()
    values = dotenv_values(ENV_EXAMPLE)
    for name in ("DOMAIN", "TRAEFIK_EMAIL", "AGE_RECIPIENT", "COMPOSE_PROFILES"):
        assert name in values, name
    for name in ("FORWARDED_ALLOW_IPS", "PGDATA_DRIVER_OPT_DEVICE", "BACKUP_HOST_DIR"):
        assert name in text, name
    # Settings builds the URL from POSTGRES_*; a DATABASE_URL would be ignored.
    assert "DATABASE_URL" not in values


def test_env_example_as_is_refuses_production_with_clear_message(clean_env):
    with pytest.raises(ValueError) as exc:
        Settings(_env_file=ENV_EXAMPLE)
    message = str(exc.value)
    for name in (*REQUIRED_SECRETS, "PRINTER_CREDENTIAL_ENCRYPTION_KEY", "APP_BASE_URL"):
        assert name in message
    assert "Fernet.generate_key" in message


def test_env_example_with_required_secrets_starts_in_production(clean_env, tmp_path):
    settings = Settings(_env_file=_filled_env(tmp_path))
    assert settings.app_env == "production"
    assert settings.app_base_url == "https://botball.school.test"
    # SMTP is disabled unless configured.
    assert settings.smtp_host == ""
    assert settings.database_url.host == "db"


def test_production_rejects_non_fernet_printer_key(clean_env, tmp_path):
    env = _filled_env(tmp_path, PRINTER_CREDENTIAL_ENCRYPTION_KEY="x" * 44)
    with pytest.raises(ValueError, match="PRINTER_CREDENTIAL_ENCRYPTION_KEY"):
        Settings(_env_file=env)


def test_smtp_default_is_disabled(clean_env):
    assert Settings(app_env="development", _env_file=None).smtp_host == ""


# ── docker-compose.yml ────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def compose():
    yaml = pytest.importorskip("yaml")
    return yaml.safe_load(COMPOSE.read_text())


def test_compose_has_all_runtime_services(compose):
    services = compose["services"]
    for name in ("traefik", "db", "redis", "backend", "worker", "beat", "frontend"):
        assert name in services
        assert "profiles" not in services[name], f"{name} must always start"
    assert services["backup"]["profiles"] == ["production"]
    for name in ("prometheus", "blackbox", "alertmanager", "node-exporter", "postgres-exporter"):
        assert services[name]["profiles"] == ["monitoring"]


def test_every_service_has_a_healthcheck(compose):
    services = compose["services"]
    # One-shot init containers (restart "no") exit once done; there is nothing to probe.
    missing = [
        name
        for name, service in services.items()
        if "healthcheck" not in service and service.get("restart") != "no"
    ]
    assert missing == []
    one_shot = {name for name, service in services.items() if service.get("restart") == "no"}
    assert one_shot == {"volume-permissions", "backup-permissions", "postgres-monitor-role"}


def test_internal_system_endpoints_are_not_routed_by_traefik(compose):
    labels = compose["services"]["backend"]["labels"]
    [rule] = [label for label in labels if label.startswith("traefik.http.routers.api.rule=")]
    assert "!Path(`/api/system/metrics`)" in rule
    assert "!Path(`/api/system/readiness`)" in rule


def test_monitoring_scrapes_every_exporter(compose):
    yaml = pytest.importorskip("yaml")
    config = yaml.safe_load((REPO / "monitoring" / "prometheus.yml").read_text())
    targets = {
        target
        for job in config["scrape_configs"]
        for static in job.get("static_configs", [])
        for target in static["targets"]
    }
    assert {"node-exporter:9100", "postgres-exporter:9187", "backend:8000"} <= targets


def test_compose_rotates_logs_for_every_service(compose):
    for name, service in compose["services"].items():
        logging = service.get("logging")
        assert logging and logging["driver"] == "json-file", name
        assert {"max-size", "max-file"} <= set(logging["options"]), name


def test_backup_service_reports_health(compose):
    backup = compose["services"]["backup"]
    assert "backup_scheduler.py" in " ".join(backup["command"])
    assert "check" in backup["healthcheck"]["test"]
    assert backup["environment"]["AGE_RECIPIENT"] == "${AGE_RECIPIENT:-}"


def test_monitoring_files_referenced_by_compose_exist(compose):
    for service in ("prometheus", "alertmanager"):
        for volume in compose["services"][service]["volumes"]:
            source = volume.split(":", 1)[0]
            if source.startswith("./"):
                assert (REPO / source).exists(), source


# ── Container hardening (security review 2026-09) ────────────────────────────
DOCKERFILE = REPO / "backend" / "Dockerfile"
APP_SERVICES = ("backend", "worker", "worker-ocr", "beat", "backup")
APP_UID = "10001"


def test_backend_image_runs_as_a_non_root_user():
    text = DOCKERFILE.read_text()
    production = text.split("AS production", 1)[1]
    users = [line.split()[1] for line in production.splitlines() if line.startswith("USER ")]
    assert users and users[-1] not in ("root", "0"), "production stage must end as non-root"
    assert f"--uid {APP_UID}" in text


def test_application_containers_drop_privileges(compose):
    for name in APP_SERVICES:
        service = compose["services"][name]
        assert service.get("cap_drop") == ["ALL"], name
        assert "no-new-privileges:true" in service.get("security_opt", []), name
        assert service.get("mem_limit"), name
        assert "user" not in service, f"{name} must use the image's non-root user"


def test_stateless_containers_have_a_read_only_root(compose):
    for name in ("backend", "worker", "worker-ocr", "beat"):
        service = compose["services"][name]
        assert service.get("read_only") is True, name
        assert any(entry.startswith("/tmp") for entry in service.get("tmpfs", [])), name
    # beat keeps its schedule file in the writable /tmp.
    assert "/tmp/" in compose["services"]["beat"]["command"]


def test_volume_ownership_is_fixed_before_the_app_starts(compose):
    services = compose["services"]
    for name in ("volume-permissions", "backup-permissions"):
        init = services[name]
        assert init["user"] == "0:0", name
        assert init["cap_drop"] == ["ALL"], name
        assert set(init["cap_add"]) <= {"CHOWN", "DAC_READ_SEARCH"}, name
        assert init["network_mode"] == "none", name
        assert APP_UID in " ".join(init["command"]), name
        assert "fix-volume-ownership.sh" in " ".join(init["entrypoint"]), name
    assert (REPO / "backend" / "scripts" / "fix-volume-ownership.sh").is_file()
    assert services["backup-permissions"]["profiles"] == ["production"]
    for name in APP_SERVICES:
        depends = services[name]["depends_on"]
        assert depends["volume-permissions"]["condition"] == "service_completed_successfully"
    depends = services["backup"]["depends_on"]
    assert depends["backup-permissions"]["condition"] == "service_completed_successfully"
    # Every writable mount of the app containers is covered by an init service.
    fixed = {
        volume.split(":")[1]
        for name in ("volume-permissions", "backup-permissions")
        for volume in services[name]["volumes"]
    }
    for name in APP_SERVICES:
        for volume in services[name].get("volumes", []):
            target, *mode = volume.split(":")[1:]
            if mode != ["ro"]:
                assert target in fixed, (name, target)


def test_worker_limits_image_decoding(compose):
    # worker-ocr runs the OCR; the general worker keeps the cap as well in
    # case an OCR task still sits in its queue from before the split.
    for name in ("worker", "worker-ocr"):
        worker = compose["services"][name]
        assert worker["environment"]["OPENCV_IO_MAX_IMAGE_PIXELS"] == "40000000", name


def test_every_backend_image_service_is_hardened_and_built_by_the_scripts(compose):
    """A service running the backend image (e.g. a new worker) must not slip
    past the hardening, the ownership init or the build/verify scripts."""
    services = compose["services"]
    backend_image = {
        name
        for name, service in services.items()
        if (service.get("build") or {}).get("context") == "./backend"
        and name not in ("volume-permissions", "backup-permissions")
    }
    assert backend_image == set(APP_SERVICES)
    update = (REPO / "scripts" / "update.sh").read_text()
    setup = (REPO / "scripts" / "proxmox-setup.sh").read_text()
    verify = (REPO / "scripts" / "verify-deployment.sh").read_text()
    built = next(li for li in update.splitlines() if li.startswith("BACKEND_SERVICES="))
    checked = next(li for li in verify.splitlines() if li.startswith("for service in backend "))
    for name in backend_image:
        assert name in built.split("(", 1)[1].rstrip(")").split(), name
        assert f"{name}|" in setup, name
        assert name in checked.split(), name


def test_traefik_limits_api_request_bodies(compose):
    labels = compose["services"]["backend"]["labels"]
    assert any(".buffering.maxRequestBodyBytes=" in label for label in labels)
    assert "traefik.http.routers.api.middlewares=api-body-limit" in labels
    # WebSockets bypass the buffering middleware on their own router, which
    # uses Traefik v3 syntax (Path() takes no regex placeholders any more).
    [ws_rule] = [label for label in labels if label.startswith("traefik.http.routers.api-ws.rule=")]
    # "$$" is compose's escape for a literal "$" (the regex end anchor).
    pattern = re.search(r"PathRegexp\(`([^`]+)`\)", ws_rule).group(1).replace("$$", "$")
    for path in ("/api/v1/public/events/ecer-2026/ws", f"/api/v1/events/{uuid.uuid4()}/ws"):
        assert re.fullmatch(pattern, path), path
    for path in ("/api/v1/events/x/ws/extra", "/api/v1/events//ws", "/api/v1/teams/x/ws"):
        assert not re.fullmatch(pattern, path), path
