from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from moku_backend.config import Settings
from moku_backend.speech import (
    AzureSpeechTextToSpeechProvider,
    FileSpeechAudioCache,
    GoogleTranslateTextToSpeechProvider,
    ProviderSpeechAudio,
    TextToSpeechError,
    TextToSpeechRequest,
    TextToSpeechService,
    build_text_to_speech_service,
)
from moku_backend.speech.providers import AZURE_MP3_OUTPUT_FORMAT


class FakeProvider:
    provider = "google"

    def __init__(self) -> None:
        self.calls: list[TextToSpeechRequest] = []

    async def synthesize(self, request: TextToSpeechRequest) -> ProviderSpeechAudio:
        self.calls.append(request)
        return ProviderSpeechAudio(
            content=b"mp3-bytes",
            provider="google",
            language=request.language or "zh-CN",
        )


def make_service(tmp_path: Path, provider: FakeProvider) -> TextToSpeechService:
    return TextToSpeechService(
        providers={"google": provider},
        cache=FileSpeechAudioCache(tmp_path),
    )


async def test_empty_text_is_rejected_before_provider_or_cache(tmp_path: Path) -> None:
    provider = FakeProvider()
    service = make_service(tmp_path, provider)

    with pytest.raises(TextToSpeechError, match="text cannot be empty"):
        await service.synthesize(TextToSpeechRequest(text="   "))

    assert provider.calls == []
    assert list(tmp_path.rglob("*")) == []


async def test_cache_miss_writes_mp3_and_returns_metadata(tmp_path: Path) -> None:
    provider = FakeProvider()
    service = make_service(tmp_path, provider)

    result = await service.synthesize(TextToSpeechRequest(text=" ni hao "))

    assert len(provider.calls) == 1
    assert provider.calls[0].text == "ni hao"
    assert result.path.read_bytes() == b"mp3-bytes"
    assert result.content_type == "audio/mpeg"
    assert result.provider == "google"
    assert result.language == "zh-CN"
    assert result.size_bytes == len(b"mp3-bytes")
    assert result.path.parts[-3] == "google"
    assert result.path.suffix == ".mp3"


async def test_cache_hit_skips_provider(tmp_path: Path) -> None:
    provider = FakeProvider()
    service = make_service(tmp_path, provider)
    request = TextToSpeechRequest(text="ni hao")

    first = await service.synthesize(request)
    second = await service.synthesize(request)

    assert len(provider.calls) == 1
    assert second == first


def test_cache_keys_change_with_request_surface(tmp_path: Path) -> None:
    cache = FileSpeechAudioCache(tmp_path)
    base = TextToSpeechRequest(
        text="ni hao",
        provider="google",
        language="zh-CN",
        voice="voice-a",
        rate="-10%",
        slow=False,
    )

    keys = {
        cache.key_for(base),
        cache.key_for(replace(base, text="zaijian")),
        cache.key_for(replace(base, provider="azure")),
        cache.key_for(replace(base, language="ja-JP")),
        cache.key_for(replace(base, voice="voice-b")),
        cache.key_for(replace(base, rate="-20%")),
        cache.key_for(replace(base, slow=True)),
    }

    assert len(keys) == 7


async def test_google_provider_uses_gtts_without_network() -> None:
    class FakeGTTS:
        calls: list[dict[str, object]] = []

        def __init__(self, *, text: str, lang: str, slow: bool) -> None:
            self.calls.append({"text": text, "lang": lang, "slow": slow})

        def write_to_fp(self, buffer) -> None:
            buffer.write(b"google-mp3")

    provider = GoogleTranslateTextToSpeechProvider(gtts_type=FakeGTTS)

    audio = await provider.synthesize(
        TextToSpeechRequest(text="ni hao", provider="google", language="zh-CN", slow=True)
    )

    assert FakeGTTS.calls == [{"text": "ni hao", "lang": "zh-CN", "slow": True}]
    assert audio.content == b"google-mp3"
    assert audio.content_type == "audio/mpeg"
    assert audio.provider == "google"


class FakeHttpResponse:
    def __init__(
        self,
        *,
        text: str = "",
        content: bytes = b"",
        error: httpx.HTTPError | None = None,
    ) -> None:
        self.text = text
        self.content = content
        self.error = error

    def raise_for_status(self) -> None:
        if self.error is not None:
            raise self.error


