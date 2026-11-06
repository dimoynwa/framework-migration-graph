"""Pluggable System-1 classifier client.

The default adapter speaks the local deployment: ``POST {base}{path}`` with
``model``, ``state``, and typed ``questions``. A 4xx is a bug in our request
and disables triage for the run. 5xx and timeouts are retried twice per row.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Awaitable, Callable
from typing import Protocol

import httpx

from migration_oracle import config
from migration_oracle.pipeline.triage.questions import Question
from migration_oracle.pipeline.triage.settings import TriageSettings

logger = logging.getLogger("migration_oracle.pipeline.triage")

Sleep = Callable[[float], Awaitable[None]]
_RETRY_BACKOFF_SEC = (0.5, 1.0)
_rejected_logged = False
_unreachable_logged = False


def reset_client_notices() -> None:
    """Allow tests to observe the one-per-run error and warning again."""
    global _rejected_logged, _unreachable_logged
    _rejected_logged = False
    _unreachable_logged = False


class TriageRejected(Exception):
    """HTTP 4xx. The request is wrong; triage must stop for the run."""

    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


class TriageUnavailable(Exception):
    """The endpoint could not be reached on the first request."""


class TriageTransportError(Exception):
    """5xx or timeout after retries. The row is kept; the run continues."""


class TriageClient(Protocol):
    async def classify(
        self, state: str, questions: dict[str, Question]
    ) -> dict[str, dict]: ...


def emit(level: int, message: str) -> None:
    logger.log(level, message)
    stream = sys.stderr if level >= logging.WARNING else sys.stdout
    print(message, file=stream)


class System1HttpClient:
    """HTTP adapter for the local System-1 deployment."""

    def __init__(
        self,
        settings: TriageSettings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Sleep | None = None,
    ) -> None:
        self._settings = settings
        self._sleep = sleep
        self._http_successes = 0
        self._rejected = False
        self.input_tokens = 0
        headers: dict[str, str] = {}
        if settings.api_key:
            headers["Authorization"] = f"Bearer {settings.api_key}"
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.timeout_sec),
            verify=config.SSL_VERIFY,
            headers=headers,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> System1HttpClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def classify(
        self, state: str, questions: dict[str, Question]
    ) -> dict[str, dict]:
        answers, _usage = await self.classify_request(state, questions)
        return answers

    async def classify_request(
        self, state: str, questions: dict[str, Question]
    ) -> tuple[dict[str, dict], dict]:
        if self._rejected:
            raise TriageRejected("triage disabled after HTTP 4xx", 400)
        body = {
            "model": self._settings.model,
            "state": state,
            "questions": questions,
        }
        last_error: Exception | None = None
        attempts = len(_RETRY_BACKOFF_SEC) + 1
        for attempt in range(attempts):
            try:
                response = await self._client.post(
                    self._settings.endpoint_url, json=body
                )
            except httpx.ConnectError as exc:
                last_error = exc
                if self._http_successes == 0:
                    if attempt + 1 < attempts:
                        await self._backoff(attempt)
                        continue
                    _warn_unreachable()
                    raise TriageUnavailable(str(exc)) from exc
                raise TriageTransportError(str(exc)) from exc
            except httpx.TimeoutException as exc:
                last_error = exc
                if attempt + 1 < attempts:
                    await self._backoff(attempt)
                    continue
                raise TriageTransportError(str(exc)) from exc
            except httpx.TransportError as exc:
                last_error = exc
                if attempt + 1 < attempts:
                    await self._backoff(attempt)
                    continue
                raise TriageTransportError(str(exc)) from exc

            if response.status_code >= 500:
                last_error = TriageTransportError(
                    f"HTTP {response.status_code}: {response.text[:300]}"
                )
                if attempt + 1 < attempts:
                    await self._backoff(attempt)
                    continue
                raise last_error
            if response.status_code >= 400:
                self._rejected = True
                message = _error_message(response)
                _log_rejected(response.status_code, message)
                raise TriageRejected(message, response.status_code)

            try:
                payload = response.json()
            except ValueError as exc:
                raise TriageTransportError("triage response was not JSON") from exc
            if not isinstance(payload, dict) or not isinstance(payload.get("answers"), dict):
                raise TriageTransportError("triage response has no answers object")
            usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
            tokens = _as_int(usage.get("input_tokens"))
            self.input_tokens += tokens
            self._http_successes += 1
            return payload["answers"], {"input_tokens": tokens}

        raise TriageTransportError(str(last_error or "triage request failed"))

    async def _backoff(self, attempt: int) -> None:
        delay = _RETRY_BACKOFF_SEC[min(attempt, len(_RETRY_BACKOFF_SEC) - 1)]
        sleep = self._sleep
        if sleep is None:
            import asyncio

            await asyncio.sleep(delay)
        else:
            await sleep(delay)


class FakeTriageClient:
    """Deterministic client for tests. ``answers`` may be a dict, a list, or a callable."""

    def __init__(
        self,
        answers: dict | list | Callable[[str, dict], dict] | Exception,
    ) -> None:
        self._answers = answers
        self.calls: list[tuple[str, dict]] = []
        self._index = 0
        self.input_tokens = 0

    async def aclose(self) -> None:
        return None

    async def classify(
        self, state: str, questions: dict[str, Question]
    ) -> dict[str, dict]:
        answers, _usage = await self.classify_request(state, questions)
        return answers

    async def classify_request(
        self, state: str, questions: dict[str, Question]
    ) -> tuple[dict[str, dict], dict]:
        self.calls.append((state, questions))
        supplied = self._answers
        if isinstance(supplied, Exception):
            raise supplied
        if isinstance(supplied, list):
            item = supplied[self._index]
            self._index += 1
            if isinstance(item, Exception):
                raise item
            return item, {}
        if callable(supplied):
            return supplied(state, questions), {}
        return supplied, {}


def _warn_unreachable() -> None:
    global _unreachable_logged
    if _unreachable_logged:
        return
    _unreachable_logged = True
    emit(
        logging.WARNING,
        "Triage endpoint unreachable; keeping every row with triage source error.",
    )


def _log_rejected(status_code: int, message: str) -> None:
    global _rejected_logged
    if _rejected_logged:
        return
    _rejected_logged = True
    emit(
        logging.ERROR,
        "Triage request rejected "
        f"(HTTP {status_code}): {message}. Disabling triage for this run.",
    )


def _error_message(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text[:500]
    if isinstance(body, dict) and body.get("error"):
        return str(body["error"])
    return response.text[:500]


def _as_int(value: object) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0
