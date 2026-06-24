"""Text-to-speech service orchestration."""

from __future__ import annotations

from pathlib import Path

from moku_backend.config import Settings
from moku_backend.speech.cache import FileSpeechAudioCache
from moku_backend.speech.providers import (
    AzureSpeechTextToSpeechProvider,
    GoogleTranslateTextToSpeechProvider,
)
from moku_backend.speech.types import (
    CachedSpeechAudio,
    TextToSpeechError,
    TextToSpeechProvider,
    TextToSpeechProviderName,
    TextToSpeechRequest,
)


class TextToSpeechService:
    def __init__(
        self,
        *,
        providers: dict[str, TextToSpeechProvider],
        cache: FileSpeechAudioCache,
        default_provider: TextToSpeechProviderName = "google",
        default_language: str = "zh-CN",
        default_azure_voice: str = "zh-CN-XiaoxiaoNeural",
        default_azure_rate: str = "-10%",
    ) -> None:
        self.providers = dict(providers)
        self.cache = cache
        self.default_provider = default_provider
        self.default_language = default_language
        self.default_azure_voice = default_azure_voice
        self.default_azure_rate = default_azure_rate

    async def synthesize(self, request: TextToSpeechRequest) -> CachedSpeechAudio:
        normalized = self._normalize_request(request)
        cached = self.cache.get(normalized)
        if cached is not None:
            return cached

        provider = self.providers.get(normalized.provider or "")
        if provider is None:
            raise TextToSpeechError(f"Unsupported text-to-speech provider: {normalized.provider}")

        audio = await provider.synthesize(normalized)
        if not audio.content:
            raise TextToSpeechError("Text-to-speech provider returned empty audio.")
        return self.cache.store(normalized, audio)

    def _normalize_request(self, request: TextToSpeechRequest) -> TextToSpeechRequest:
        text = request.text.strip()
        if not text:
            raise TextToSpeechError("Text-to-speech text cannot be empty.")

        provider = request.provider or self.default_provider
        if provider not in self.providers:
            raise TextToSpeechError(f"Unsupported text-to-speech provider: {provider}")

        language = (request.language or self.default_language).strip()
        if not language:
            raise TextToSpeechError("Text-to-speech language cannot be empty.")

        voice = request.voice
        rate = request.rate
        if provider == "azure":
            voice = voice or self.default_azure_voice
            rate = rate or self.default_azure_rate

        return TextToSpeechRequest(
            text=text,
            provider=provider,
            language=language,
            voice=voice,
            rate=rate,
            slow=request.slow,
            output_format=request.output_format,
        )


def build_text_to_speech_service(settings: Settings) -> TextToSpeechService:
    cache = FileSpeechAudioCache(Path(settings.tts_audio_dir))
    providers: dict[str, TextToSpeechProvider] = {
        "google": GoogleTranslateTextToSpeechProvider(),
        "azure": AzureSpeechTextToSpeechProvider(
            subscription_key=settings.azure_speech_key,
            region=settings.azure_speech_region,
        ),
    }
    return TextToSpeechService(
        providers=providers,
        cache=cache,
        default_provider=settings.tts_default_provider,
        default_language=settings.tts_default_language,
        default_azure_voice=settings.tts_azure_voice,
        default_azure_rate=settings.tts_azure_rate,
    )
