"""Text-to-speech provider implementations."""

from __future__ import annotations

import time
from collections.abc import Callable
from html import escape as xml_escape
from io import BytesIO
from typing import Any

import httpx

from moku_backend.speech.types import (
    ProviderSpeechAudio,
    TextToSpeechError,
    TextToSpeechRequest,
)

AZURE_MP3_OUTPUT_FORMAT = "audio-48khz-96kbitrate-mono-mp3"
AZURE_TOKEN_TTL_SECONDS = 540


class GoogleTranslateTextToSpeechProvider:
    provider = "google"

    def __init__(self, gtts_type: Any | None = None) -> None:
        self._gtts_type = gtts_type

    async def synthesize(self, request: TextToSpeechRequest) -> ProviderSpeechAudio:
        language = request.language
        if not language:
            raise TextToSpeechError("Google Translate TTS requires a language.")

        gtts_type = self._gtts_type
        if gtts_type is None:
            from gtts import gTTS

            gtts_type = gTTS

        buffer = BytesIO()
        try:
            gtts_type(text=request.text, lang=language, slow=request.slow).write_to_fp(buffer)
        except Exception as exc:
            raise TextToSpeechError(f"Google Translate TTS failed: {exc}") from exc

        content = buffer.getvalue()
        if not content:
            raise TextToSpeechError("Google Translate TTS returned empty audio.")
        return ProviderSpeechAudio(content=content, provider="google", language=language)


class AzureSpeechTextToSpeechProvider:
    provider = "azure"

    def __init__(
        self,
        *,
        subscription_key: str | None,
        region: str,
        client_factory: Callable[[], Any] | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.subscription_key = subscription_key
        self.region = region
        self._client_factory = client_factory or httpx.AsyncClient
        self._clock = clock or time.monotonic
        self._token: str | None = None
        self._token_timestamp = 0.0

    async def synthesize(self, request: TextToSpeechRequest) -> ProviderSpeechAudio:
        if not self.subscription_key:
            raise TextToSpeechError("Azure Speech requires azure_speech_key.")
        if not self.region:
            raise TextToSpeechError("Azure Speech requires azure_speech_region.")
        if not request.voice:
            raise TextToSpeechError("Azure Speech TTS requires a voice.")
        if not request.language:
            raise TextToSpeechError("Azure Speech TTS requires a language.")

        token = await self._get_token()
        ssml = _build_azure_ssml(request)
        try:
            async with self._client_factory() as client:
                response = await client.post(
                    f"https://{self.region}.tts.speech.microsoft.com/cognitiveservices/v1",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/ssml+xml",
                        "X-Microsoft-OutputFormat": AZURE_MP3_OUTPUT_FORMAT,
                        "User-Agent": "moku",
                    },
                    data=ssml.encode("utf-8"),
                    timeout=20,
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise TextToSpeechError(f"Azure Speech TTS synthesis failed: {exc}") from exc

        if not response.content:
            raise TextToSpeechError("Azure Speech TTS returned empty audio.")
        return ProviderSpeechAudio(
            content=response.content,
            provider="azure",
            language=request.language,
            voice=request.voice,
        )

    async def _get_token(self) -> str:
        if self._token and (self._clock() - self._token_timestamp) < AZURE_TOKEN_TTL_SECONDS:
            return self._token

        try:
            async with self._client_factory() as client:
                response = await client.post(
                    f"https://{self.region}.api.cognitive.microsoft.com/sts/v1.0/issueToken",
                    headers={"Ocp-Apim-Subscription-Key": self.subscription_key},
                    timeout=10,
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise TextToSpeechError(f"Azure Speech token request failed: {exc}") from exc

        self._token = response.text
        self._token_timestamp = self._clock()
        return self._token


def _build_azure_ssml(request: TextToSpeechRequest) -> str:
    language = xml_escape(request.language or "", quote=True)
    voice = xml_escape(request.voice or "", quote=True)
    rate = xml_escape(request.rate or "0%", quote=True)
    text = xml_escape(request.text, quote=True)
    return (
        f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
        f'xml:lang="{language}">'
        f'<voice name="{voice}"><prosody rate="{rate}">{text}</prosody></voice>'
        "</speak>"
    )
