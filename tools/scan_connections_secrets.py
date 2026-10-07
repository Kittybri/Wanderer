"""Offline staged-file credential-pattern check; emits locations, never matched values.

This is a focused release check, not a replacement for a full secret-scanning service.
Test credentials must be obviously synthetic. The script performs no network calls.
"""
import re
import subprocess
from pathlib import Path


RULES = {
    "google_access_token": re.compile(r"ya29\.[A-Za-z0-9_-]{20,}"),
    "google_refresh_token": re.compile(r"1//[A-Za-z0-9_-]{20,}"),
    "google_client_secret": re.compile(r"GOCSPX-[A-Za-z0-9_-]{20,}"),
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "discord_token": re.compile(r"[MN][A-Za-z0-9_-]{22,27}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{27,}"),
    "connection_secret_assignment": re.compile(r"^(?:GOOGLE_OAUTH_CLIENT_SECRET|CONNECTIONS_MASTER_KEY)\s*=\s*[^\s#]+", re.M),
}


def main():
    names = subprocess.check_output(["git", "diff", "--cached", "--name-only", "--diff-filter=ACM", "-z"]).decode().split("\0")
    findings = []
    checked = 0
    for name in filter(None, names):
        text = Path(name).read_text(encoding="utf-8", errors="replace")
        checked += 1
        for rule, pattern in RULES.items():
            for match in pattern.finditer(text):
                findings.append((name, text.count("\n", 0, match.start()) + 1, rule))
    for name, line, rule in findings:
        print(f"{name}:{line}: {rule} (value redacted)")
    print(f"Staged files checked: {checked}; credential-pattern findings: {len(findings)}")
    return bool(findings)


if __name__ == "__main__":
    raise SystemExit(main())
