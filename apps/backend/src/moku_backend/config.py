"""Application settings."""

from __future__ import annotations

import os
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="MOKU_", extra="ignore")

    app_name: str = "Moku Backend"
    database_url: str = "postgresql+asyncpg://moku:moku@localhost:5432/moku"
    default_corpus_name: str = "sample-en"
    default_language: str = "en"
    default_learner_handle: str = "default"
    import_max_documents: int | None = Field(default=None, ge=1)
    import_max_sentences: int | None = Field(default=None, ge=1)
    min_sentence_tokens: int = Field(default=6, ge=1)
    max_sentence_tokens: int = Field(default=32, ge=1)
    anki_connect_url: str = "http://127.0.0.1:8765"
    anki_connect_api_key: str | None = None
    anki_connect_timeout_seconds: float = Field(default=10.0, gt=0)
    anki_connect_batch_size: int = Field(default=500, ge=1)
    tts_audio_dir: str = "data/audio/tts"
    tts_default_provider: Literal["google", "azure"] = "google"
    tts_default_language: str = "zh-CN"
    tts_azure_voice: str = "zh-CN-XiaoxiaoNeural"
    tts_azure_rate: str = "-10%"
    azure_speech_key: str | None = None
    azure_speech_region: str = "eastus"

    @model_validator(mode="after")
    def apply_legacy_azure_speech_env(self) -> Settings:
        if self.azure_speech_key is None:
            self.azure_speech_key = os.getenv("AZURE_SPEECH_KEY")
        if self.azure_speech_region == "eastus" and "MOKU_AZURE_SPEECH_REGION" not in os.environ:
            self.azure_speech_region = os.getenv("AZURE_SPEECH_REGION", self.azure_speech_region)
        return self
