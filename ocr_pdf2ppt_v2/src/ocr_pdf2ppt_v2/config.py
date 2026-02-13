from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_PACKAGE_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    siliconflow_api_key: str | None = None
    siliconflow_base_url: str = "https://api.siliconflow.cn/v1"
    siliconflow_model: str = "Pro/deepseek-ai/deepseek-ocr"

    model_config = SettingsConfigDict(
        env_prefix="",
        case_sensitive=False,
        extra="ignore",
        env_file=(str(_PACKAGE_ROOT / ".env"), ".env"),
    )


def get_settings() -> Settings:
    return Settings()
