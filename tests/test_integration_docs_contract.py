"""Docs point to correct Oracle and Google authorization boundaries."""
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_docs_protect_user_owned_google_from_legacy_bridge():
    notes = (ROOT / "GOOGLE_DOCS_SETUP.md").read_text()
    setup = (ROOT / "INTEGRATIONS_SETUP.md").read_text()
    assert "NOT live until" in notes
    assert "one-use" in notes
    assert "owner-only" in notes
    assert "not** user-owned Calendar/Tasks" in setup


def test_google_checkpoint_is_labeled_historical():
    docs = (ROOT / "CONNECTED_ACCOUNTS.md").read_text()
    assert "Current status (October 2026)" in docs
    assert "Google **Production** approval" in docs
