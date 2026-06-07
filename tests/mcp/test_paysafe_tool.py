"""Tests for Paysafe MCP tool."""

from __future__ import annotations

import importlib
import sys
from unittest.mock import patch

from migration_oracle.mcp.tools import paysafe as paysafe_tool


def test_resolve_delegates_to_resolver():
    expected = {"status": "ok", "service_name": "my-lib", "selected_version": "1.0.0"}
    with patch("migration_oracle.mcp.tools.paysafe.resolve", return_value=expected) as mock_resolve:
        result = paysafe_tool.resolve_paysafe_dependency_by_service_name(
            service_name="my-lib",
            target_version="3.5.6",
            framework="spring-boot",
            allow_latest_overall=True,
            max_tags=50,
        )
    mock_resolve.assert_called_once_with(
        service_name="my-lib",
        target_version="3.5.6",
        framework="spring-boot",
        allow_latest_overall=True,
        max_tags=50,
        pinned_version=None,
        pinned_tag=None,
    )
    assert result is expected


def test_resolve_no_findit_import():
    module = importlib.import_module("migration_oracle.mcp.tools.paysafe")
    source = importlib.util.find_spec("migration_oracle.mcp.tools.paysafe").origin
    text = open(source, encoding="utf-8").read()
    assert "findit" not in text
    assert "gitlab" not in text
    assert "migration_oracle.paysafe.resolver import resolve" in text
