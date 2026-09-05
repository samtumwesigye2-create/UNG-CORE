from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "UNG-CORE"
    environment: str = "development"
    database_url: str = "sqlite+aiosqlite:///./ung_core.db"
    iam_base_url: str = "http://ung-iam:8000"
    data_relay_base_url: str = "http://data-relay:8000"
    public_base_url: str = ""
    service_version: str = "0.1.0"
    health_poll_enabled: bool = True
    health_poll_interval_seconds: int = 30
    scheduler_enabled: bool = True
    scheduler_interval_seconds: int = 5
    request_body_limit_bytes: int = 1_048_576
    request_timeout_seconds: int = 30
    security_headers_enabled: bool = True
    production_require_postgres: bool = True
    production_require_https_dependencies: bool = True
    trusted_hosts: str = "*"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
