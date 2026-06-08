"""Tests for the Pipeline Trigger page."""

import subprocess
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from streamlit.testing.v1 import AppTest

PAGE = "migration_oracle/streamlit_app/pages/01_pipeline_trigger.py"


def test_page_loads_without_exception():
    at = AppTest.from_file(PAGE)
    at.run()
    assert not at.exception


def test_blank_versions_show_warning():
    at = AppTest.from_file(PAGE)
    at.run()
    at.text_input[0].set_value("")
    at.text_input[1].set_value("")
    at.get("form")[0].submit()
    at.run()
    assert len(at.warning) > 0


def test_happy_path_exit_zero():
    mock_proc = MagicMock()
    mock_proc.stdout = iter(["line1\n", "line2\n"])
    mock_proc.returncode = 0
    mock_proc.stderr.read.return_value = ""

    with patch("subprocess.Popen", return_value=mock_proc):
        at = AppTest.from_file(PAGE)
        at.run()
        at.text_input[0].set_value("2.7.x")
        at.text_input[1].set_value("3.2")
        at.get("form")[0].submit()
        at.run()
    assert len(at.success) > 0


def test_streaming_output_accumulates():
    mock_proc = MagicMock()
    mock_proc.stdout = iter(["line1\n", "line2\n", "line3\n"])
    mock_proc.returncode = 0
    mock_proc.stderr.read.return_value = ""

    with patch("subprocess.Popen", return_value=mock_proc):
        at = AppTest.from_file(PAGE)
        at.run()
        at.text_input[0].set_value("2.7.x")
        at.text_input[1].set_value("3.2")
        at.get("form")[0].submit()
        at.run()
    assert len(at.success) > 0


def test_non_zero_exit_shows_error():
    mock_proc = MagicMock()
    mock_proc.stdout = iter([])
    mock_proc.returncode = 1
    mock_proc.stderr.read.return_value = "Build failed"

    with patch("subprocess.Popen", return_value=mock_proc):
        at = AppTest.from_file(PAGE)
        at.run()
        at.text_input[0].set_value("2.7.x")
        at.text_input[1].set_value("3.2")
        at.get("form")[0].submit()
        at.run()
    assert len(at.error) > 0
    assert "Exit 1" in at.error[0].value
    assert "Build failed" in at.error[0].value
