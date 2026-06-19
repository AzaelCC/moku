from __future__ import annotations

import json
from typing import Any

import pytest
from moku_backend.services.anki_connect_client import (
    AnkiConnectClient,
    AnkiConnectConnectionError,
    AnkiConnectResponseError,
)


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        if isinstance(self.payload, bytes):
            return self.payload
        return json.dumps(self.payload).encode("utf-8")


class FakeUrlOpen:
    def __init__(self, responses: list[object]) -> None:
        self.responses = responses
        self.requests: list[dict[str, Any]] = []
        self.timeouts: list[float] = []

    def __call__(self, request: Any, timeout: float) -> FakeResponse:
        self.requests.append(json.loads(request.data.decode("utf-8")))
        self.timeouts.append(timeout)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return FakeResponse(response)


def test_deck_names_sends_version_and_api_key() -> None:
    urlopen = FakeUrlOpen([{"result": ["Default"], "error": None}])
    client = AnkiConnectClient(
        url="http://anki.local",
        api_key="secret",
        timeout_seconds=3,
        urlopen=urlopen,
    )

    assert client.deck_names() == ["Default"]
    assert urlopen.requests == [
        {"action": "deckNames", "version": 6, "key": "secret"}
    ]
    assert urlopen.timeouts == [3]


def test_api_error_raises_response_error() -> None:
    urlopen = FakeUrlOpen([{"result": None, "error": "unsupported action"}])
    client = AnkiConnectClient(urlopen=urlopen)

    with pytest.raises(AnkiConnectResponseError, match="unsupported action"):
        client.deck_names()


def test_malformed_response_raises_response_error() -> None:
    urlopen = FakeUrlOpen([{"result": []}])
    client = AnkiConnectClient(urlopen=urlopen)

    with pytest.raises(AnkiConnectResponseError, match="unexpected response shape"):
        client.deck_names()


def test_invalid_json_raises_response_error() -> None:
    urlopen = FakeUrlOpen([b"not-json"])
    client = AnkiConnectClient(urlopen=urlopen)

    with pytest.raises(AnkiConnectResponseError, match="invalid JSON"):
        client.deck_names()


def test_connection_error_raises_connection_error() -> None:
    urlopen = FakeUrlOpen([TimeoutError("slow")])
    client = AnkiConnectClient(urlopen=urlopen)

    with pytest.raises(AnkiConnectConnectionError, match="Could not connect"):
        client.deck_names()


def test_cards_info_and_status_calls_are_batched() -> None:
    urlopen = FakeUrlOpen(
        [
            {
                "result": [
                    {"cardId": 1, "fields": {}},
                    {"cardId": 2, "fields": {}},
                ],
                "error": None,
            },
            {"result": [{"cardId": 3, "fields": {}}], "error": None},
            {"result": [False, True], "error": None},
            {"result": [False], "error": None},
        ]
    )
    client = AnkiConnectClient(batch_size=2, urlopen=urlopen)

    assert [card["cardId"] for card in client.cards_info([1, 2, 3])] == [1, 2, 3]
    assert client.are_suspended([1, 2, 3]) == {1: False, 2: True, 3: False}
    assert [request["action"] for request in urlopen.requests] == [
        "cardsInfo",
        "cardsInfo",
        "areSuspended",
        "areSuspended",
    ]
