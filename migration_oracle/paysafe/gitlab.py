"""GitLab git operations: tag listing, build-file fetch, framework detection."""

from __future__ import annotations

import json
import re
import subprocess
import tarfile
import time
import xml.etree.ElementTree as ET
from io import BytesIO
from urllib.parse import quote, urlparse

import httpx
from packaging.version import InvalidVersion, Version

from migration_oracle import config
from migration_oracle.paysafe._types import CompatibilityInfoObj

_GIT_TIMEOUT_SECONDS = 30
_ARCHIVE_TIMEOUT_SECONDS = 15
_RETRIES = 2
_BACKOFF_SECONDS = [1.0, 3.0]
_HTTP_TIMEOUT_SECONDS = 15


class _GitError(Exception):
    def __init__(self, error_code: str, message: str = "") -> None:
        self.error_code = error_code
        self.message = message
        super().__init__(message or error_code)


def _project_path_from_url(repo_url: str) -> str:
    if repo_url.startswith("git@"):
        _, path = repo_url.split(":", 1)
        if path.endswith(".git"):
            path = path[:-4]
        return path
    parsed = urlparse(repo_url)
    path = parsed.path.strip("/")
    if path.endswith(".git"):
        path = path[:-4]
    return path


def _gitlab_api_base(repo_url: str) -> str | None:
    if repo_url.startswith("git@"):
        host = repo_url.split("@", 1)[1].split(":", 1)[0]
    elif repo_url.startswith("http"):
        host = urlparse(repo_url).hostname or ""
    else:
        return None
    if not host:
        return None
    return f"https://{host}/api/v4"


def _https_to_scp(url: str) -> str:
    if url.startswith("git@"):
        return url
    if not url.startswith("http"):
        return url
    parsed = urlparse(url)
    host = parsed.hostname or ""
    path = _project_path_from_url(url)
    return f"git@{host}:{path}.git"


def _auth_https_url(repo_url: str) -> str | None:
    """Authenticated HTTPS clone URL when GITLAB_API_KEY is configured."""
    token = config.GITLAB_API_KEY.strip()
    if not token or not repo_url.startswith("http"):
        return None
    parsed = urlparse(repo_url)
    host = parsed.hostname or ""
    path = parsed.path.rstrip("/")
    if not path.endswith(".git"):
        path = f"{path}.git"
    return f"https://oauth2:{quote(token, safe='')}@{host}{path}"


def _git_remote_url(repo_url: str) -> str:
    """Best URL for git network commands: HTTPS+token when configured, else SSH."""
    return _auth_https_url(repo_url) or _https_to_scp(repo_url)


def _run_git_once(
    args: list[str],
    *,
    text: bool = True,
    timeout: int = _GIT_TIMEOUT_SECONDS,
    append_repo: str | None = None,
) -> subprocess.CompletedProcess:
    cmd = ["git", *args]
    if append_repo is not None:
        cmd.append(_git_remote_url(append_repo))
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=text,
            timeout=timeout,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise _GitError("git_ls_remote_failed", f"git command failed: {cmd}") from exc
    if result.returncode != 0:
        raise _GitError(
            "git_ls_remote_failed",
            f"git command failed ({result.returncode}): {result.stderr or result.stdout}",
        )
    return result


