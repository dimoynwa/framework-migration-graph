#!/usr/bin/env bash
# Runs verification-protocol.md checks in order. Stops on first failure.
set -euo pipefail
cd "$(dirname "$0")/../.."
set -a && source .env && set +a
export FINDIT_BASE_URL="https://findit-api.icd.paysafe.cloud"
export FINDIT_AUTH_TOKEN="${FINDIT_AUTH_TOKEN#Bearer }"

run_py() { uv run python -c "$1"; }

echo "=== Level 0 ==="
run_py "import migration_oracle.paysafe, migration_oracle.paysafe.resolver, migration_oracle.paysafe.findit, migration_oracle.paysafe.gitlab, migration_oracle.paysafe._types; from migration_oracle.paysafe import resolve; print('PASS 0-A')"
run_py "from migration_oracle import config; url=config.FINDIT_BASE_URL; assert 'findit-api.icd.paysafe.cloud' in url and 'findit.paysafe.com' not in url; print(f'PASS 0-B: {url!r}')"
run_py "from migration_oracle import config; assert config.FINDIT_SERVICE_NAME_FUZZY_THRESHOLD==0.68; print('PASS 0-C')"
run_py "from migration_oracle import config; assert hasattr(config,'GITLAB_API_KEY') and isinstance(config.GITLAB_API_KEY,str); print('PASS 0-D')"
run_py "from migration_oracle.paysafe._types import ResolverResult; import typing; h=typing.get_type_hints(ResolverResult); r={'status','service_name','selected_tag','selected_version','framework','framework_version','selection_strategy','target_version','code_repo_link','compatibility','effective_settings'}; assert not r-set(h); print('PASS 0-E')"
run_py "from migration_oracle.paysafe._types import SelectionStrategy; import typing; vals=set(typing.get_args(SelectionStrategy)); exp={'latest_compatible','latest_overall','latest_with_known_compatibility','pinned'}; assert vals==exp; print(f'PASS 0-F: {sorted(vals)}')"
run_py "from migration_oracle.paysafe._types import ERROR_CODES; c={'invalid_service_name','service_not_found','no_repo_url','no_tags_found','no_parseable_tags','no_compatible_version','compatibility_unknown','http_timeout','http_request_failed','git_ls_remote_failed'}; assert not c-ERROR_CODES; print('PASS 0-G')"
! grep -rq "utcnow" migration_oracle/paysafe/ && echo "PASS 0-H"
! grep -rq "from migration_oracle\.graph\|from neo4j\|import neo4j\|from migration_oracle\.pipeline" migration_oracle/paysafe/ && echo "PASS 0-I"
! grep -rqE "os\.environ|os\.getenv" migration_oracle/paysafe/ && echo "PASS 0-J"
! grep -q "subprocess" migration_oracle/paysafe/resolver.py migration_oracle/paysafe/findit.py migration_oracle/paysafe/__init__.py migration_oracle/paysafe/_types.py 2>/dev/null && echo "PASS 0-K"

echo "=== Level 1 ==="
run_py "import inspect; from migration_oracle.paysafe.resolver import resolve; p=set(inspect.signature(resolve).parameters); assert {'service_name','target_version','framework','allow_latest_overall','max_tags','pinned_version','pinned_tag'}<=p; print('PASS 1-A')"
run_py "import inspect; from migration_oracle.paysafe.resolver import resolve; assert inspect.signature(resolve).parameters['allow_latest_overall'].default is False; print('PASS 1-B')"
run_py "import inspect; from migration_oracle.paysafe.resolver import resolve; d=inspect.signature(resolve).parameters['max_tags'].default; assert isinstance(d,int) and d>0; print(f'PASS 1-C: max_tags={d}')"
run_py "from migration_oracle.paysafe.resolver import resolve; r1=resolve(''); assert isinstance(r1,dict) and r1.get('status')=='error'; r2=resolve('x',target_version=None,framework=None); assert isinstance(r2,dict); print('PASS 1-D')"
run_py "from migration_oracle.paysafe.resolver import resolve; r=resolve(''); assert r['status']=='error' and 'error' in r and 'error_code' not in r and 'error_code' in r['error']; print(f'PASS 1-E: {r[\"error\"][\"error_code\"]!r}')"
run_py "from migration_oracle.paysafe.resolver import resolve; e=resolve('')['error']; [e[f] for f in ('error_code','message','recoverable','actionable_hint','details')]; assert isinstance(e['recoverable'],bool) and isinstance(e['details'],dict); print('PASS 1-F')"

echo "=== Level 2 + 7 (inline from protocol) ==="
echo "Running pytest suite (7-J)..."
uv run pytest tests/paysafe/ -q --tb=line
echo "PASS 7-J"
