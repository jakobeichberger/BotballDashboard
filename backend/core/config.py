from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Application
    app_env: str = "production"
    app_secret_key: str = "change-me"
    app_base_url: str = "http://localhost:8000"
    allowed_origins: str = "http://localhost:5173"

    # Database
    database_url: str = "postgresql+asyncpg://botball:botball@db:5432/botball"

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
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",")]

    @property
    def is_dev(self) -> bool:
        return self.app_env == "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()
