from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str = "UNG-CORE"
    environment: str = "development"
    database_url: str = "sqlite+aiosqlite:///./ung_core.db"
    iam_base_url: str = "http://ung-iam:8000"
    data_relay_base_url: str = "http://data-relay:8000"
    service_version: str = "0.1.0"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
