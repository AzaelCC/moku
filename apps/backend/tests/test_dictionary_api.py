from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from moku_backend.api.deps import get_session
from moku_backend.api.v1 import dictionary as dictionary_api
from moku_backend.config import Settings
from moku_backend.services.dictionary_service import (
    DictionaryLookupEntry,
    DictionaryLookupResult,
    DictionarySourceSummary,
)


async def fake_get_session() -> AsyncIterator[object]:
    yield object()


def make_app(monkeypatch, fake_service_type: type) -> FastAPI:
    monkeypatch.setattr(dictionary_api, "DictionaryService", fake_service_type)

    app = FastAPI()
    app.state.settings = Settings(_env_file=None, database_url="postgresql+asyncpg://unused/unused")
    app.include_router(dictionary_api.router, prefix="/v1")
    app.dependency_overrides[get_session] = fake_get_session
    return app


def test_dictionary_lookup_api_returns_entries_and_attribution(monkeypatch) -> None:
    seen: dict[str, object] = {}

    class FakeDictionaryService:
        def __init__(self, session: object, settings: Settings) -> None:
            pass

        async def lookup(self, **kwargs: object) -> DictionaryLookupResult:
            seen.update(kwargs)
            return DictionaryLookupResult(
                term=str(kwargs["term"]),
                language="zh_cn",
                definition_language="en",
                entries=[
                    DictionaryLookupEntry(
                        entry_id=uuid4(),
                        headword="\u5b66\u4e60",
                        forms={
                            "simplified": "\u5b66\u4e60",
                            "traditional": "\u5b78\u7fd2",
                        },
                        reading="xue2 xi2",
                        senses=[["to learn", "to study"]],
                        source=DictionarySourceSummary(
                            source_key="cc-cedict",
                            version=None,
                            license_name="CC BY-SA 4.0",
                            license_url="https://creativecommons.org/licenses/by-sa/4.0/",
                            attribution="CC-CEDICT",
                        ),
                    )
                ],
            )

    response = TestClient(make_app(monkeypatch, FakeDictionaryService)).get(
        "/v1/dictionary/lookup",
        params={
            "term": "\u5b66\u4e60",
            "language": "zh-CN",
            "definition_language": "en",
            "limit": 10,
        },
    )

    assert response.status_code == 200
    assert seen["term"] == "\u5b66\u4e60"
    assert seen["language"] == "zh-CN"
    assert seen["limit"] == 10
    payload = response.json()
    assert payload["language"] == "zh_cn"
    assert payload["entries"][0]["forms"]["traditional"] == "\u5b78\u7fd2"
    assert payload["entries"][0]["source"]["license_name"] == "CC BY-SA 4.0"


def test_dictionary_lookup_api_returns_empty_entries(monkeypatch) -> None:
    class FakeDictionaryService:
        def __init__(self, session: object, settings: Settings) -> None:
            pass

        async def lookup(self, **kwargs: object) -> DictionaryLookupResult:
            return DictionaryLookupResult(
                term=str(kwargs["term"]),
                language="zh_cn",
                definition_language="en",
                entries=[],
            )

    response = TestClient(make_app(monkeypatch, FakeDictionaryService)).get(
        "/v1/dictionary/lookup",
        params={"term": "\u4e0d\u5b58\u5728", "language": "zh-CN"},
    )

    assert response.status_code == 200
    assert response.json()["entries"] == []


def test_dictionary_lookup_api_validates_required_term(monkeypatch) -> None:
    class FakeDictionaryService:
        def __init__(self, session: object, settings: Settings) -> None:
            pass

    response = TestClient(make_app(monkeypatch, FakeDictionaryService)).get(
        "/v1/dictionary/lookup",
        params={"language": "zh-CN"},
    )

    assert response.status_code == 422
