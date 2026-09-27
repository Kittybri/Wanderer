# Local computer companion

An **off-by-default**, visible macOS extension of the existing home relay. No new server,
Discord token, LLM executor, Fish replacement, or remote shell. The executable lives in
Scaramouche's `home_agent`; both character repositories contain the same Discord adapter.
This feature is not installed or running on your Mac merely because the code is present.

## Architecture and data

Mac adapter → existing outbound authenticated WSS agent → existing home hub → private
owner commands / sparse character check-ins. Both hub and agent independently check
owner ID, private-DM scope, capabilities, action enum, enabled state, hours, rate limits,
confirmation, replay protection and a maximum 30-second command lifetime. Reconnects
never queue actions. At most one computer device per agent, one per owner/bot mapping.

The adapter polls every **10 seconds**, not every input event. It reads the foreground
bundle ID and seconds since input, never keys or coordinates. Only locally configured
friendly labels/categories leave the Mac; unknown apps become `Unknown app`. Durations
are 5-minute buckets, reset at app/idle transitions, capped at 24 hours. Events are
deduplicated: app/state change, 30-minute duration milestone, or 60-second heartbeat.
States: ACTIVE, IDLE (default 5m), AWAY (15m), LOCKED, UNKNOWN. These are observations,
not proof of attention or productivity. Polling can miss switches shorter than 10 seconds.

The single normalized context combines independently fresh Discord status and local
state without pretending they must agree. Fields expire after 120 seconds; disconnect
clears relay context immediately. No browser history, URLs, clipboard, microphone,
webcam, keystrokes, full document content, or long-term activity timeline is collected.
Window titles are read **locally only** for blocking, never transmitted or persisted.

## Install and configure (Mac, Python 3.11/3.12)

From the Scaramouche checkout, create a separate environment, then:

```sh
python3.12 -m venv .venv-companion
.venv-companion/bin/python -m pip install -r requirements-companion.txt
```

Copy `home/config.companion.example.json` to a private file outside Git. Change the
placeholder owner ID, endpoint and secret; the placeholder secret intentionally fails
validation. Generate a unique long random agent secret and provision the same value in
the hub's `agents.desktop`. Never paste credentials into Discord. Restrict config and
database file permissions to your OS user (for example, `chmod 600` on the exact files).

Merge the example's `devices.desktop` into the **existing hub** device registry. Preserve
existing lights/speakers/printers and their agents/secrets. The Mac's local device policy
may be stricter but should use the same owner/device/agent IDs. Set `enabled: true` at
the agent top level, device, and `companion` only after reviewing permissions. Enable
the matching hub device. Keep `mode: MANUAL`, or choose `CONFIRM`; autonomous computer
actions are rejected. Both bot clients must already be configured in the home bridge.

Bot integration configuration can optionally contain:

```json
{"companion": {
  "session_threshold_seconds": 7200,
  "reaction_cooldown_seconds": 21600,
  "development_notifications": false,
  "deadline_context": false
}}
```

Companion reactions require existing `proactive`, `allow_dms`, DM timing and quiet-hours
preferences. Serious/utility messages suppress them for an hour. Shared cooldown is at
least four hours across both bots (default six); no relationship-score penalties.
Scaramouche's existing self-model may receive a generic, user-deletable observation,
not an app name, screenshot, or screen transcript. Wanderer uses the same bounded
reaction gate without adding a second self-model. Screen summaries are NOT inserted
into ordinary LLM conversations or persisted message-memory automatically.

`deadline_context` reuses the owner's existing Google Tasks/Calendar credentials,
read-only. It keeps only a due-soon boolean, never task/event titles or descriptions.
It adds a neutral schedule reminder, not an accusation based on app names. Task dates
are coarse Google dates, so this is not an exact deadline alert.

## Start, stop, verify

```sh
.venv-companion/bin/python -m home_agent.agent --config /absolute/private/companion.json --validate
.venv-companion/bin/python -m home_agent.agent --config /absolute/private/companion.json --status
COMPANION_AGENT_ENABLED=true .venv-companion/bin/python -m home_agent.agent --config /absolute/private/companion.json
```

These first two commands do **not** sense the desktop. The running relay prints a visible
startup notice. Keep its terminal visible. Ctrl-C cleanly stops the process and audio.
No launch-at-login service is installed. Optional manual service management should use
a plainly named user LaunchAgent with `RunAtLoad=false` and no `KeepAlive`; never a
root daemon. A GUI login session is needed. Starting manually is the supported default.

