# Local companion validation — 2026-09-27

## Scope and preserved bases

- Scaramouche: stacked on `fix/scarahelp-pagination`, base `37a8ceeedf7b51b661fd11cdaf439d70ce310175`.
- Wanderer: stacked on `feature/home-presence-bridge`, base `c0e3e60f07963f6d1399787d364144dbd3e524e0`.
- Both new heads: `feature/local-companion-agent`. Existing PRs remain unmerged.
- Canonical hub/macOS executable is in Scaramouche; Wanderer contains only the shared bot adapter/protocol and its wiring. No second relay framework, provider replacement or unrelated refactor.

## Exact completed checks

| Check | Result |
|---|---|
| Scaramouche full suite, Python 3.9.6 | **221 passed**, 1 existing urllib3/LibreSSL warning, 45.30s |
| Wanderer full suite, Python 3.9.6 | **60 passed**, 8.78s |
| Companion-only focused suite, Python 3.9.6 | **55 passed**, 13.58s |
| Companion + home relay suites, Python 3.12.14 | **113 passed**, 1 existing audioop deprecation warning, 9.29s |
| Bot import/command registration with synthetic credentials and dotenv disabled | Both passed; Scaramouche 110 commands (including scarahelp and pc), Wanderer 134 (including pc) |
| Agent CLI validate/status/disabled verify | Passed in synthetic-config test; no desktop sample or database created |
| Syntax/import checks | compileall passed for changed bot/home/agent modules |
| Shared-module parity | companion model, bot adapter, protocol, client and home adapter byte-identical |
| Patch whitespace | git diff --check passed |
| Changed-file credential-pattern scan | No matching provider tokens, GitHub tokens, AWS access IDs or private-key headers |

The focused suites overlap the full suites; these totals must not be added together.
No CI workflow or live Discord Gateway connection is implied by import/registration testing.

## Test coverage

App changes/duration buckets/deduplication; ACTIVE/IDLE/AWAY/LOCKED; stale and conflicting
presence; explicit opt-in and kill switch; sensitive app/title exclusions; screen race
discard, crop/redaction/downscale/cooldown, no screenshot files; invalid/sensitive/
low-confidence vision; free-text stripping; cross-user isolation; durable deletion retry;
offline revocation reconciled on reconnect; strict action enums; stale/replayed messages;
owner-only confirmation; audited actions; notifications disabled/allowed; quiet-hours
and bounded volume; stop during an in-flight relay action; local audio cleanup; audio
origin/path restrictions; allowlisted launch; fixed AppleScript argv boundary; no shell,
eval or remote code inputs; proactive, serious-context and shared-cooldown gates; read-only
Google due context; disabled bot/agent startup.

Network tests use actual loopback HTTP/WebSocket connections and authenticated envelopes.
OS adapters, screenshot bytes, audio devices, Apple frameworks and helper processes are
mocked. No real local app tracking, screen capture, lock, app launch, desktop notification,
audio playback, provider vision request or production deployment was performed.
PyObjC is an optional local installation, not a dependency added to the Oracle bot process.

## Preferences, persistence and limits

Everything starts disabled. Desktop config, per-device policy/capabilities, environment
switch and private owner consent all apply. Screens have additional per-app/local/remote
consent and run only on explicit `!pc look`; no background screen scheduler. Broad app
and idle polling is 10s with deduplicated events. Usable context expires at 120s and relay
disconnect clears it. RAM-only screenshot processing, no screenshot archive/temp file.
Action audits are configurable up to 30d. An additive shared preferences table tracks
opt-in/pending deletion; durable hub revocation is reconciled before new actions.
Existing memory reset and topic forget revoke companion consent conservatively.

macOS permissions and user-side smoke commands are in LOCAL_COMPANION.md. Real GUI
verification remains necessary on the user's authorized Mac. Screenshot filtering cannot
guarantee removal of all PII, provider retention is outside this code's control, and
Python cannot promise forensic RAM zeroization. Newer macOS capture APIs may require a
future adapter update; Windows/Linux deliberately remain unsupported/fail-closed.
Lock safety uses explicit opt-in, confirmation and local safe-app guards, not a claim to
understand every dangerous background workflow. Keep locking disabled where that matters.
