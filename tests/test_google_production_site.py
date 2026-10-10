"""Offline assertions for public Google verification preparation."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "deploy" / "connections" / "public"


def test_site_explains_google_scopes_and_links_to_privacy():
    homepage = (PUBLIC / "index.html").read_text()
    privacy = (PUBLIC / "privacy.html").read_text()
    assert 'href="/privacy"' in homepage
    assert "Calendar" in homepage and "Tasks" in homepage
    assert "explicit" in homepage.lower() and "confirmation" in homepage
    for token in ("access and refresh tokens", "Discord user ID", "text-generation provider", "disconnect"):
        assert token in privacy
    assert "www.googleapis.com/auth/drive" not in privacy
    assert "www.googleapis.com/auth/gmail" not in privacy


def test_proxy_separates_public_pages_from_oauth():
    conf = (ROOT / "deploy" / "connections" / "nginx.conf.example").read_text()
    assert "location = / {" in conf and "location = /privacy {" in conf
    assert "proxy_pass http://127.0.0.1:8787;" in conf
    assert "oauth/google/(start/[^/]+|callback)" in conf
    assert "access_log off;" in conf


def test_wanderer_global_policy_discloses_connected_account_data_and_controls():
    from pathlib import Path
    global_privacy = (Path(__file__).resolve().parents[1] / "privacy.html").read_text()
    scoped = (PUBLIC / "privacy.html").read_text()
    for phrase in ("Wanderer", "voice audio", "face-recognition", "Google Calendar", "Google Tasks", "Limited Use", "!google disconnect"):
        assert phrase in global_privacy
    assert "Limited Use" in scoped
    assert "AI models" in scoped


def test_separate_legacy_docfix_disclosure_is_not_confused_with_oauth():
    privacy = (Path(__file__).resolve().parents[1] / "privacy.html").read_text()
    assert "Separate Legacy Google Docs Feature" in privacy
    assert "!fixdoc" in privacy
    assert "overwrite the original document" in privacy
    assert "separate from Google Connected Accounts OAuth" in privacy