Local verification, explicitly consenting to **one metadata sample**, no screenshot:

```sh
COMPANION_AGENT_ENABLED=true .venv-companion/bin/python -m home_agent.agent --config /absolute/private/companion.json --verify-computer
```

After starting the configured relay, DM either bot `!pc on`, then check `!pc privacy`.
Enabling in Discord cannot override disabled local configuration or the environment
switch. `COMPANION_AGENT_ENABLED=false` is the default. Environment changes require
restarting an existing process; they do not magically alter another process's environment.
For immediate shutdown use Ctrl-C, not merely an `export` in a different terminal.

## Commands (owner, DM only)

| Command | Effect |
|---|---|
| `!pc on` | Shared companion consent; screenshots reset OFF |
| `!pc off`, `!pc forget`, `!pc unlink` | Clear context, revoke consent, disable both characters, retry offline revocation |
| `!pc status`, `!pc privacy`, `!pc context` | Consent, agent health, capabilities and expiring normalized context |
| `!pc screen on/off` | Additional screenshot consent; local config is still required |
| `!pc look` | One explicitly requested foreground-window capture/analysis |
| `!pc notify test` | Fixed, honestly branded notification |
| `!pc audio test` | Current Fish TTS pipeline, short bounded output |
| `!pc stop` | Stop companion audio, including during playback/quiet hours |
| `!pc volume 0.25` | System output volume, locally/hub-clamped to at most 50% |
| `!pc open python_docs` | URL from static local alias map only |
| `!pc launch vscode` | App from static alias/path configuration only |
| `!pc lock` | Always requires a second confirmation, expires in 30 seconds |
| `!pc confirm <id>` | Confirm exactly the pending action |

Each capability needs local `companion.capabilities` plus the device capability and
action allowlist at both ends. Notifications/audio/lock/screens also have explicit
local booleans. `!home do` cannot bypass companion consent or policy. Only preset
notifications exist; no arbitrary text, fake malware warnings or OS/security branding.
All actions are manual/confirmed, never caused by an irritated character.

## Screen privacy and permissions

Screens are OFF by default. Enable `screen_allowed` globally **and for each allowed
app**, enable `screen_context` capability, then explicitly `!pc screen on`. This batch
only captures on `!pc look`, not on a timer or automatically at milestones. Explicit
requests are at least 60 seconds apart. The runtime additionally enforces >=15 minutes
(default 30) for any future non-explicit trigger; no such scheduler is installed.

Only the foreground app's single window is captured. Login/locked/idle states, unknown
apps, browsers/communication categories, password managers, authentication/financial/
medical apps, and sensitive title patterns are blocked. Add `blocked_apps` substrings
and `blocked_window_patterns` case-insensitively. Browsers are deliberately unavailable
because private browsing cannot be reliably verified. Do not mislabel browser apps.
The first 15% of the window is cropped; optional `redact_regions` black out normalized
`[left, top, right, bottom]` rectangles **after** cropping. Output is a maximum
1024×768 JPEG, quality 60, <=350KB. Foreground/lock state is rechecked after capture.

Grant Screen Recording permission only to your chosen Python/Terminal runner in
System Settings → Privacy & Security, and only if you want captures. The code checks
permission; it does not silently grant/request it. Notification settings apply to the
OS runner. Fixed-script lock uses macOS Control-Command-Q and may require Accessibility
and Automation permission for System Events; all other keyboard shortcuts are absent.
It requires `lock_allowed`, a nonempty `lock_safe_apps` bundle-ID list, and rejects
obvious active upload/install/render/call/record/payment windows. This heuristic cannot
prove all workflows safe: leave lock disabled if interruption could be dangerous.

Image filtering is **not guaranteed credential/PII detection**. A password inside an
allowed editor might escape cropping. Keep screens off for sensitive work. Images go
to the already configured xAI vision provider, not a local LLM. Provider-side retention
is subject to that provider's policies; the bot cannot promise external deletion.
The model returns category/confidence/sensitive only. Free text and screenshot-borne
instructions are discarded; low confidence or sensitivity yields `unknown`. No giant
transcript enters character prompts. The user sees only a bounded uncertain summary.

