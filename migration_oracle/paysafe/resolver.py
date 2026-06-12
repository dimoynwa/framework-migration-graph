"""Seven-step orchestration for Paysafe internal library version resolution."""

from __future__ import annotations

import os
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

import requests
from packaging.version import InvalidVersion, Version

_FINDIT_TIMEOUT_SECONDS = 10

_CRED_RE = re.compile(r'https?://[^:@/\s]+:[^@\s]+@|oauth2:[^@\s]+@')


def _scrub(s: str) -> str:
    return _CRED_RE.sub('<redacted>@', s)

from migration_oracle.paysafe import findit, gitlab
from migration_oracle.paysafe._types import (
    RESOLVER_RESULT_REQUIRED_KEYS,
    CompatibilityInfoObj,
    EffectiveSettings,
)
from migration_oracle.paysafe.findit import _FindItError
from migration_oracle.paysafe.gitlab import _GitError


def _build_effective_settings(max_tags: int) -> EffectiveSettings:
    return {
        "max_tags_returned": max_tags,
        "git_timeout_seconds": 30,
        "retries": 2,
        "backoff_seconds": [1.0, 3.0],
    }


def _build_error(
    error_code: str,
    message: str,
    *,
    recoverable: bool,
    actionable_hint: str,
    details: dict | None = None,
) -> dict:
    message = _scrub(message)
    return {
        "status": "error",
        "error": {
            "error_code": error_code,
            "message": message,
            "recoverable": recoverable,
            "actionable_hint": actionable_hint,
            "details": details or {},
        },
    }


def _build_result(**kwargs) -> dict:
    allowed = RESOLVER_RESULT_REQUIRED_KEYS | {"name_resolution"}
    extra = set(kwargs) - allowed
    if extra:
        raise ValueError(f"Unexpected ResolverResult keys: {extra}")
    missing = RESOLVER_RESULT_REQUIRED_KEYS - set(kwargs)
    if missing:
        raise ValueError(f"Missing required ResolverResult keys: {missing}")
    return dict(kwargs)


def _parse_selected_version(tag: str | None, pinned_version: str | None = None) -> str:
    if pinned_version:
        return pinned_version
    if tag is None:
        return ""
    cleaned = tag[1:] if tag and tag[0] in ("v", "V") else tag
    try:
        return str(Version(cleaned))
    except InvalidVersion:
        return cleaned


