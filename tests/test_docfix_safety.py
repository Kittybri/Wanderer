"""Legacy Google Docs: confirmation and privacy safety contracts."""
import pathlib
from docfix_guard import DocFixPending

ROOT = pathlib.Path(__file__).parents[1]


def test_docfix_pending_is_bound_to_same_user_and_one_use():
    now = [100.0]
    pending = DocFixPending(ttl_seconds=10, clock=lambda: now[0])
    token = pending.create(11, {"revision": "r-1", "revision_text": "good"})
    assert pending.take(12, token) is None
    assert pending.take(11, token)["revision_text"] == "good"
    assert pending.take(11, token) is None


def test_expiry_and_forget_prevent_later_overwrite():
    now = [100.0]
    p = DocFixPending(ttl_seconds=10, clock=lambda: now[0])
    t = p.create(11, {"value": "one"})
    now[0] = 111.0
    assert p.take(11, t) is None
    t = p.create(11, {"value": "two"})
    p.forget(11)
    assert p.take(11, t) is None


def test_no_heuristic_auto_edit_and_revision_binding_required():
    bot = (ROOT / "bot.py").read_text()
    bridge = (ROOT / "google_docs_bridge.py").read_text()
    assert 'raw_stripped.lower().startswith("!fixdoc ")' in bot
    assert 'and _looks_like_docfix_request(raw_stripped)' not in bot
    assert 'required_revision_id=record["revision"]' in bot
    assert 'raw.lower().startswith("confirm ")' in bot
    assert "file=preview" in bot
    assert '"writeControl"] = {"requiredRevisionId": required_revision_id}' in bridge