The Mac capture implementation targets the observed macOS 13.7.8 environment. Apple's
[window capture API](https://developer.apple.com/documentation/coregraphics/cgwindowlistcreateimage?language=objc)
is deprecated on newer macOS; failure is closed, not a fallback to full-display capture.
The lock shortcut is [documented by Apple](https://support.apple.com/en-au/102650).

## Audio and local actions

Audio reuses the existing RAM-only home AudioVault and current Fish TTS. Only the
configured HTTPS origin's `/audio/` resources are fetched, no redirects, <=5MB, eight-
second download timeout, <=12 seconds playback, <=50% volume. Local opt-in, quiet hours,
owner scope, 60-second minimum action cooldown, max six actions/hour all apply. Stop
bypasses cooldown/confirmation/hours to remain usable during playback. Cleanup is in
`finally`, disconnect and disable paths. No persistent sound file is created.

URLs must be explicit HTTPS configuration entries; app paths must be static `.app`
paths under `/Applications`, with `launch_allowed`. No close/kill-process, shutdown,
restart, sleep, logout, arbitrary path, command, shell, Python, or AppleScript parameter
can be sent from Discord/LLM. The adapter has three **constant** AppleScripts (notification,
bounded numeric volume and lock shortcut), passed to a fixed executable without a shell.
It can terminate only its own timed-out helper, never an application selected remotely.

## Optional developer completion events

Enable local `development_events`, the capability, and bot `development_notifications`.
Call this yourself after a build/test completes:

```sh
.venv-companion/bin/python -m home_agent.agent --config /absolute/private/companion.json --event test_failed
```

Only `test_passed`, `test_failed`, `build_completed`, `build_failed` are accepted. One
local pending enum with a 120-second lifetime; no file watching, terminal-output parsing,
keystrokes or source ingestion. No commit hook, so GitHub notices are not duplicated.
Notices still obey proactive/quiet/serious/cooldown gates; this is not a guaranteed pager.

## Storage, forgetting and kill switch

- Current apps/activity: RAM only, freshness <=120s, no historical rows.
- Screenshots/audio: process memory only; no temp files or archives. Python cannot
  guarantee forensic RAM zeroization, and OS swap/crash dumps are outside this guarantee.
- Screen classification: RAM only, usable <=120s, cleared on disabled/offline/reset.
- Action audits: actor, device, action, trigger/reason, timestamp and result only.
  `audit_retention_seconds` configurable from 60s to 30 days; default 30d, example 7d.
- Bot DB: additive shared `companion_preferences` (enabled, pending deletion).
- Hub DB: consent flags only, plus existing replay receipts/confirmation/audit rows.

`!forget <topic>` conservatively also revokes companion consent; confirmed memory reset
does too. An offline hub creates a durable deletion retry and reports the wipe incomplete
instead of claiming remote deletion. An offline Mac receives disabled consent before
any commands at reconnection and clears local computer audit/development state. Unlink
revokes runtime linkage; remove the static owner/device mapping in both config files to
prevent later re-enrollment. The disabled consent tombstone is intentionally retained.
Previously sent Discord messages are not erased by this feature; delete them in Discord
if desired. Local snapshots/backups and provider-held data require separate management.

Emergency: **Ctrl-C the local process**, set `COMPANION_AGENT_ENABLED=false`, revoke
Screen Recording/Accessibility permission, and DM `!pc off`. `!home disable` also blocks
the relay. Ordinary Discord bots continue without companion functionality.

Uninstall: stop the process; remove any user-created LaunchAgent (none is installed by
this code); revoke macOS permissions; revoke the hub agent secret/device mapping; remove
your private companion config/database and optional `.venv-companion` through Finder.
Do not remove the bots' shared database. Use `!pc forget` before removing connectivity.

## Troubleshooting and validation

If status is offline, check WSS URL/secret/device IDs, hub enabled state and network.
If online but no data, check all three local enabled flags, environment, `!pc on`, GUI
login session and configured app bundle IDs. `UNKNOWN` is not proof of inactivity.
Screen errors may mean disabled policy, blocked title/app, missing permission, cooldown,
unsupported capture API or vision failure. No raw exception/image content is logged.
Lock/notification/audio success reflects adapter completion, not proof the user perceived it.

GUI sensing/capture, real notifications/audio and locking were **not** executed during
development. Tests use fake OS boundaries and a real loopback HTTP/WebSocket relay.
After configuring your own Mac, use `--verify-computer`, `!pc privacy`, and the manual
commands above to verify each capability individually. Do not enable screens just to
test connectivity. See `LOCAL_COMPANION_VALIDATION.md` for exact test results.
