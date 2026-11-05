"""Research dossier: a free-text description of one change plus its fetched sources.

The research model writes Markdown, not JSON. The next stages (filter and
entity extraction) are LLMs that read text, so the dossier only carries what
the code itself needs: whether there is anything to append (``status``), the
description (``text``), and the pages that were actually fetched
(``sources``, set by the code, never by the model).
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

PROMPT_VERSION = 7

DossierStatus = Literal["ok", "not_found", "error"]

NOT_FOUND_MARKER = "NOT_FOUND"
ERROR_MAX_CHARS = 2000


class ResearchDossier(BaseModel):
    row_key: str
    status: DossierStatus
    # Markdown description of the change, written by the research model.
    text: str = ""
    # Pages fetched during this research and cited in ``text`` (all fetched
    # pages when the text cites none). Set by the code.
    sources: list[str] = Field(default_factory=list)
    model: str = ""
    prompt_version: int = PROMPT_VERSION
    # Why the row ended as ``status="error"``. Set by the code, never by the model.
    error: str = ""
    # Tool calls used before the error, for triage of budget/timeout failures.
    error_tool_calls: int = 0

    @field_validator("text", "model", "error", mode="before")
    @classmethod
    def _text(cls, value: object) -> str:
        if value is None:
            return ""
        return str(value)


def describe_error(exc: BaseException) -> str:
    """``Type: message`` plus the chained cause, capped for the JSONL artifact."""
    text = f"{type(exc).__name__}: {exc}".strip()
    cause = exc.__cause__ or exc.__context__
    if cause is not None and cause is not exc:
        text += f" (caused by {type(cause).__name__}: {cause})"
    return text[:ERROR_MAX_CHARS]


def error_dossier(
    row_key: str, model: str, error: str = "", *, tool_calls: int = 0
) -> ResearchDossier:
    return ResearchDossier(
        row_key=row_key,
        status="error",
        model=model,
        prompt_version=PROMPT_VERSION,
        error=(error or "unknown error")[:ERROR_MAX_CHARS],
        error_tool_calls=tool_calls,
    )


_ACTION = re.compile(r"^\s*\*\*Action:\*\*\s*(.*)$", re.MULTILINE)


def action_of(text: str) -> str:
    """``required`` / ``none`` / ``unclear`` from the ``**Action:**`` line, or ``missing``.

    Only for summary counts. Nothing downstream branches on it; the next stages
    read the text.
    """
    match = _ACTION.search(text or "")
    if not match:
        return "missing"
    value = match.group(1).strip().strip("\"'*").lower()
    if value.startswith("required"):
        return "required"
    if value.startswith("none") or value.startswith("no action"):
        return "none"
    if value.startswith("unclear"):
        return "unclear"
    return "missing"


def normalize_url(url: str) -> str:
    return url.strip().rstrip("/")


_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)
# One pass, in text order: a Markdown link, or a bare URL.
_URL = re.compile(
    r"\[(?P<label>[^\]]*)\]\((?P<link>https?://[^)\s]+)\)"
    r"|(?P<bare>https?://[^\s<>()\[\]`'\"]+)"
)
_TRAILING = ".,;:!?"


def _strip_url(url: str) -> str:
    return url.rstrip(_TRAILING)


def build_dossier(
    content: str,
    *,
    fetched_urls: set[str],
    row_key: str,
    model: str,
) -> ResearchDossier:
    """Turn the model's Markdown into a dossier.

    - Empty text or text starting with ``NOT_FOUND`` is ``not_found``.
    - Nothing fetched means nothing is grounded: ``not_found``.
    - URLs the model did not fetch are removed from the text (a Markdown link
      keeps its label), so the next stage never sees an uncited link.
    - ``sources`` lists the fetched pages the text cites, or every fetched page
      when it cites none.
    """
    text = _THINK.sub("", content or "").strip()
    fetched = {normalize_url(url): url for url in fetched_urls if url}
    if not text or text.upper().startswith(NOT_FOUND_MARKER) or not fetched:
        return ResearchDossier(
            row_key=row_key, status="not_found", model=model, prompt_version=PROMPT_VERSION
        )

    cited: list[str] = []

    def keep(url: str) -> bool:
        key = normalize_url(_strip_url(url))
        if key in fetched:
            if fetched[key] not in cited:
                cited.append(fetched[key])
            return True
        return False

    def replace(match: re.Match[str]) -> str:
        if match.group("link"):
            return match.group(0) if keep(match.group("link")) else match.group("label")
        url = match.group("bare")
        tail = url[len(_strip_url(url)) :]
        return url if keep(url) else tail

    text = _URL.sub(replace, text)
    text = re.sub(r"[ \t]+\n", "\n", text).strip()
    sources = cited or sorted(fetched.values())
    return ResearchDossier(
        row_key=row_key,
        status="ok",
        text=text,
        sources=sources,
        model=model,
        prompt_version=PROMPT_VERSION,
    )
