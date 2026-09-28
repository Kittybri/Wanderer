# Server chaos validation — 2026-09-28

## Final integrated result

Implemented reversible Server Sovereign cosmetics, shared chaos throttling, atomic fictional wagers, provenance-backed voluntary court, Scaramouche-only labeled parody/phantom ping/public-source gossip, and bounded Wanderer defense/exposure. All features remain deployment-configured OFF by default. No live configuration was changed.

The existing advanced-VC heads were preserved:
- Scaramouche: `68e2108d8c371fd2ab6e01b1ac443931e393268b` (PR 9).
- Wanderer: `17139ec6fd172d466251317bfa10ebcdfe84e871` (PR 7).

New work is on `feature/server-chaos-games`, stacked onto `feature/advanced-vc-personality`. No merging or deployment is part of this handoff.

## Files and persistence

- `server_chaos/service.py`: command routing, host distinction, consent, safe sources, scheduler and adapters.
- `server_chaos/state.py`: transactions, budget, wager settlement, bounded court coordinator, preferences and retention.
- `server_chaos/restoration.py`: original-before-edit receipts, leases, compare-before-restore, retries and audit.
- `server_chaos/errors.py`, `__init__.py`: safe public errors and package.
- `bot.py`: command/help wiring, opt-out integration, structured-duo exclusion; Scaramouche reuses Autocorrect and routes new slowmode writes through recovery.
- `memory.py`: protect structured server duo turns from ordinary chat.
- `birthday_event.py`: optional guild/receipt filters for existing emergency cleanup.
- `tests/test_server_chaos.py`: 50 focused test cases in each repository.
- `SERVER_CHAOS_GAMES.md`: configuration, commands, privacy, operations and limitations.

Only one new table, `chaos_wallet`, is introduced. Four default-OFF consent columns extend existing preferences. All other new persistent state reuses `persistent_world_events`; court coordination, cooldowns, GrudgeJournal and relationship memory reuse existing systems.

## Exact automated results

| Validation | Scaramouche | Wanderer |
| --- | --- | --- |
| Complete base suite (Python 3.9.6) | 358 passed, 3 skipped | 197 passed, 3 skipped |
| Optional voice + advanced VC + chaos (Python 3.12.14) | 140 passed | 140 passed |
| New chaos cases included above | 50 passed | 50 passed |
| Offline real bot import / command registration | 116 commands | 140 commands |
| Compile, whitespace diff and new-module formatting checks | passed | passed |

The three base skips are optional WebRTC VAD, voice receive and real Opus tests. They execute in the optional environment with discord.py 2.7.1, davey 0.1.6, PyNaCl 1.5.0, webrtcvad-wheels 2.0.14, the existing pinned voice-receive fork and a test-only Opus library. This does not change production dependencies. Existing LibreSSL warning occurs in Scaramouche's base suite; optional suites emit Python's audioop deprecation warning.

Offline imports run with dotenv disabled, an empty environment and a temporary working directory. Both actual bot modules register their four distinct new command names without starting the chaos task or enabling configuration. Scaramouche's real Autocorrect callback is present; Wanderer's is absent.

## Coverage

Tests exercise defaults and migration preservation, atomic concurrent budget/wager operations, all four random games, invalid stakes, cancellation/expiry, write-ahead values and restart reconciliation, manual changes, permission loss and deleted objects, active-receipt priority, safe cosmetic roles and own nickname, court provenance/consent/defense/verdict/duo ownership, opt-out, serious-text suppression, untouched originals, daylight restrictions, exact bot-owned ping cleanup, crash nonce recovery, public-source gossip and edited-source rejection, bounded exposure, birthday guild scoping, VC cleanup and emergency idempotence.

Final review also fixed and tested:
- Scaramouche-only character import breaking Wanderer collection: explicit optional transformation callback.
- Unavailable/disabled Wanderer cancelling the host's pending court: partner must not dismiss on missing local state.
- MANUAL mode allowing scheduled triggers: explicit mode gate.

## Evidence boundaries

Discord HTTP calls are mocked; SQLite transactions use real temporary databases. Random mechanics and optional codec/VAD paths execute locally. No Discord messages, DMs, pings, edits, roles, voice joins or server restarts were performed. Live permissions, push notifications, process restart recovery against Discord and cross-process deployment paths still require an explicitly configured staging smoke test.

Voice conversation modules, voice_handler.py, home relay and dependency manifests have zero diff against the completed advanced-VC base in both repositories. No Fish replacement or full-duplex redesign. A targeted new-file secret-pattern scan found no Groq/GitHub token or private-key patterns; this is not a comprehensive security certification.

## Deployment / limitations

See SERVER_CHAOS_GAMES.md for the complete JSON and command reference. Administrators must deploy/restart both bots, configure eligible guild/channel/cosmetic-role IDs, grant only needed permissions, and point both bots at the same shared SQLite database. Users opt in separately per bot. Nothing has been enabled on the live server.

Supported wagers use only bragging or one fictional favor token; court outcomes have no moderation consequences. Presence changes, wager roles, witnesses, trivia wagers, automatic tournament detection and grudge prizes are outside this safe subset. Existing legacy slowmode receipts without applied values require manual reconciliation. Discord offers no atomic conditional edit, so compare-before-restore cannot eliminate an exactly simultaneous admin-write race. Durable recovery needs a running bot and restored API permissions.

Opt-out cancels pending personal games and deliveries but preserves recovery, audit and accounting obligations. Terminal chaos receipts expire after 30 days; active recovery and wallet records remain. At-most-once outbound claims may suppress a message after an ambiguous network failure rather than duplicate it.
