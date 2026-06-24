"""Filesystem cache for synthesized speech audio."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from moku_backend.speech.types import (
    TEXT_TO_SPEECH_CACHE_VERSION,
    TEXT_TO_SPEECH_CONTENT_TYPE,
    CachedSpeechAudio,
    ProviderSpeechAudio,
    TextToSpeechRequest,
)


class FileSpeechAudioCache:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def key_for(self, request: TextToSpeechRequest) -> str:
        key_payload = {
            "version": TEXT_TO_SPEECH_CACHE_VERSION,
            "provider": request.provider,
            "text": request.text,
            "language": request.language,
            "voice": request.voice,
            "rate": request.rate,
            "slow": request.slow,
            "output_format": request.output_format,
        }
        encoded = json.dumps(
            key_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def path_for(self, request: TextToSpeechRequest) -> Path:
        key = self.key_for(request)
        return self.root / str(request.provider) / key[:2] / f"{key}.mp3"

    def get(self, request: TextToSpeechRequest) -> CachedSpeechAudio | None:
        path = self.path_for(request)
        if not path.exists():
            return None
        return self._cached_audio(request=request, path=path)

    def store(
        self,
        request: TextToSpeechRequest,
        audio: ProviderSpeechAudio,
    ) -> CachedSpeechAudio:
        path = self.path_for(request)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(audio.content)
        return self._cached_audio(request=request, path=path)

    def _cached_audio(
        self,
        *,
        request: TextToSpeechRequest,
        path: Path,
    ) -> CachedSpeechAudio:
        return CachedSpeechAudio(
            key=self.key_for(request),
            path=path,
            provider=request.provider or "google",
            language=request.language or "",
            content_type=TEXT_TO_SPEECH_CONTENT_TYPE,
            size_bytes=path.stat().st_size,
            voice=request.voice,
            rate=request.rate,
            slow=request.slow,
        )
