"""Text-to-speech domain types."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

TEXT_TO_SPEECH_CACHE_VERSION = "v1"
TEXT_TO_SPEECH_CONTENT_TYPE = "audio/mpeg"
TEXT_TO_SPEECH_EXTENSION = ".mp3"

TextToSpeechProviderName = Literal["google", "azure"]


class TextToSpeechError(Exception):
    """Raised when text-to-speech validation or synthesis fails."""


@dataclass(frozen=True)
class TextToSpeechRequest:
    text: str
    provider: TextToSpeechProviderName | None = None
    language: str | None = None
    voice: str | None = None
    rate: str | None = None
    slow: bool = False
    output_format: Literal["mp3"] = "mp3"


@dataclass(frozen=True)
class ProviderSpeechAudio:
    content: bytes
    provider: TextToSpeechProviderName
    language: str
    content_type: str = TEXT_TO_SPEECH_CONTENT_TYPE
    extension: str = TEXT_TO_SPEECH_EXTENSION
    voice: str | None = None


@dataclass(frozen=True)
class CachedSpeechAudio:
    key: str
    path: Path
    provider: TextToSpeechProviderName
    language: str
    content_type: str
    size_bytes: int
    voice: str | None = None
    rate: str | None = None
    slow: bool = False


class TextToSpeechProvider(Protocol):
    provider: TextToSpeechProviderName

    async def synthesize(self, request: TextToSpeechRequest) -> ProviderSpeechAudio:
        """Synthesize speech audio for a normalized request."""
