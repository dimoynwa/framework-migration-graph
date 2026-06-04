"""Input contract from framework extractors."""

from dataclasses import dataclass


@dataclass(frozen=True)
class DocumentedChange:
    """One raw upstream change record before LLM filtering."""

    change_type: str
    confidence: str
    source_url: str
    statement: str
