"""Small AnkiConnect HTTP client."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Iterable
from typing import Any, Protocol


class AnkiConnectError(RuntimeError):
    """Base error raised for AnkiConnect failures."""


class AnkiConnectConnectionError(AnkiConnectError):
    """Raised when AnkiConnect cannot be reached."""


class AnkiConnectResponseError(AnkiConnectError):
    """Raised when AnkiConnect returns an API or payload error."""


class UrlOpen(Protocol):
    def __call__(self, request: urllib.request.Request, timeout: float) -> Any: ...


class AnkiConnectClient:
    api_version = 6

    def __init__(
        self,
        *,
        url: str = "http://127.0.0.1:8765",
        api_key: str | None = None,
        timeout_seconds: float = 10.0,
        batch_size: int = 500,
        urlopen: UrlOpen = urllib.request.urlopen,
    ) -> None:
        self.url = url
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.batch_size = batch_size
        self.urlopen = urlopen

    def deck_names(self) -> list[str]:
        result = self.invoke("deckNames")
        if not isinstance(result, list) or not all(isinstance(deck, str) for deck in result):
            raise AnkiConnectResponseError("AnkiConnect deckNames returned an invalid result.")
        return result

    def find_cards(self, query: str) -> list[int]:
        result = self.invoke("findCards", {"query": query})
        return self._require_int_list(result, "findCards")

    def cards_info(self, cards: Iterable[int]) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for batch in self._batches(cards):
            result = self.invoke("cardsInfo", {"cards": batch})
            if not isinstance(result, list) or not all(isinstance(card, dict) for card in result):
                raise AnkiConnectResponseError("AnkiConnect cardsInfo returned an invalid result.")
            records.extend(result)
        return records

    def are_suspended(self, cards: Iterable[int]) -> dict[int, bool]:
        return self._bools_by_card("areSuspended", cards)

    def are_due(self, cards: Iterable[int]) -> dict[int, bool]:
        return self._bools_by_card("areDue", cards)

    def invoke(self, action: str, params: dict[str, Any] | None = None) -> Any:
        payload: dict[str, Any] = {"action": action, "version": self.api_version}
        if params is not None:
            payload["params"] = params
        if self.api_key:
            payload["key"] = self.api_key

        request = urllib.request.Request(
            self.url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self.urlopen(request, timeout=self.timeout_seconds) as response:
                body = response.read()
        except (OSError, TimeoutError, urllib.error.URLError) as exc:
            raise AnkiConnectConnectionError(
                f"Could not connect to AnkiConnect at {self.url}: {exc}"
            ) from exc

        try:
            response_payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AnkiConnectResponseError("AnkiConnect returned invalid JSON.") from exc

        if not isinstance(response_payload, dict) or set(response_payload) != {
            "result",
            "error",
        }:
            raise AnkiConnectResponseError("AnkiConnect returned an unexpected response shape.")

        error = response_payload["error"]
        if error is not None:
            raise AnkiConnectResponseError(str(error))
        return response_payload["result"]

    def _bools_by_card(self, action: str, cards: Iterable[int]) -> dict[int, bool]:
        values: dict[int, bool] = {}
        for batch in self._batches(cards):
            result = self.invoke(action, {"cards": batch})
            if not isinstance(result, list) or len(result) != len(batch):
                raise AnkiConnectResponseError(
                    f"AnkiConnect {action} returned an invalid result."
                )
            values.update(
                {
                    card_id: bool(value)
                    for card_id, value in zip(batch, result, strict=True)
                    if value is not None
                }
            )
        return values

    def _batches(self, values: Iterable[int]) -> list[list[int]]:
        value_list = list(values)
        return [
            value_list[start : start + self.batch_size]
            for start in range(0, len(value_list), self.batch_size)
        ]

    def _require_int_list(self, value: Any, action: str) -> list[int]:
        if not isinstance(value, list) or not all(isinstance(item, int) for item in value):
            raise AnkiConnectResponseError(f"AnkiConnect {action} returned an invalid result.")
        return value
