"""Shared data-model types for the Paysafe resolver."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypedDict

SelectionStrategy = Literal[
    "latest_compatible",
    "latest_overall",
    "latest_with_known_compatibility",
    "pinned",
]

ERROR_CODES = frozenset(
    {
        "invalid_service_name",
        "service_not_found",
        "no_repo_url",
        "no_tags_found",
        "no_parseable_tags",
        "no_compatible_version",
        "compatibility_unknown",
        "http_timeout",
        "http_request_failed",
        "git_ls_remote_failed",
    }
)


class EffectiveSettings(TypedDict):
    max_tags_returned: int
    git_timeout_seconds: int
    retries: int
    backoff_seconds: list[float]


class NameResolution(TypedDict, total=False):
    method: str
    matched_name: str
    similarity: float
    threshold_used: float
    alternatives: list[str]


class CompatibilityInfoDict(TypedDict):
    framework_version: str
    source_file: str
    source_precedence: str


class ResolverResult(TypedDict, total=False):
    status: str
    service_name: str
    selected_tag: str | None
    selected_version: str
    framework: str | None
    framework_version: str | None
    selection_strategy: str
    target_version: str | None
    code_repo_link: str | None
    compatibility: CompatibilityInfoDict | None
    effective_settings: EffectiveSettings
    name_resolution: NameResolution


class ErrorDetail(TypedDict):
    error_code: str
    message: str
    recoverable: bool
    actionable_hint: str
    details: dict


class ErrorResponse(TypedDict):
    status: str
    error: ErrorDetail


class ResolveRequest(TypedDict, total=False):
    service_name: str
    target_version: str | None
    framework: str | None
    allow_latest_overall: bool
    max_tags: int
    pinned_version: str | None
    pinned_tag: str | None


RESOLVER_RESULT_REQUIRED_KEYS = frozenset(
    {
        "status",
        "service_name",
        "selected_tag",
        "selected_version",
        "framework",
        "framework_version",
        "selection_strategy",
        "target_version",
        "code_repo_link",
        "compatibility",
        "effective_settings",
    }
)


@dataclass(frozen=True)
class CompatibilityInfo:
    framework_version: str
    source_file: str
    source_precedence: str

    def to_dict(self) -> CompatibilityInfoDict:
        return {
            "framework_version": self.framework_version,
            "source_file": self.source_file,
            "source_precedence": self.source_precedence,
        }


# Backward-compatible alias for internal modules that used CompatibilityInfoObj
CompatibilityInfoObj = CompatibilityInfo
