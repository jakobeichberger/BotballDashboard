from functools import lru_cache

from cryptography.fernet import Fernet
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Application
    app_env: str = "production"
    app_secret_key: str = "change-me"
    app_base_url: str = "http://localhost:8000"
    allowed_origins: str = "http://localhost:5173"
    # Log level for the API, worker and beat (DEBUG, INFO, WARNING, ...).
    # Empty means DEBUG in development and INFO otherwise.
    log_level: str = ""

    # Database – individual components so passwords with special characters
    # are never embedded in a URL string (avoids URL-encoding pitfalls).
    postgres_host: str = "db"
    postgres_port: int = 5432
    postgres_db: str = "botball"
    postgres_user: str = "botball"
    postgres_password: str = "botball"

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # JWT
    jwt_secret_key: str = "change-me-jwt"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 30
    # Where logged-out access tokens are remembered until they expire:
    # "redis" (shared by all API instances) or "memory" (one process; tests).
    token_denylist_backend: str = "redis"
    # bcrypt work factor for new password hashes. 12 is the production value;
    # the test suite lowers it (tests/conftest.py) because hashing dominates
    # its runtime. Existing hashes keep the factor they were created with.
    bcrypt_rounds: int = Field(default=12, ge=4, le=31)

    # Email – an empty SMTP_HOST disables SMTP (SendGrid is still tried when
    # SENDGRID_API_KEY is set).
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "BotballDashboard <noreply@example.com>"
    smtp_tls: bool = True
    sendgrid_api_key: str = ""
    sendgrid_from: str = ""

    # Web Push
    vapid_private_key: str = ""
    vapid_admin_email: str = "admin@example.com"

    # 3D Print – Fernet key (urlsafe base64 of 32 bytes). Required in production.
    printer_credential_encryption_key: str = ""

    # Files
    upload_dir: str = "/app/uploads"
    max_upload_size_mb: int = 20
    # Print job files (STL/3MF/G-code) are much larger than papers or photos,
    # so they have their own limit. A reverse proxy in front of the API must
    # accept at least max(MAX_UPLOAD_SIZE_MB, PRINT_UPLOAD_MAX_MB) + 1 MB.
    print_upload_max_mb: int = 100

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        if self.app_env != "production":
            return self

        invalid: list[str] = []
        secrets = {
            "APP_SECRET_KEY": self.app_secret_key,
            "JWT_SECRET_KEY": self.jwt_secret_key,
            "POSTGRES_PASSWORD": self.postgres_password,
            "PRINTER_CREDENTIAL_ENCRYPTION_KEY": self.printer_credential_encryption_key,
        }
        for name, value in secrets.items():
            lowered = value.lower()
            if len(value) < 24 or "change-me" in lowered or "placeholder" in lowered:
                invalid.append(name)
        if "example.com" in self.app_base_url or "example.com" in self.allowed_origins:
            invalid.extend(["APP_BASE_URL", "ALLOWED_ORIGINS"])
        if "PRINTER_CREDENTIAL_ENCRYPTION_KEY" not in invalid and not _is_fernet_key(
            self.printer_credential_encryption_key
        ):
            invalid.append("PRINTER_CREDENTIAL_ENCRYPTION_KEY")
        if invalid:
            names = ", ".join(sorted(set(invalid)))
            raise ValueError(
                f"Unsafe production configuration: replace {names}. "
                "Secrets need at least 24 random characters; generate one with "
                "`python3 -c 'import secrets; print(secrets.token_urlsafe(32))'`. "
                "PRINTER_CREDENTIAL_ENCRYPTION_KEY must be a Fernet key: "
                "`python3 -c 'from cryptography.fernet import Fernet; "
                "print(Fernet.generate_key().decode())'` (or `make fernet-key`)."
            )
        if self.bcrypt_rounds < 10:
            # Only the test suite may use cheap hashes (tests/conftest.py).
            raise ValueError("Unsafe production configuration: BCRYPT_ROUNDS must be at least 10.")
        return self

    @property
    def database_url(self) -> URL:
        return URL.create(
            drivername="postgresql+asyncpg",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",")]

    @property
    def is_dev(self) -> bool:
        return self.app_env == "development"


def _is_fernet_key(value: str) -> bool:
    try:
        Fernet(value.encode())
    except (ValueError, TypeError):
        return False
    return True


@lru_cache
def get_settings() -> Settings:
    return Settings()
