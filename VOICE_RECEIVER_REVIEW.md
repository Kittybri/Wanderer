# Wanderer receive-listener lifecycle repair

Base release SHA: 3b998a71b3f3d75c14b7eeef00932e31c60569a5

## Evidence
The receive callback previously set failed to bool(error), so an unexpectedly ended reader with error=None could leave the failure flag false. The health check watched the voice connection but not whether a started receiver was still listening. A connected bot could therefore become deaf without reporting a receiver failure.

## Changes
- Track successful receiver startup and check an active reader's is_listening() state.
- Treat unexpected reader completion, even without an exception, as failure.
- Keep normal intentional stop free of false failure reports.
- Add six no-network regression tests.
- Update only the receive.py SHA-256 in the voice-preservation baseline to describe this user-authorized voice repair. Old: 06b5d5ed0da70e30714539b658e937a2e2fafaa8d23ffd961ab88706a6cf7486. New: 6e3dd7a9c2376cfc506717e7ffb2706e582c2391b463f8452cc2e745cf961353.
- No alterations to DAVE, RTP parsing, STT, TTS, consent, speech targeting, voice command registration, Scaramouche, or Wanderer's text pipeline.

## Release gates
Tests have NOT been executed here. Run full voice and preservation suites and real Discord voice tests before approval. This detects a plausible silent-deafness bug; it does not establish the cause of the currently reported live failures. No deployment or merge is authorized by this PR.
