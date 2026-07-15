from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Application
    app_env: str = "production"
    app_secret_key: str = "change-me"
    app_base_url: str = "http://localhost:8000"
    allowed_origins: str = "http://localhost:5173"

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

    # Email
    smtp_host: str = "localhost"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "BotballDashboard <noreply@example.com>"
    smtp_tls: bool = True
    sendgrid_api_key: str = ""
    sendgrid_from: str = ""

    # Web Push
    vapid_private_key: str = ""
    vapid_public_key: str = ""
    vapid_admin_email: str = "admin@example.com"

    # 3D Print
    printer_credential_encryption_key: str = ""

    # Files
    upload_dir: str = "/app/uploads"
    max_upload_size_mb: int = 20

    @property
    def database_url(self):
        from sqlalchemy.engine import URL
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

    @model_validator(mode="after")
    def _reject_default_secrets_in_prod(self) -> "Settings":
        """Fail fast in production if security-critical secrets are left at
        their insecure defaults — otherwise an attacker who knows the public
        default JWT key could forge tokens for any user."""
        if self.is_dev:
            return self
        weak: list[str] = []
        if self.app_secret_key.startswith("change-me") or len(self.app_secret_key) < 16:
            weak.append("APP_SECRET_KEY")
        if self.jwt_secret_key.startswith("change-me") or len(self.jwt_secret_key) < 16:
            weak.append("JWT_SECRET_KEY")
        if weak:
            raise ValueError(
                "Insecure default secret(s) in production: "
                + ", ".join(weak)
                + ". Set strong values (>=16 chars) in the environment/.env."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
