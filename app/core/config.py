from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- auth ---
    api_keys: str = ""                      # comma-separated list of client keys

    # --- infra ---
    redis_url: str = "redis://redis:6379/0"
    job_ttl_seconds: int = 604800           # keep job records 7 days
    job_timeout_seconds: int = 900

    # --- google drive ---
    google_credentials_file: str = "/secrets/service-account.json"
    drive_input_folder_id: str = ""         # watched folder (incoming CVs)
    drive_output_folder_id: str = ""        # where JSON results are written
    drive_shared_drive_id: str = ""         # optional, speeds up queries

    # --- ocr ---
    ocr_lang: str = "fr"
    ocr_dpi: int = 220
    max_pages: int = 15
    min_text_chars: int = 200               # below this, assume scan -> OCR
    min_block_score: float = 0.60           # drop low-confidence blocks

    # --- polling mode (no n8n trigger needed) ---
    poll_enabled: bool = False
    poll_interval_seconds: int = 120

    @property
    def api_key_set(self) -> set[str]:
        return {k.strip() for k in self.api_keys.split(",") if k.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
