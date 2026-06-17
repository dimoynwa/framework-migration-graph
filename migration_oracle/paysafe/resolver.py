"""Seven-step orchestration for Paysafe internal library version resolution."""

from __future__ import annotations

import logging
import os
import re

import requests
from packaging.version import InvalidVersion, Version

_CRED_RE = re.compile(r'https?://[^:@/\s]+:[^@\s]+@|oauth2:[^@\s]+@')

_logger = logging.getLogger(__name__)


def _scrub(s: str) -> str:
    return _CRED_RE.sub('<redacted>@', s)

from migration_oracle.paysafe import findit, gitlab
from migration_oracle.paysafe._types import (
    RESOLVER_RESULT_REQUIRED_KEYS,
    EffectiveSettings,
)
from migration_oracle.paysafe.findit import _FindItError
from migration_oracle.paysafe.gitlab import _GitError, _version_token_from_tag


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


def _error_no_compatible_version(target_version: str, tags_scanned: int) -> dict:
    # unreachable in resolver v2 — retained for reference
    return _build_error(
        "no_compatible_version",
        f"No tag compatible with target version {target_version!r}.",
        recoverable=False,
        actionable_hint="Try a different target version or set allow_latest_overall=True.",
        details={
            "target_version": target_version,
            "tags_scanned": tags_scanned,
        },
    )


def _error_compatibility_unknown(target_version: str, tags_scanned: int) -> dict:
    # unreachable in resolver v2 — retained for reference
    return _build_error(
        "compatibility_unknown",
        "All scanned tags have unreadable or missing framework versions.",
        recoverable=False,
        actionable_hint="Ensure build files declare framework versions at tag refs.",
        details={
            "target_version": target_version,
            "tags_scanned": tags_scanned,
        },
    )


def _build_resolution_failed(
    sub_status: str,
    failure_reason: str,
    service_name: str,
    remediation_steps: list[str] | None = None,
) -> dict:
    """Build a typed RESOLUTION_FAILED envelope for auth/transport failures."""
    if sub_status == "auth_error":
        steps = remediation_steps or [
            "Set FINDIT_AUTH_TOKEN env var: export FINDIT_AUTH_TOKEN=<token>",
            "Set GITLAB_API_KEY env var: export GITLAB_API_KEY=<token>",
        ]
    else:
        steps = remediation_steps or [
            "Check VPN connection",
            "Verify FINDIT_BASE_URL is reachable: curl -s $FINDIT_BASE_URL/health",
        ]
    return {
        "status": "RESOLUTION_FAILED",
        "subStatus": sub_status,
        "failureReason": _scrub(failure_reason),
        "remediationSteps": steps,
        "unresolvedDependencies": [service_name],
        "fallbackInstructions": (
            "Run gradle dependencies --configuration runtimeClasspath and inspect output manually"
        ),
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
    cleaned = _version_token_from_tag(tag)
    try:
        return str(Version(cleaned))
    except InvalidVersion:
        return cleaned


def _handle_findit_error(exc: _FindItError, service_name: str) -> dict:
    if exc.error_code == "service_not_found":
        return _build_error(
            exc.error_code,
            exc.message or f"No FindIt service matched {service_name!r}.",
            recoverable=False,
            actionable_hint="Verify the service name against the FindIt registry.",
            details=exc.details,
        )
    if exc.error_code == "http_timeout":
        return _build_resolution_failed(
            "transport_error",
            exc.message or "FindIt request timed out.",
            service_name,
        )
    if exc.error_code == "http_request_failed":
        status_code = exc.details.get("status_code", 0)
        if status_code in (401, 403):
            return _build_resolution_failed(
                "auth_error",
                exc.message or f"FindIt returned HTTP {status_code} — authentication failed.",
                service_name,
            )
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


def resolve(
    service_name: str,
    target_version: str | None = None,
    framework: str | None = None,
    allow_latest_overall: bool = False,  # The MCP layer sets allow_latest_overall — resolver never defaults this to True
    max_tags: int = 15,
    pinned_version: str | None = None,
    pinned_tag: str | None = None,
) -> dict:
    """Resolve the newest compatible Paysafe internal library version."""
    try:
        if allow_latest_overall is False:
            _logger.warning(
                "allow_latest_overall=False is ignored in resolver v2; "
                "latest_overall is always returned."
            )

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

        # Step 2b: check auth token availability
        if not os.environ.get("FINDIT_AUTH_TOKEN", ""):
            return _build_resolution_failed(
                "auth_error",
                "FINDIT_AUTH_TOKEN environment variable is not set or empty.",
                service_name,
            )

        # Step 3 (v2): cache lookup with per-call fallback
        try:
            code_repo_link = findit.get_repo_link(service_name)
        except _FindItError as exc:
            return _handle_findit_error(exc, service_name)

        if not code_repo_link:
            return _build_error(
                "no_repo_url",
                f"No codeRepoLink found for {service_name!r} in cache or FindIt.",
                recoverable=False,
                actionable_hint=(
                    "Check that the service is registered in FindIt or add it to "
                    "migration_oracle/paysafe/static_registry.json."
                ),
                details={"service_name": service_name},
            )

        version_file = findit.get_version_file(service_name)
        if version_file:
            subproject_version = gitlab.fetch_gradle_subproject_version(
                code_repo_link, version_file
            )
            if not subproject_version:
                return _build_error(
                    "subproject_version_not_found",
                    f"Could not read version from {version_file!r} at HEAD in {code_repo_link}.",
                    recoverable=False,
                    actionable_hint=(
                        "Ensure the static registry versionFile path is correct and declares "
                        'version "X.Y.Z" in the Gradle file.'
                    ),
                    details={
                        "service_name": service_name,
                        "version_file": version_file,
                        "repo_url": code_repo_link,
                    },
                )
            return _build_result(
                status="ok",
                service_name=service_name,
                selected_tag=None,
                selected_version=subproject_version,
                framework=framework,
                framework_version=None,
                selection_strategy="latest_overall",
                target_version=target_version,
                code_repo_link=code_repo_link,
                compatibility=None,
                effective_settings=_build_effective_settings(max_tags),
            )

        # Step 5 (v2): list tags, return the first (latest) one
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

        best_tag = tags[0]

        return _build_result(
            status="ok",
            service_name=service_name,
            selected_tag=best_tag,
            selected_version=_parse_selected_version(best_tag),
            framework=framework,
            framework_version=None,
            selection_strategy="latest_overall",
            target_version=target_version,
            code_repo_link=code_repo_link,
            compatibility=None,
            effective_settings=_build_effective_settings(max_tags),
        )

    except Exception as exc:
        return _build_error(
            "internal_error",
            f"Unexpected resolver error: {exc}",
            recoverable=True,
            actionable_hint="Report this error to the migration-oracle maintainers.",
            details={"exception_type": type(exc).__name__},
        )
