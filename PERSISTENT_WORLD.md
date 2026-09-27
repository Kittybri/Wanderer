# Persistent-world batch

This stacks on `feature/character-polish-batch`. It does not deploy itself or merge earlier PRs.

## Commands

- Scaramouche: `!grudges`, `!atone [voluntary apology]`.
- Wanderer: `!grudges`, `!clemency`. Petitions are processed by Scaramouche, not direct edits by Wanderer.
- Both: `!worldprefs`, `!worldprefs grudges on|off`.
- Wanderer: `!worldprefs lullaby on|off`, `!worldprefs lullaby_hour 20–23`. Uses the existing user timezone; this explicit ambient opt-in allows the configured late-night window, including quiet hours.
- Both, **DM only**: `!enrollface` (aliases `!rememberface`, `!reenrollface`) with one image; `!recognizeface` with one image; `!faceinfo`; `!deleteface`.
- Each enrollment adds a sample, up to eight. Changed/legacy models start a new compatible template set. To replace all current samples, delete then enroll.
- Face commands never accept another user's ID or mention as an enrollment target. Users affirm that their attachment is their own face. This is consent-based convenience, not proof of ownership or authentication.
- Existing topic forgetting also removes matching grudge/birthday records; confirmed full memory reset clears the user's new world records and active face templates.
- Recognition is explicit; ordinary images and videos do not run a face matcher.

## Setup

Back up the existing per-bot and shared SQLite databases. Install requirements for the target Python runtime and restart each service once. Tested locally on Python 3.9.6/macOS x86_64; Linux/ARM deployments still need their normal package-install and startup smoke test. No dlib compiler dependency.

Both processes must point at the **same local shared SQLite file** on durable storage. The existing Memory shared_db_path is reused; do not put SQLite on an unreliable network filesystem. Separate Railway services need an actual supported shared-state service or colocated durable storage; merely giving two separate volumes the same filename does not share state.

Add the following section to the existing private `BOT_INTEGRATIONS_CONFIG` JSON file (or its existing JSON environment value). These are examples: IDs, repo branch and paths must be filled by the administrator. Defaults disable dreams, source posts, birthdays, decorations and lullabies.

```json
{
  "persistent_world": {
    "grudge_decay_days": [7, 30, 180],
    "grudge_ledger_channels": {"GUILD_ID": "SOURCE_CHANNEL_ID"},
    "playful_reports": false,
    "dreams": {"enabled": false, "hour_utc": 3, "cooldown_days": 7, "significance": 65},
    "birthday": {
      "guilds": {
        "GUILD_ID": {
          "enabled": false,
          "channel_id": 0,
          "timezone": "America/Los_Angeles",
          "petty_neglect": false,
          "decorations_enabled": false,
          "channels": {},
          "roles": {}
        }
      }
    },
    "code_awareness": {
      "enabled": false,
      "repository": "Kittybri/scaramouche",
      "branch": "main",
      "channel_id": 0,
      "cooldown_seconds": 21600,
      "reflection": false
    },
    "lullaby": {
      "enabled": false,
      "channel_ids": [],
      "ambient_path": "/absolute/path/to/your-authorized-ambient.wav",
      "duration_seconds": 180,
      "cooldown_seconds": 604800,
      "min_affection": 75,
      "final_line": false
    }
  }
}
```

Use `Kittybri/Wanderer` for Wanderer's source review. Retain the existing GitHub integration token and allowed_repositories settings; no new GitHub client/account is required. The developer channel must deny View Channel to @everyone. Review posts may still be visible to any roles allowed there; audit those permissions.

The ledger intentionally only posts when its configured ID equals the **originating conversation's channel**. A separate central ledger receives nothing, avoiding accidental private-channel/DM disclosure. Internal grudges work without any ledger.

For decoration maps, keys are explicit channel/cosmetic-role IDs and values are temporary names. Roles must be unmanaged and below the bot's role. Only name edits occur, never permissions, assignments, hierarchy changes or deletions. Originals and restoration deadlines are saved **before** edits. Restore after restart runs even if birthday configuration is subsequently disabled. If the bot is offline, removed, or loses permissions, restoration necessarily waits until access returns; preserve the DB and restore permissions. Administrator renames are not overwritten.

## Face model installation

Use OpenCV's official [YuNet model directory](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet) and [SFace model directory](https://github.com/opencv/opencv_zoo/tree/main/models/face_recognition_sface). Download actual ONNX weights, not Git LFS pointer text, review their model licenses, then configure:

```text
FACE_YUNET_MODEL=/absolute/path/face_detection_yunet_2023mar.onnx
FACE_SFACE_MODEL=/absolute/path/face_recognition_sface_2021dec.onnx
FACE_COSINE_THRESHOLD=0.55
```

