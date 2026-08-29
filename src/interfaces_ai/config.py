"""Process-wide settings. Env vars use prefix IAI_ (see .env.example)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="IAI_", env_file=".env", extra="ignore")

    env: str = "local"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    # Origin discovery uses when it HTTP-GETs a bank page (empty SPA → contract HTML).
    bank_ui_base_url: str = "http://127.0.0.1:5173"
    # Replay hold: amount >= this USD opens amount_threshold (not a PCI limit).
    transfer_escalation_usd: float = 5000.0
    # Discovery hold floor. The 0–1 score is a demo formula, not a calibrated probability.
    discovery_min_confidence: float = 0.72
    # Log verbosity. DEBUG adds per-field discovery lines (still masked).
    log_level: str = "INFO"


def get_settings() -> Settings:
    """Read env/.env each call so tests can patch env without a process-wide cache."""
    return Settings()
