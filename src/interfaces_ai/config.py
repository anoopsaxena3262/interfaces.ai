from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="IAI_", env_file=".env", extra="ignore")

    env: str = "local"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    bank_ui_base_url: str = "http://127.0.0.1:5173"
    transfer_escalation_usd: float = 5000.0
    discovery_min_confidence: float = 0.72


def get_settings() -> Settings:
    return Settings()