def _run_git_with_retry(
    args: list[str],
    *,
    text: bool = True,
    append_repo: str | None = None,
) -> subprocess.CompletedProcess:
    cmd = ["git", *args]
    if append_repo is not None:
        cmd.append(_git_remote_url(append_repo))
    last_exc: Exception | None = None
    for attempt in range(_RETRIES + 1):
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=text,
                timeout=_GIT_TIMEOUT_SECONDS,
                check=False,
            )
            if result.returncode == 0:
                return result
            last_exc = subprocess.CalledProcessError(
                result.returncode, cmd, result.stdout, result.stderr
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            last_exc = exc
        if attempt < _RETRIES:
            time.sleep(_BACKOFF_SECONDS[attempt])
    raise _GitError("git_ls_remote_failed", f"git command failed: {cmd}") from last_exc


def _strip_v_prefix(tag: str) -> str:
    if tag and tag[0] in ("v", "V"):
        return tag[1:]
    return tag


def _version_token_from_tag(tag: str) -> str:
    """Extract the semver token from a git tag (plain, v-prefixed, or Maven coordinate)."""
    token = tag.rsplit("/", 1)[-1] if "/" in tag else tag
    return _strip_v_prefix(token)


def _parse_tag_version(tag: str) -> Version | None:
    try:
        return Version(_version_token_from_tag(tag))
    except InvalidVersion:
        return None


def _tag_ref_candidates(tag: str) -> list[str]:
    """Prefer the canonical tag name before optional v-prefixed git ref variants."""
    candidates = [tag]
    # Maven coordinate tags (group/artifact/version) must use the exact ref only.
    if "/" in tag:
        return candidates
    if tag.startswith(("v", "V")):
        stripped = _strip_v_prefix(tag)
        if stripped != tag:
            candidates.append(stripped)
    else:
        candidates.append(f"v{tag}")
    seen: list[str] = []
    for candidate in candidates:
        if candidate not in seen:
            seen.append(candidate)
    return seen


def _ref_to_gitlab_api_ref(ref: str) -> str:
    if ref.startswith("refs/tags/"):
        return ref[len("refs/tags/") :]
    return ref


def _fetch_file_via_gitlab_api(repo_url: str, ref: str, path: str) -> bytes | None:
    token = config.GITLAB_API_KEY.strip()
    api_base = _gitlab_api_base(repo_url)
    if not token or not api_base:
        return None

    project = quote(_project_path_from_url(repo_url), safe="")
    file_path = quote(path, safe="")
    api_ref = _ref_to_gitlab_api_ref(ref)
    url = f"{api_base}/projects/{project}/repository/files/{file_path}/raw"
    headers = {"PRIVATE-TOKEN": token}

    for candidate in _tag_ref_candidates(api_ref):
        try:
            with httpx.Client(timeout=_HTTP_TIMEOUT_SECONDS) as client:
                response = client.get(url, params={"ref": candidate}, headers=headers)
            if response.status_code == 200:
                return response.content
        except httpx.HTTPError:
            continue
    return None


def list_tags(repo_url: str) -> list[str]:
    """List git tags sorted descending by semver."""
    result = _run_git_with_retry(["ls-remote", "--tags"], append_repo=repo_url)
    raw_lines = [line for line in result.stdout.splitlines() if line.strip()]
    if not raw_lines:
        raise _GitError("no_tags_found", "Repository has no git tags")

    tag_names: set[str] = set()
    for line in raw_lines:
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        ref = parts[1].strip()
        if not ref.startswith("refs/tags/"):
            continue
        tag = ref[len("refs/tags/") :]
        if tag.endswith("^{}"):
            continue
        tag_names.add(tag)

    if not tag_names:
        raise _GitError("no_tags_found", "Repository has no git tags")

    parsed: list[tuple[Version, str]] = []
    for tag in tag_names:
        version = _parse_tag_version(tag)
        if version is not None:
            parsed.append((version, tag))

    if not parsed:
        raise _GitError("no_parseable_tags", "No tags parse as semantic versions")

    parsed.sort(key=lambda x: x[0], reverse=True)
    return [tag for _, tag in parsed]


def _archive_file(repo_url: str, ref: str, path: str) -> bytes | None:
    api_content = _fetch_file_via_gitlab_api(repo_url, ref, path)
    if api_content is not None:
        return api_content

    remote_url = _https_to_scp(repo_url)
    try:
        result = _run_git_once(
            ["archive", f"--remote={remote_url}", ref, path],
            text=False,
            timeout=_ARCHIVE_TIMEOUT_SECONDS,
        )
    except _GitError:
        return None
    if not result.stdout:
        return None
    raw = result.stdout
    try:
        with tarfile.open(fileobj=BytesIO(raw), mode="r:*") as tar:
            for member in tar.getmembers():
                if member.name.endswith(path) or member.name == path:
                    extracted = tar.extractfile(member)
                    if extracted is not None:
                        return extracted.read()
    except (tarfile.TarError, OSError):
        pass
    return raw


def _parse_pom_xml(content: bytes) -> CompatibilityInfoObj | None:
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return None

    ns = ""
    if root.tag.startswith("{"):
        ns = root.tag.split("}")[0] + "}"

    parent = root.find(f"{ns}parent")
    if parent is not None:
        artifact_id = parent.findtext(f"{ns}artifactId", "")
        version = parent.findtext(f"{ns}version", "")
        if artifact_id == "spring-boot-starter-parent" and version:
            return CompatibilityInfoObj(version, "pom.xml", "spring-boot-starter-parent")

    for prop in root.findall(f".//{ns}properties/*"):
        tag = prop.tag.replace(ns, "")
        if tag == "spring-boot.version" and prop.text:
            return CompatibilityInfoObj(
                prop.text.strip(), "pom.xml", "spring-boot.version-property"
            )

    for dep in root.findall(f".//{ns}dependencyManagement/{ns}dependencies/{ns}dependency"):
        group_id = dep.findtext(f"{ns}groupId", "")
        artifact_id = dep.findtext(f"{ns}artifactId", "")
        version = dep.findtext(f"{ns}version", "")
        if (
            group_id == "org.springframework.boot"
            and artifact_id == "spring-boot-dependencies"
            and version
        ):
            return CompatibilityInfoObj(
                version.strip(), "pom.xml", "spring-boot-dependencies-bom"
            )

    return None


def _parse_gradle(content: str, source_file: str = "build.gradle") -> CompatibilityInfoObj | None:
    patterns: list[tuple[str, str]] = [
        (
            r'id\s*\(\s*["\']org\.springframework\.boot["\']\s*\)\s*version\s*["\']([^"\']+)["\']',
            "gradle-plugin-version",
        ),
        (
            r'id\s+"org\.springframework\.boot"\s+version\s+"([^"]+)"',
            "gradle-plugin-version",
        ),
        (
            r"org\.springframework\.boot['\"]?\s+version\s+['\"]([^'\"]+)['\"]",
            "gradle-plugin-version",
        ),
        (
            r"springBootVersion\s*=\s*['\"]([^'\"]+)['\"]",
            "gradle-springBootVersion-property",
        ),
        (
            r"ext\.springBootVersion\s*=\s*['\"]([^'\"]+)['\"]",
            "gradle-springBootVersion-property",
        ),
    ]
    for pattern, precedence in patterns:
        match = re.search(pattern, content)
        if match:
            return CompatibilityInfoObj(match.group(1), source_file, precedence)
    return None


def _parse_gradle_properties(content: str) -> CompatibilityInfoObj | None:
    patterns: list[tuple[str, str]] = [
        (r"^springBootVersion\s*=\s*([^\s#]+)", "gradle-springBootVersion-property"),
        (r"^spring\.boot\.version\s*=\s*([^\s#]+)", "gradle-springBootVersion-property"),
    ]
    for line in content.splitlines():
        stripped = line.strip()
        for pattern, precedence in patterns:
            match = re.match(pattern, stripped)
            if match:
                version = match.group(1).strip().strip('"').strip("'")
                return CompatibilityInfoObj(
                    version, "gradle.properties", precedence
                )
    return None


def _parse_package_json(content: bytes) -> CompatibilityInfoObj | None:
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None

    for section in ("dependencies", "devDependencies"):
        deps = data.get(section, {})
        if isinstance(deps, dict) and "@angular/core" in deps:
            version = deps["@angular/core"]
            version = version.lstrip("^~>=<")
            return CompatibilityInfoObj(version, "package.json", "angular-core-dep")
    return None


def fetch_framework_version(repo_url: str, tag: str) -> CompatibilityInfoObj | None:
    """Fetch and parse framework version from build files at a tag."""
    # deprecated — not used by resolver v2
    for candidate in _tag_ref_candidates(tag):
        ref = f"refs/tags/{candidate}"
        info = _fetch_framework_version_at_ref(repo_url, ref)
        if info is not None:
            return info
    return None


def _fetch_framework_version_at_ref(repo_url: str, ref: str) -> CompatibilityInfoObj | None:
    pom_content = _archive_file(repo_url, ref, "pom.xml")
    if pom_content:
        info = _parse_pom_xml(pom_content)
        if info:
            return info

    for gradle_file in ("build.gradle", "build.gradle.kts"):
        gradle_content = _archive_file(repo_url, ref, gradle_file)
        if gradle_content:
            info = _parse_gradle(
                gradle_content.decode("utf-8", errors="replace"),
                source_file=gradle_file,
            )
            if info:
                return info

    gradle_props = _archive_file(repo_url, ref, "gradle.properties")
    if gradle_props:
        info = _parse_gradle_properties(
            gradle_props.decode("utf-8", errors="replace")
        )
        if info:
            return info

    pkg_content = _archive_file(repo_url, ref, "package.json")
    if pkg_content:
        info = _parse_package_json(pkg_content)
        if info:
            return info

    return None



def _head_has_file(repo_url: str, path: str) -> bool:
    content = _archive_file(repo_url, "HEAD", path)
    return content is not None and len(content) > 0


def detect_framework_at_head(repo_url: str) -> str | None:
    """Detect framework type by probing HEAD build files."""
    # deprecated — not used by resolver v2
    if _head_has_file(repo_url, "pom.xml"):
        return "spring-boot"
    if _head_has_file(repo_url, "build.gradle") or _head_has_file(repo_url, "build.gradle.kts"):
        return "spring-boot"
    if _head_has_file(repo_url, "package.json"):
        return "angular"
    return None


def _is_compatible(declared: str, target: str) -> bool:
    # deprecated — not used by resolver v2
    try:
        d = Version(declared)
        t = Version(target)
    except InvalidVersion:
        return False
    return d.major == t.major and (d.major, d.minor, d.micro) >= (t.major, t.minor, t.micro)
