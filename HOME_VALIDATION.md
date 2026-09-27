# Home bridge validation — 2026-09-27

## Scope and preservation

This batch is stacked on `feature/persistent-world-batch`, in new branches named
`feature/home-presence-bridge`. The starting completed heads were:

- Scaramouche: `7ca9c84c2ac61538c68aed4151521d32d2313929`
- Wanderer: `90ab07e6663f8f365315cf824755a36a164e7a59`

No previous PR was merged/reset, and no production service was deployed or restarted.
Fish/emotional TTS was not replaced. Changes to each existing bot entry point are
limited to home initialization, a reminder-scheduler hook, and opt-in DM speaker output.
The server/relay are canonical in Scaramouche; Wanderer only gains the common client,
protocol, command adapter and additive preferences. Those common sources match.

## Results

| Check | Result |
| --- | --- |
| Scaramouche full `python -m pytest -q`, Python 3.9.6 | **160 passed**, one existing urllib3/LibreSSL warning |
| Wanderer full `python -m pytest -q`, including root tests | **55 passed** |
| New bridge tests on Python 3.12.14 | **58 passed**, one discord.py audioop deprecation warning |
| Standalone hub and relay `--validate` with disabled mock configs | Passed; no device access |
| Real outbound loopback HTTP/WebSocket hub/relay startup | Passed in network tests, mock device providers |
| Both bot imports with no home configuration | Passed; home disabled, command registration intact |
| Syntax compilation / whitespace checks | Passed |
| Relay runtime package imports and `pip check` | Passed with Kasa 0.10.2 / PyChromecast 14.0.10 |

New Scaramouche coverage: 36 protocol/policy/privacy/storage tests, seven real
loopback transport tests, nine mocked vendor-adapter tests, six shared bot tests.
Wanderer runs those six bot-specific regression tests alongside its existing suite.

Transport tests cover authenticated roundtrips, tampering/replay, duplicate relay
connections, reconnect reconciliation, user/bot-bound confirmation, offline/no queue,
expiry/timeout, kill-switch cancellation and audit outcomes. Privacy tests cover
OwnTracks authentication/opt-in/debounce/deletion/retention/user boundaries, temporary
audio ownership/expiry and minimal audit fields. Policy tests cover modes, actor
scope, unsafe-plug automation rejection, presets/brightness/volume, printer quotas,
private-document rejection, defaults and malformed configuration. Vendor tests check
Hue verified-TLS requests, scoped Kasa outlets/cleanup, Cast identity/media activation/
cleanup and IPP completion versus submission/failure. Bot tests verify additive
preference migration, owner-only DM diagnostics, current TTS reuse, quiet gates and
safe handling of a post-action memory failure.

A targeted credential-pattern scan of new code/config/tests/docs found no private
keys or recognizable provider/GitHub tokens. New config files contain placeholders
that credential validation rejects. Source inspection found no shell/eval executor,
TLS-verification bypass, strobe operation, raw print-content operation or raw-coordinate
prompt injection. This is a focused implementation review, not a formal penetration test.

## Environment and live-verification limits

**No physical lights, plugs, speakers, printers, real phone location events or live
Discord/cloud deployment were exercised.** Network tests use real local sockets with
mock adapters; vendor tests intercept vendor requests. Actual hardware/firmware,
audible playback, TLS proxy routing, CUPS page behavior and production permissions
remain owner setup checks, not claimed successes.

A fully isolated Python 3.12 install on macOS 13 hit a cryptography native build
failure because OpenSSL development files were unavailable. A separate test venv
using the bundled OpenSSL-backed cryptography 48.0.1 installed the pinned relay
dependencies, passed imports, `pip check`, and the 58 focused tests. This does not
claim a clean Raspberry Pi/Linux installation was verified. See setup troubleshooting.

## Manual setup and bounds

Follow [HOME_INTEGRATIONS.md](HOME_INTEGRATIONS.md): create strong per-client/agent
credentials, a TLS cloud endpoint, an always-on home relay, reviewed device policies,
private OwnTracks zones and explicit user opt-ins. Everything starts disabled.

Supported boundaries are intentionally conservative: one action/relay; one hub
worker; short Cast playback (at most 12 seconds, volume <=0.5); fixed one-page print
notes (at most three attempts/device/UTC day); minimum 60-second physical-action
cooldown; maximum six actions/device/hour; 30-second command expiry; one-day zone
retention; 30-day minimal audit retention. No continuous monitoring/audio, surveillance
profile, arbitrary uploaded printing, automatic OS control or SMS gateway was added.
Already accepted physical actions, printer jobs, sent Discord DMs and backups cannot
be universally undone by a runtime disable/delete command.
