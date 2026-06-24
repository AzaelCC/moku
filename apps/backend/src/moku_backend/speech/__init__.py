"""Text-to-speech abstractions."""

from moku_backend.speech.cache import FileSpeechAudioCache
from moku_backend.speech.providers import (
    AzureSpeechTextToSpeechProvider,
    GoogleTranslateTextToSpeechProvider,
)
from moku_backend.speech.service import TextToSpeechService, build_text_to_speech_service
from moku_backend.speech.types import (
    CachedSpeechAudio,
    ProviderSpeechAudio,
    TextToSpeechError,
    TextToSpeechProvider,
    TextToSpeechRequest,
)

__all__ = [
    "AzureSpeechTextToSpeechProvider",
    "CachedSpeechAudio",
    "FileSpeechAudioCache",
    "GoogleTranslateTextToSpeechProvider",
    "ProviderSpeechAudio",
    "TextToSpeechError",
    "TextToSpeechProvider",
    "TextToSpeechRequest",
    "TextToSpeechService",
    "build_text_to_speech_service",
]
