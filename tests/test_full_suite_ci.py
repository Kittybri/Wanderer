"""Verify the comprehensive test suite stays enabled on candidate branches."""
from pathlib import Path


def test_full_suite_workflow_is_gated_and_read_only():
    data = (Path(__file__).resolve().parents[1] / ".github/workflows/full-suite.yml").read_text()
    assert "pull_request:" in data and "push:" in data
    assert "timeout-minutes:" in data
    assert "python -m pytest -q" in data
    assert "contents: read" in data
    assert "python -m pip install -r requirements.txt pytest pytest-asyncio" in data
    assert "ssh " not in data and "oracle" not in data.lower()
