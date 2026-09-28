# Full-duplex validation — 2026-09-27

## State preserved

New `feature/full-duplex-voice` branches are stacked on the completed
`feature/local-companion-agent` heads, verified against origin before editing:

- Scaramouche: `458f8b9a61d3a99b793f10e719d869f146675d6d` (PR 7)
- Wanderer: `ae777e1a2b48b6efa414297584c72fc033f1a571` (PR 5)

No branch resets, framework migration, PR merges or production deployment.
The receive modules and the two new test files are identical between repositories.

## Automated results

| Check | Scaramouche | Wanderer |
| --- | --- | --- |
| Complete repository suite, existing Python 3.9.6 environment | **262 passed, 3 skipped** | **101 passed, 3 skipped** |
| New voice suites, Python 3.12.14 with pinned optional dependencies and real Opus | **44 passed** | **44 passed** |
| Syntax/byte-compilation | passed | passed |
| Bot import/command registration without connecting | 110 commands | 134 commands |
| Existing voice aliases | speak, say | speak, say |
| Live sessions on import | 0 | 0 |

The 3 skips in the base environment are optional WebRTC VAD, receive-extension
adapter, and real Opus tests. All three run successfully in the separate optional
environment. The Scaramouche base suite retains its existing urllib3/LibreSSL
warning. Python 3.12 emits the expected audioop deprecation warning.

The optional environment uses discord.py 2.7.1, davey 0.1.6, PyNaCl 1.5.0,
webrtcvad-wheels 2.0.14 and the exact receive-fork commit documented in
`FULL_DUPLEX_VOICE.md`. The dependency guard verified those pins and absence of
py-cord. For local testing only, PyAV 15.1.0 supplied libopus 1.5.2; **PyAV is not
a new production dependency**. Its library path was passed through
`VOICE_OPUS_LIBRARY`. Production should install ordinary libopus and FFmpeg.

## Test evidence and limits

Tests cover attribution and bot/self exclusion; malformed/inactive receive;
bounded queues and audio; silence/noise/overlap/utterance endpoints; STT success,
empty response, HTTP failure, timeout, malformed response and stale/revoked result;
natural/keyword/off interruption gates; stale LLM/TTS/playback; completed-only
assistant memory; opt-out and disconnected/channel-deleted cleanup; owner controls;
serious-context prompt injection; legacy voice dispatch; dependency-failure behavior;
decoder DAVE-ready/authentication gates and transport-key rotation; smoke evidence.

Real components exercised: installed receive class imports, dependency validation,
WebRTC VAD on silent PCM, libopus encoding/decoding of generated PCM with valid
frame size/RMS. **DAVE/MLS session behavior is mocked in adapter tests**; no claim
of a real Discord encrypted call, live human STT, actual Fish request, or audible
end-to-end interruption is made. No live interruption latency was measured.
Synthetic timing tests establish control flow, not real-world latency.

Existing emotion/VoiceState, soundboard, home/companion, memory and other regression
tests pass. Current Fish voice handlers are byte-for-byte unchanged from the bases:

- Scaramouche Git blob: `6786eaba82c78cab15e0a5702935871914c15e03`
- Wanderer Git blob: `14714b5b62c2be2ff0b759a4c4ea516a5cec4d83`

The `bot.py` changes are limited to command/service wiring, a delivery-deferred
response flag/callback, and send-only stop calls. Normal text callers keep the
existing behavior. Existing lullaby/home provider code is not replaced.
Targeted scans of new code/tests/docs found no Groq/live-key/private-key patterns;
no credentials were added. Diff whitespace checks pass.

## Reproduction and release gate

Run `python -m pytest -q` in each repository. With the pinned optional stack and
libopus installed, run `python -m pytest tests/test_voice_conversation.py
tests/test_voice_integration.py -q`. The complete manual controlled-VC procedure
and `python -m voice_conversation.smoke` evidence checker are in
`FULL_DUPLEX_VOICE.md`.

**Release gate remains manual:** configure FFmpeg/libopus, Fish/Groq credentials,
VC allowlist and permissions; perform the real DAVE/Opus/speech/interrupt/echo test
with consenting people. The receive fork is experimental. KEYWORD mode waits for
final transcription; NATURAL mode stops on focused sustained VAD. Headphones are
recommended because exact-text echo suppression is not acoustic echo cancellation.
No raw audio archive or recording mode was implemented.