class FakeHttpClient:
    def __init__(self, responses: list[FakeHttpResponse]) -> None:
        self.responses = responses
        self.posts: list[dict[str, object]] = []

    async def __aenter__(self) -> FakeHttpClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def post(self, url: str, **kwargs: object) -> FakeHttpResponse:
        self.posts.append({"url": url, **kwargs})
        return self.responses.pop(0)


async def test_azure_provider_requests_token_once_and_sends_escaped_ssml() -> None:
    client = FakeHttpClient(
        [
            FakeHttpResponse(text="token"),
            FakeHttpResponse(content=b"azure-mp3-1"),
            FakeHttpResponse(content=b"azure-mp3-2"),
        ]
    )
    provider = AzureSpeechTextToSpeechProvider(
        subscription_key="key",
        region="eastus",
        client_factory=lambda: client,
        clock=lambda: 1000.0,
    )
    request = TextToSpeechRequest(
        text='5 < 6 & "quoted"',
        provider="azure",
        language="zh-CN",
        voice="zh-CN-XiaoxiaoNeural",
        rate="-10%",
    )

    first = await provider.synthesize(request)
    second = await provider.synthesize(request)

    assert first.content == b"azure-mp3-1"
    assert second.content == b"azure-mp3-2"
    assert len(client.posts) == 3
    assert "issueToken" in str(client.posts[0]["url"])
    assert client.posts[0]["headers"] == {"Ocp-Apim-Subscription-Key": "key"}
    assert "cognitiveservices/v1" in str(client.posts[1]["url"])
    assert client.posts[1]["headers"]["Authorization"] == "Bearer token"
    assert client.posts[1]["headers"]["X-Microsoft-OutputFormat"] == AZURE_MP3_OUTPUT_FORMAT
    ssml = client.posts[1]["data"].decode("utf-8")
    assert 'xml:lang="zh-CN"' in ssml
    assert 'voice name="zh-CN-XiaoxiaoNeural"' in ssml
    assert 'prosody rate="-10%"' in ssml
    assert "5 &lt; 6 &amp; &quot;quoted&quot;" in ssml


async def test_azure_provider_maps_http_failures_to_tts_error() -> None:
    request = httpx.Request("POST", "https://eastus.example.test")
    response = httpx.Response(500, request=request)
    client = FakeHttpClient(
        [
            FakeHttpResponse(
                error=httpx.HTTPStatusError("token failed", request=request, response=response)
            )
        ]
    )
    provider = AzureSpeechTextToSpeechProvider(
        subscription_key="key",
        region="eastus",
        client_factory=lambda: client,
    )

    with pytest.raises(TextToSpeechError, match="token request failed"):
        await provider.synthesize(
            TextToSpeechRequest(
                text="ni hao",
                provider="azure",
                language="zh-CN",
                voice="zh-CN-XiaoxiaoNeural",
            )
        )


def test_service_factory_uses_settings(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://unused/unused",
        tts_audio_dir=str(tmp_path),
        tts_default_provider="azure",
        azure_speech_key="key",
    )

    service = build_text_to_speech_service(settings)

    assert service.cache.root == tmp_path
    assert service.default_provider == "azure"
    assert service.default_language == "zh-CN"
    assert set(service.providers) == {"google", "azure"}


def test_settings_parse_chinese_tts_defaults() -> None:
    settings = Settings(_env_file=None, database_url="postgresql+asyncpg://unused/unused")

    assert settings.tts_audio_dir == "data/audio/tts"
    assert settings.tts_default_provider == "google"
    assert settings.tts_default_language == "zh-CN"
    assert settings.tts_azure_voice == "zh-CN-XiaoxiaoNeural"
    assert settings.tts_azure_rate == "-10%"


def test_docker_compose_mounts_tts_audio_volume() -> None:
    repo_root = Path(__file__).resolve().parents[3]

    compose = (repo_root / "docker-compose.yml").read_text(encoding="utf-8")
    dockerfile = (repo_root / "apps/backend/Dockerfile").read_text(encoding="utf-8")

    assert "tts-audio:/app/data/audio/tts" in compose
    assert "MOKU_TTS_AUDIO_DIR: /app/data/audio/tts" in compose
    assert "tts-audio:" in compose
    assert "/app/data/audio/tts" in dockerfile
    assert "chown -R moku:moku /app/.cache /app/data" in dockerfile