def resolve(
    service_name: str,
    target_version: str | None = None,
    framework: str | None = None,
    allow_latest_overall: bool = False,  # The MCP layer sets allow_latest_overall — resolver never defaults this to True
    max_tags: int = 100,
    pinned_version: str | None = None,
    pinned_tag: str | None = None,
) -> dict:
    """Resolve the newest compatible Paysafe internal library version."""
    try:
        # Step 1: pinned short-circuit
        if pinned_version:
            result = _build_result(
                status="ok",
                service_name=service_name,
                selected_tag=pinned_tag,
                selected_version=pinned_version,
                framework=None,
                framework_version=None,
                selection_strategy="pinned",
                target_version=target_version,
                code_repo_link=None,
                compatibility=None,
                effective_settings=_build_effective_settings(max_tags),
            )
            assert "name_resolution" not in result
            return result

        # Step 2: validate service_name
        if not service_name or not service_name.strip():
            return _build_error(
                "invalid_service_name",
                "service_name must not be blank or whitespace-only.",
                recoverable=False,
                actionable_hint="Provide a non-empty Paysafe service name.",
                details={"input_name": service_name},
            )

        # Step 3: FindIt lookup (time-bounded to avoid hanging on unresponsive backend)
        _fi_executor = ThreadPoolExecutor(max_workers=1)
        try:
            _fi_future = _fi_executor.submit(findit.lookup, service_name)
            try:
                findit_record = _fi_future.result(timeout=_FINDIT_TIMEOUT_SECONDS)
            except FuturesTimeout:
                _fi_executor.shutdown(wait=False)
                return _build_error(
                    "findit_timeout",
                    f"FindIt did not respond within {_FINDIT_TIMEOUT_SECONDS}s for {service_name!r}.",
                    recoverable=True,
                    actionable_hint="Retry the request or check network connectivity to FindIt.",
                    details={"service_name": service_name, "timeout_seconds": _FINDIT_TIMEOUT_SECONDS},
                )
            _fi_executor.shutdown(wait=False)
        except _FindItError as exc:
            if exc.error_code == "service_not_found":
                return _build_error(
                    exc.error_code,
                    exc.message or f"No FindIt service matched {service_name!r}.",
                    recoverable=False,
                    actionable_hint="Verify the service name against the FindIt registry.",
                    details=exc.details,
                )
            if exc.error_code == "http_timeout":
                return _build_error(
                    exc.error_code,
                    exc.message or "FindIt request timed out.",
                    recoverable=True,
                    actionable_hint="Retry the request or check network connectivity to FindIt.",
                    details=exc.details,
                )
            if exc.error_code == "http_request_failed":
                return _build_error(
                    exc.error_code,
                    exc.message or "FindIt request failed.",
                    recoverable=True,
                    actionable_hint="Check FindIt availability and authentication token.",
                    details=exc.details,
                )
            return _build_error(
                exc.error_code,
                exc.message or "FindIt lookup failed.",
                recoverable=True,
                actionable_hint="Check FindIt configuration.",
                details=exc.details,
            )

        name_resolution = findit_record.pop("name_resolution", None)

        # Step 4: extract codeRepoLink
        code_repo_link = findit_record.get("codeRepoLink")
        if not code_repo_link:
            return _build_error(
                "no_repo_url",
                f"FindIt record for {service_name!r} has no codeRepoLink.",
                recoverable=False,
                actionable_hint="Ensure the service is registered in FindIt with a GitLab repo URL.",
                details={"service_name": service_name},
            )

        # Step 5: list tags
        try:
            tags = gitlab.list_tags(code_repo_link)
        except _GitError as exc:
            if exc.error_code == "git_ls_remote_failed":
                artifactory_base = os.environ.get("ARTIFACTORY_BASE_URL", "").rstrip("/")
                if not artifactory_base:
                    return _build_error(
                        exc.error_code,
                        exc.message or "git ls-remote failed.",
                        recoverable=True,
                        actionable_hint="Check GitLab access credentials and repository URL.",
                        details={"repo_url": code_repo_link},
                    )
                try:
                    url = f"{artifactory_base}/api/search/latestVersion?a={service_name}"
                    resp = requests.get(url, timeout=10)
                    if resp.ok and resp.text.strip():
                        tags = [resp.text.strip()]
                    else:
                        return _build_error(
                            "git_ls_remote_failed",
                            "GitLab failed and Artifactory returned no version.",
                            recoverable=True,
                            actionable_hint="Check GitLab access and Artifactory repository.",
                            details={"repo_url": code_repo_link},
                        )
                except Exception:
                    return _build_error(
                        "git_ls_remote_failed",
                        "GitLab failed and Artifactory fallback also failed.",
                        recoverable=True,
                        actionable_hint="Check GitLab access credentials and Artifactory availability.",
                        details={"repo_url": code_repo_link},
                    )
            elif exc.error_code == "no_tags_found":
                return _build_error(
                    exc.error_code,
                    exc.message or "Repository has no git tags.",
                    recoverable=False,
                    actionable_hint="Ensure the repository has version tags.",
                    details={"repo_url": code_repo_link},
                )
            elif exc.error_code == "no_parseable_tags":
                return _build_error(
                    exc.error_code,
                    exc.message or "No tags parse as semantic versions.",
                    recoverable=False,
                    actionable_hint="Ensure tags follow semver conventions.",
                    details={"repo_url": code_repo_link},
                )
            else:
                return _build_error(
                    exc.error_code,
                    exc.message or "Git tag listing failed.",
                    recoverable=True,
                    actionable_hint="Check GitLab repository access.",
                    details={"repo_url": code_repo_link},
                )

        # Step 6: scan tags
        compatible_tags: list[tuple[str, CompatibilityInfoObj]] = []
        unknown_tags: list[str] = []
        overall_tags: list[str] = []
        incompatible_found = False

        for tag in tags[:max_tags]:
            overall_tags.append(tag)
            info = gitlab.fetch_framework_version(code_repo_link, tag)
            if info is None:
                unknown_tags.append(tag)
                continue

            if target_version is None:
                continue

            if gitlab._is_compatible(info.framework_version, target_version):
                compatible_tags.append((tag, info))
            else:
                incompatible_found = True

        # Step 7: strategy selection
        detected_framework = framework
        if target_version is None:
            detected_framework = detected_framework or gitlab.detect_framework_at_head(
                code_repo_link
            )

        if target_version is not None and compatible_tags:
            best_tag, best_info = compatible_tags[0]
            result_kwargs = dict(
                status="ok",
                service_name=service_name,
                selected_tag=best_tag,
                selected_version=_parse_selected_version(best_tag),
                framework=detected_framework,
                framework_version=best_info.framework_version,
                selection_strategy="latest_compatible",
                target_version=target_version,
                code_repo_link=code_repo_link,
                compatibility=best_info.to_dict(),
                effective_settings=_build_effective_settings(max_tags),
            )
            if name_resolution is not None:
                result_kwargs["name_resolution"] = name_resolution
            return _build_result(**result_kwargs)

        if target_version is not None and allow_latest_overall and overall_tags:
            best_tag = overall_tags[0]
            best_info = gitlab.fetch_framework_version(code_repo_link, best_tag)
            result_kwargs = dict(
                status="ok",
                service_name=service_name,
                selected_tag=best_tag,
                selected_version=_parse_selected_version(best_tag),
                framework=detected_framework,
                framework_version=best_info.framework_version if best_info else None,
                selection_strategy="latest_overall",
                target_version=target_version,
                code_repo_link=code_repo_link,
                compatibility=None,
                effective_settings=_build_effective_settings(max_tags),
            )
            if name_resolution is not None:
                result_kwargs["name_resolution"] = name_resolution
            return _build_result(**result_kwargs)

        if target_version is None and overall_tags:
            best_tag = overall_tags[0]
            best_info = gitlab.fetch_framework_version(code_repo_link, best_tag)
            if best_info is not None:
                result_kwargs = dict(
                    status="ok",
                    service_name=service_name,
                    selected_tag=best_tag,
                    selected_version=_parse_selected_version(best_tag),
                    framework=detected_framework,
                    framework_version=best_info.framework_version,
                    selection_strategy="latest_with_known_compatibility",
                    target_version=None,
                    code_repo_link=code_repo_link,
                    compatibility=best_info.to_dict(),
                    effective_settings=_build_effective_settings(max_tags),
                )
            else:
                result_kwargs = dict(
                    status="ok",
                    service_name=service_name,
                    selected_tag=best_tag,
                    selected_version=_parse_selected_version(best_tag),
                    framework=detected_framework,
                    framework_version=None,
                    selection_strategy="latest_overall",
                    target_version=None,
                    code_repo_link=code_repo_link,
                    compatibility=None,
                    effective_settings=_build_effective_settings(max_tags),
                )
            if name_resolution is not None:
                result_kwargs["name_resolution"] = name_resolution
            return _build_result(**result_kwargs)

        if target_version is not None:
            if incompatible_found:
                return _build_error(
                    "no_compatible_version",
                    f"No tag compatible with target version {target_version!r}.",
                    recoverable=False,
                    actionable_hint="Try a different target version or set allow_latest_overall=True.",
                    details={
                        "target_version": target_version,
                        "tags_scanned": min(len(tags), max_tags),
                    },
                )
            return _build_error(
                "compatibility_unknown",
                "All scanned tags have unreadable or missing framework versions.",
                recoverable=False,
                actionable_hint="Ensure build files declare framework versions at tag refs.",
                details={
                    "target_version": target_version,
                    "tags_scanned": min(len(tags), max_tags),
                },
            )

        return _build_error(
            "no_tags_found",
            "No tags available for resolution.",
            recoverable=False,
            actionable_hint="Ensure the repository has version tags.",
            details={"repo_url": code_repo_link},
        )

    except Exception as exc:
        return _build_error(
            "internal_error",
            f"Unexpected resolver error: {exc}",
            recoverable=True,
            actionable_hint="Report this error to the migration-oracle maintainers.",
            details={"exception_type": type(exc).__name__},
        )
