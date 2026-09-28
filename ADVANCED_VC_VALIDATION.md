# Advanced VC integrated validation — 2026-09-28

## Preserved starting state

Both existing remote full-duplex PRs were checked again before finishing this batch:

- Scaramouche PR 8: `3342c5b279521348d4f25803dda406141a285dba`.
- Wanderer PR 6: `09d61192f515baf9a80e12b768ecc69c46e4a3a6`.

Both remain open on `feature/full-duplex-voice`. This batch uses
`feature/advanced-vc-personality`, stacked on that branch in each repository.
Existing progress was retained; no reset, framework change, production deployment,
or automatic PR merge was performed.

## Final automated results

| Check | Scaramouche | Wanderer |
| --- | --- | --- |
| Complete suite, Python 3.9.6 | 308 passed, 3 skipped | 147 passed, 3 skipped |
| Foundation + advanced voice tests, Python 3.12.14, optional DAVE/Opus stack | 90 passed | 90 passed |
| New advanced cases within these totals | 46 | 46 |
| Offline bot import and command registration | 112 commands | 136 commands |
| New commands | vcparty, vcgame | vcparty, vcgame |
| Existing voice aliases | speak, say | speak, say |
| Sessions / feature tasks on import | 0 / 0 | 0 / 0 |
| Syntax compilation; whitespace diff check | passed | passed |

The optional stack is unchanged: discord.py 2.7.1, davey 0.1.6, PyNaCl 1.5.0,
webrtcvad-wheels 2.0.14, discord-ext-voice-recv 0.5.3a181 from the pinned experimental
fork. The local validation environment uses PyAV's libopus for the existing real
codec round-trip test; no PyAV dependency was added to either repository. The three
base skips are optional receive adapter, WebRTC VAD and real Opus cases, all passing
in the optional environment. Known warnings: base Scaramouche retains urllib3's
LibreSSL warning; Python 3.12 reports audioop deprecation. Final optional runs have
no skips. No API tokens or `.env` files were loaded for offline command registration.

Reproduce from each repository:

```sh
python -m pytest -q
python -m pytest tests/test_voice_conversation.py tests/test_voice_integration.py tests/test_advanced_vc.py -q
python -m compileall -q bot.py memory.py voice_conversation tests/test_advanced_vc.py
git diff --check
```

The second command requires the documented optional receive environment and an
available libopus (`VOICE_OPUS_LIBRARY` if automatic discovery is unavailable).

## Coverage and fixes found during review

- OFF defaults, idempotent preference migration preserving existing columns,
  atomic shared cooldowns, scoped social notes, and bot/user isolation.
- Ten sensitive-parody exclusions, actual-transcript quoting, character difference,
  consent, cooldown, cache expiry, wrong-speaker exclusion, session teardown.
- Seven interruption classifications; repeated accidents do not become deliberate
  provocation; ordinary interruptions have no persistent/grudge consequence.
- Actual join/focused departure, ignoring ordinary/bot events, consent before welcome.
- Authorized asset selection, busy/TTS exclusion, cooldown, cancellation using
  the existing playback pipeline without calling STT/TTS for a sound effect.
- Atomic leased duo claims, offline-partner refusal, delivered-only advance,
  cancellation and distinct useful character roles. Real existing Memory coordinator
  test enforces two turns and prevents ordinary text replies consuming VC turns.
- No room creation/move before the exact target accepts. A failed receive startup
  restores the user; crash between creation and saved ID recovers the exact empty
  room. Manual departure is not chased; permission failure retains recovery and
  sends one notice. Listening opt-out ends the game even while the user stays in VC.
- Three-question cap, no stored answer transcript, serious game speech ends playful
  questions and routes to the foundation's protective response.
- Private-thread consent, deterministic puzzle initialization, wrong/correct answer,
  hints, participant/thread authorization, restart preservation, expiry/archive.
- Consent checked again after TTS, preventing delayed output after revocation.
  Opt-out/forget work even with guild features disabled and clear scoped partner text.
- Continuation segments reach the router as one final utterance: a harmless opening
  cannot trigger parody before its urgent/sensitive continuation is evaluated.

Existing full suites exercise memory, self-model (where present), text command/help
delivery, lifecycle, character features, soundboard, home/companion behavior and
voice state. Existing foundation tests retain DAVE attribution/decryption gates,
bot/self rejection, VAD/STT, interruption modes, provider bounds, stale-result
suppression, completed-only assistant memory and smoke-test evidence checks.

## Change inventory

New shared files: `voice_conversation/features.py`, `personality.py`, `games.py`,
`social_store.py`; `tests/test_advanced_vc.py`; this report and `ADVANCED_VC_FEATURES.md`.
Modified: `Session`/integration hooks, minimal `bot.py` wiring/help/privacy hooks,
`Memory.bump_duo_session` voice-only guard, foundation documentation link.
The shared modules/tests are identical in both repositories; personality selection
uses bot identity, with different behavior/cadence rather than cloned responses.

Persistence uses the existing preference table and shared database only. The new
tables are `vc_social`, `vc_feature_budget`, `vc_games`, `vc_presence`, and
`vc_duo_output`. All retention/caps and recovery exceptions are documented in the
feature guide. No raw audio file writes, human voice cloning, extra STT pipeline,
new provider, autonomous destructive permissions action, or forced isolation.

Fish handlers remain byte-for-byte unchanged:

- Scaramouche blob `6786eaba82c78cab15e0a5702935871914c15e03`.
- Wanderer blob `14714b5b62c2be2ff0b759a4c4ea516a5cec4d83`.

`receive.py` (`ad4ad0b31fd4dab7bd13631e68f5d9d532d701ea`) and `speech.py`
(`8a9ba0bc75fd93d8c51d948a32c1d7a5cccf3fcd`) remain unchanged in both repositories.
Dependency manifests and home/lullaby provider files are unchanged. Targeted staged
secret-pattern scans and final diff review found no added live keys/private keys.

## Live verification and known limitations

**No live calls, human STT, Fish requests, real Discord moves or production deployment
were performed. DAVE/MLS negotiation and feature Discord APIs are mocked.** Real
installed-library imports, WebRTC VAD and Opus round trips do not prove a live call.
No end-to-end latency or audible fidelity claim is made.

Manual setup remains: existing receive dependencies/FFmpeg/libopus and credentials,
allowlists, guild feature configuration, approved reaction assets, permissions,
the same physical shared database, and each person's separate per-bot consent.
Run the foundation release gate followed by the advanced smoke checklist before
production use. The receive fork remains experimental.

Priority Speaker reports permission, not activation; pinned discord.py's ordinary
speaking state can overwrite a private priority flag. No unreliable patch was added.
Parody vocabulary is deliberately narrow. Duo requests use explicit commands and
serialized turns, not simultaneous talking or automatic spoken dual summons.
Each bot can host its own interrogation style; optional simultaneous second-bot
room participation is not implemented. Escape puzzles are templates, not generated.
Archived Discord game threads remain visible to authorized participants until
separately deleted. Recovery can require administrator intervention after permission
loss; journals remain rather than falsely claiming cleanup. Forgetting local state
does not delete already-sent Discord/Groq/Fish data or backup copies.

PR links, final head SHAs and mergeability are reported at handoff rather than
embedding a self-referential commit hash in this document.
