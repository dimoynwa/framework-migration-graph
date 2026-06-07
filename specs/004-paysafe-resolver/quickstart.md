# Quickstart: 004-paysafe-resolver

**Branch**: `004-paysafe-resolver` | **Date**: 2026-06-06

---

## Required Environment Variables

| Variable                              | Required | Default  | Description |
|---------------------------------------|----------|----------|-------------|
| `FINDIT_AUTH_TOKEN`                   | No       | `""`     | Bearer token for FindIt API authentication |
| `FINDIT_BASE_URL`                     | No       | `https://findit-api.icd.paysafe.cloud` | FindIt registry base URL |
| `GITLAB_API_KEY`                      | No       | `""`     | GitLab credential; when empty, SSH ambient credentials are used |
| `FINDIT_SERVICE_NAME_FUZZY_THRESHOLD` | No       | `0.68`   | Minimum similarity score for fuzzy name matching (0.0–1.0) |
| `NEO4J_URI`                           | Yes*     | —        | Required by `config.py` at import time; set any valid value for tests |
| `NEO4J_PASSWORD`                      | Yes*     | —        | Required by `config.py` at import time; set any value for tests |

*`NEO4J_URI` and `NEO4J_PASSWORD` are required by `migration_oracle/config.py` at import
time even though the paysafe resolver does not use Neo4j. Set dummy values in test env.

### Minimal `.env` for testing

```bash
NEO4J_URI=bolt://localhost:7687
NEO4J_PASSWORD=test
FINDIT_AUTH_TOKEN=test-token
```

---

## Install Dependencies

```bash
uv sync
```

---

## Run All Paysafe Resolver Tests

```bash
uv run pytest tests/paysafe/ -v
```

---

## Run Individual Test Files

```bash
# FindIt client: cache TTL, four matching levels, error shapes
uv run pytest tests/paysafe/test_findit.py -v

# GitLab client: tag sort, compatibility rule, build-file parsing
uv run pytest tests/paysafe/test_gitlab.py -v

# Resolver orchestration: integration-style with mocked HTTP/git
uv run pytest tests/paysafe/test_resolver.py -v
```

---

## Mocking FindIt in Tests

Use `respx` (already in dev dependencies) to mock the FindIt HTTP endpoint:

```python
import respx
import httpx

@respx.mock
def test_findit_exact_match():
    respx.get("https://findit-api.icd.paysafe.cloud/services").mock(
        return_value=httpx.Response(200, json={
            "services": [
                {"name": "payment-service", "codeRepoLink": "https://gitlab.paysafe.com/payment/payment-service.git"}
            ]
        })
    )
    from migration_oracle.paysafe.findit import lookup
    result = lookup("payment-service")
    assert result["name"] == "payment-service"
```

---

## Mocking GitLab Git Operations in Tests

Patch `subprocess.run` in `migration_oracle.paysafe.gitlab`:

```python
from unittest.mock import patch, MagicMock

def test_list_tags(monkeypatch):
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "3.5.10\trefs/tags/3.5.10\n3.4.0\trefs/tags/3.4.0\n"
    mock_result.stderr = ""

    with patch("migration_oracle.paysafe.gitlab.subprocess.run", return_value=mock_result):
        from migration_oracle.paysafe.gitlab import list_tags
        tags = list_tags("git@gitlab.paysafe.com:payment/payment-service.git")
        assert tags[0] == "3.5.10"   # newest first
```

---

## Smoke-Test with a Real FindIt Call

Requires a valid `FINDIT_AUTH_TOKEN` and network access to `findit-api.icd.paysafe.cloud`.

```bash
FINDIT_AUTH_TOKEN=<your-token> uv run python -c "
from migration_oracle.paysafe import resolve

result = resolve(
    service_name='payment-service',
    target_version='3.5.6',
    framework='spring-boot',
    allow_latest_overall=True,
)
import json
print(json.dumps(result, indent=2))
"
```

Expected output structure:

```json
{
  "status": "ok",
  "service_name": "payment-service",
  "selected_tag": "3.5.10",
  "selected_version": "3.5.10",
  "framework": "spring-boot",
  "framework_version": "3.5.10",
  "selection_strategy": "latest_compatible",
  "target_version": "3.5.6",
  "code_repo_link": "https://gitlab.paysafe.com/...",
  "compatibility": {
    "framework_version": "3.5.10",
    "source_file": "pom.xml",
    "source_precedence": "spring-boot-starter-parent"
  },
  "effective_settings": {
    "max_tags_returned": 100,
    "git_timeout_seconds": 30,
    "retries": 2,
    "backoff_seconds": [1.0, 3.0]
  }
}
```

---

## Smoke-Test Pinned Mode (No Network Required)

```bash
uv run python -c "
from migration_oracle.paysafe.resolver import resolve

result = resolve('any-name', pinned_version='3.5.10', pinned_tag='3.5.10.A')
assert result['selection_strategy'] == 'pinned', f'Unexpected: {result}'
import json
print(json.dumps(result, indent=2))
"
```

Expected:

```json
{
  "status": "ok",
  "service_name": "any-name",
  "selected_tag": "3.5.10.A",
  "selected_version": "3.5.10",
  "framework": null,
  "framework_version": null,
  "selection_strategy": "pinned",
  "target_version": null,
  "code_repo_link": null,
  "compatibility": null,
  "effective_settings": {
    "max_tags_returned": 100,
    "git_timeout_seconds": 30,
    "retries": 2,
    "backoff_seconds": [1.0, 3.0]
  }
}
```

The assertion guards against any regression that touches pinned-mode short-circuit logic.
No FindIt or GitLab calls are made regardless of environment — this test runs offline.