YuNet detection plus SFace 128-dimensional embeddings uses OpenCV's CPU runtime, already present in Wanderer's dependency family. [Official API/model documentation](https://docs.opencv.org/4.x/d0/dd4/tutorial_dnn_face.html) describes the local detector/recognizer. The default 0.55 is deliberately conservative, not a measured accuracy guarantee for your users. Calibrate using consenting genuine and nonmatching photos before changing it. Similarity is **not a probability**. Multiple faces, small/blurry inputs, incompatible/corrupt templates and close candidates are rejected or reported unknown/ambiguous. No liveness/access-control claim is made.

Weights load lazily only for explicit face processing; inference runs off the event loop behind a model lock. Templates include the combined model SHA-256 fingerprint. No model downloads at startup and no external face API calls. Missing weights/dependencies fail closed without disabling ordinary chat.

Only embeddings, owner ID and version metadata are stored in the existing face_profiles shape. The enrollment generation table prevents an in-flight enrollment from resurrecting a deleted template. Legacy owner_face belongs only to its recorded owner; no automatic conversion. Protect DB/backups with filesystem permissions and encrypted storage: embeddings remain sensitive biometric data. Deletion removes active rows, not forensic SQLite remnants, historical backups or Discord's retained attachment. This implementation does not pretend to delete those services' copies.

## Behavior and persistence

- Grudges are scoped to user + original channel. Repeated severe direct insults require pre-existing unresolved conflict and low mood, or an enabled allowlisted playful report. Generic factual reasons only; never arbitrary private message quotations. Birthday neglect is PETTY only, opt-in at guild level, for actual participants with proactive/grudge preferences enabled. No offline-user punishment.
- Severity mildly changes the existing response mood/conflict inputs and records bounded self-model irritation. It never invokes moderation or blocks utility commands. Atone is deterministic and cooldown-limited; apologies reduce one tier. Petty clemency can be accepted with Wanderer provenance; more severe requests are declined, auditable.
- Dreams: one shared significant seed per configured period, one independent bounded call per bot. Seeds use aggregate bot-relationship state, not private histories. Correlated records survive restart. At most +1 respect/-1 tension per perspective, plus Scara curiosity/reflection. Failures consume the attempt and do not loop. Optional callbacks only on dream/sleep topics, once per day per bot.
- Birthday tribute grading uses the normal response context; no second reply or extra model call. No payments or real-world gifts.
- Source awareness reviews the current branch head, not every intermediate commit if several land between polls. It restricts input to bot.py, self_model.py, internal_state.py, relationship_engine.py and personality.py. Structural patch lines only: literals, numeric values, assignment expressions, comments, secret-ish lines and free-form text are omitted. One SHA receipt, private developer channel only, no edits to source. This deliberately limits technical precision; never point the feature at a repository used to store secrets.
- Lullabies require explicit user opt-in, high affection, recent activity, online/idle status, a configured VC containing only that human, permissions, no existing voice client/duo session, and a weekly default cooldown. It self-deafens, plays authorized local ambient audio with a 300-second hard cap, stops if the audience changes, optionally calls the current TTS interface, and disconnects in finally. It never records or listens.
- Jobs run within Scara's existing heartbeat / Wanderer's existing hourly birthday scheduler. Reconnect does not create new loops. Normal messages add no new model calls.
- New shared tables: character_grudges, grudge_events, grudge_clemency, persistent_world_events, face_consent_generation; face_profiles reused/created when required. Existing user_preferences gains grudge_enabled, lullaby_enabled, lullaby_start_hour. Idempotent migrations, WAL, busy timeouts and transactional claims.
- External sends are at-most-once attempts: an ambiguous send/crash may omit an announcement/review rather than spam on restart. Decoration restore receipts are retained until successfully handled.

## Validation

Run from each repository with the installed interpreter:

```sh
python -m pytest -q
python -m compileall -q bot.py memory.py persistent_world.py grudge_system.py world_store.py dream_coordinator.py birthday_event.py face_memory.py face_controls.py code_awareness.py lullaby.py
git diff --check
```

Tests use temporary databases and mock Discord/Groq. They do not post to servers, enroll actual people or start a live VC. A real Discord voice/permission smoke test and representative face accuracy evaluation remain administrator deployment checks.

Batch validation: 33 added tests per repository; full suites 102 passed (Scaramouche) and 49 passed (Wanderer). Both bot imports and command registrations passed. Official YuNet/SFace weights loaded under OpenCV 4.11.0 and a generated blank image returned no_face. Positive identity accuracy is not measured by this smoke test. Scaramouche's suite reports the pre-existing urllib3/LibreSSL warning from the macOS Python build; deploy with a supported Python/OpenSSL runtime.
