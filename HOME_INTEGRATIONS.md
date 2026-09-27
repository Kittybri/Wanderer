# Home presence bridge

This is an opt-in, disabled-by-default addition. Existing Discord chat, commands,
voice, Fish Audio, emotional TTS, and previous feature batches remain intact.
The canonical **hub and home relay live in Scaramouche's repository**. Wanderer
includes only the same small protocol/client/Discord adapter, not another server.

## Architecture and trust boundary

```text
Scaramouche ─┐                     outbound WSS from home host
             ├─ signed HTTPS RPC ─ Hub ◀──────────────── Home relay
Wanderer ────┘                      ▲                    ├─ Hue v2
                                   │                    ├─ python-kasa
Phone/OwnTracks ── HTTPS Basic ──────┘                    ├─ PyChromecast
                                                        └─ local CUPS/IPP
```

Run one hub and one relay per configured agent ID; SQLite and sockets are
single-process, not a multi-worker service. No home inbound port forwarding, main
laptop, GPU, LLM, Discord token, Groq key, or Fish key is needed on the relay.
Only explicitly registered devices are usable. Discovery never grants permission.
Bot clients authenticate as `scaramouche` or `wanderer`; the hub trusts each bot
process to supply the genuine Discord user/guild IDs. Protect those processes.

Both hub and relay independently enforce structured enums, actor/device/action
allowlists, time windows, modes, bounds, cooldowns and quotas. There is no shell,
eval, raw device-command, arbitrary URL, file-path or arbitrary-document operation.
HMAC-SHA256 signatures are domain separated, nonce checked, expire after 30 seconds,
and use constant-time comparison. Request IDs are durable audit/replay receipts.
Clocks must be synchronized. HTTP RPC is limited to 10 authenticated requests/second
per identity, with no automatic action retries. A relay accepts one action at a time.
Unknown, malformed, expired, offline, and unauthorized requests fail closed.

## Install and configure the cloud hub

Use a dedicated unprivileged service account, private config directory (0700),
config files (0600), and persistent data directory. Keep credentials and databases
outside the checkout and out of backups/logs unless those backups are protected.
Examples are templates, not deployable credentials. Generate **different random
credentials** for each bot, relay and OwnTracks account, e.g. with
`openssl rand -hex 32`; never paste them in Discord or commit them.

From the Scaramouche checkout on the cloud host, with Python 3.11+:

```sh
python3.11 -m venv .venv-home
.venv-home/bin/python -m pip install -r requirements-home.txt
.venv-home/bin/python -m home.hub --config /etc/character-home/hub.json --validate
.venv-home/bin/python -m home.hub --config /etc/character-home/hub.json
```

Create the private hub file using `home/config.hub.example.json`. Replace all
IDs, URLs, credentials, zones and resource IDs. Leave `enabled:false` and device
`enabled:false` until policies are reviewed. `guilds:[0]` means DM commands only;
add a specific guild ID only when intended. Users are numeric Discord IDs.

Expose a dedicated HTTPS origin such as `https://home.example.com` (root path).
Terminate TLS in the hub with `tls_cert`/`tls_key`, or use a reverse proxy on the
**same host**. With `trust_loopback_proxy:true`, the hub binds only 127.0.0.1;
the proxy must strip incoming forwarded headers and set `X-Forwarded-Proto:https`.
Forward `/rpc/`, `/agent/` with WebSocket upgrade, `/owntracks/`, and `/audio/`.
Never expose port 8765 directly with proxy trust enabled. Do not log request bodies,
Authorization/X-Home-Auth headers, query data or audio capability paths. Disable
proxy access logging for these routes. Valid TLS certificates are required; do not
disable certificate checks. `--validate` checks local structure, not live TLS/DNS.

Run both services with a process supervisor such as systemd, `Restart=on-failure`,
an unprivileged user, private data directory, and `UMask=0077`. Do not put credentials
on the command line. Stop/start services through the supervisor when rotating keys.

## Home relay setup

Use an always-on Linux Pi/mini PC on the devices' LAN. Current pinned Kasa and Cast
libraries require Python 3.11+. No GPU is needed. From the same Scaramouche version:

```sh
python3.11 -m venv .venv-home
.venv-home/bin/python -m pip install -r requirements-home-agent.txt
.venv-home/bin/python -m home_agent.agent --config /etc/character-home/agent.json --validate
.venv-home/bin/python -m home_agent.agent --config /etc/character-home/agent.json
```

Start with `home/config.agent.example.json`. Use the matching per-agent credential,
`wss://` hub URL and `https://` media origin. **Copy each approved device's policy
object from the hub's `devices` into the relay's `devices`**, then add the local
adapter fields below. The local policy can be stricter, never broader in effect.
Keep `enabled:false` until ready; enabling at only one end is insufficient.
On older macOS, a clean dependency install may need OpenSSL development libraries
and native build tools when no compatible cryptography wheel exists. The validation
Mac hit that limitation; relay imports/tests then succeeded in a Python 3.12
environment using the bundled OpenSSL-backed cryptography package. Do not disable
TLS or downgrade security dependencies to bypass build errors. Linux/Pi deployment
still needs its own installation check.

The relay advertises configured IDs/types and sends health every 10 seconds.
Reconnect delays increase exponentially to 60 seconds plus up to one second jitter.
Commands expire in 30 seconds, execute for at most 24 seconds, are never queued
across reconnects, and are never retried automatically. Persistent disable states
are reconciled on reconnect. Graceful shutdown cancels active work and closes Cast
connections. An already accepted hardware action cannot always be undone.

### Hue

For a `type:"hue"` policy add:

```json
{"host":"192.168.1.10", "resource_id":"YOUR-LIGHT-UUID",
 "application_key":"YOUR-HUE-APPLICATION-KEY", "tls_fingerprint":"64_HEX_SHA256_CERTIFICATE_FINGERPRINT"}
```

Use an explicit private IP/DHCP reservation. Pair the bridge and obtain application
key/resource IDs using Hue's authorized setup flow. Trust a certificate fingerprint
verified locally, or supply `ca_file` for a CA that validates the bridge/IP. Never
use `ssl=False`. Rotate the pin deliberately if its certificate changes.

Supported actions are power, brightness, configured XY colors, color temperature
(153–500 mirek), and recall of configured scene UUIDs. Put identical named
`colors`/`scenes` on hub and relay. Exclude unsupported actions for your actual light.
Brightness defaults to 10–70%; policy may narrow/change bounds within 1–100%.
Changes have a minimum 60-second cooldown and maximum six/hour, even if a config
requests less/more. No strobe, flashing, or dynamic-scene command exists. Approve
only static scenes. See [official Hue developer information](https://developers.meethue.com/).

### Kasa/Tapo

For `type:"kasa"` add `host` (private IP), and `username`/`password` on the relay only
if required by the device. Modern models often need TP-Link account authentication;
compatibility varies by model/firmware. On a power strip set the exact `child_id`;
an omitted/wrong child ID is rejected rather than switching every outlet.

The default category is `NEVER_AUTOMATE`. Only explicitly reviewed `DECORATIVE`,
`LIGHTING` or `LOW_RISK` devices may use autonomous triggers, and then only in
`AUTONOMOUS_SAFE` mode. Never register heaters, medical equipment, fridges/freezers,
cooking equipment, routers, PC power, or life-safety equipment for character control.
`NEVER_AUTOMATE` can still allow deliberate manual actions if configured; use
`DISABLED`/no registration to prohibit all control. See
[python-kasa connection guidance](https://python-kasa.readthedocs.io/en/stable/guides/connect.html).

### Chromecast

For `type:"cast"` add `host` (private IP), exact `uuid`, and optionally
`max_play_seconds` (1–12, default 12). Selection must match both IP and UUID;
discovery of other devices cannot authorize them. The configured home host must be
on the appropriate LAN/subnet and able to reach the Cast device.

Actions: `play`, `pause`, `stop`, bounded `volume`, `test`. Default volume range is
0.10–0.50 and 0.50 is a hard upper bound. Current emotion-aware Fish TTS is called
unchanged; the bridge uploads its output, not credentials or internal prompts.
Audio is limited to 5 MB, MIME+signature-checked MP3/WAV/OGG, in-memory, 120-second
unguessable HTTPS URLs, 20 files and 20 fetches per file. URLs are scoped to a
user/bot before issuance, removed after playback/timeout, and swept when idle.
The Cast device needs public HTTPS reachability to the hub's `/audio/` origin.
These bearer URLs must be treated as private; anyone holding one can fetch it until
expiry. There is no permanent public bucket or filesystem-serving endpoint.

Optional administrator-approved static sounds: add asset names to hub `assets`,
and relay `asset_urls`, e.g. `{"chime":{"url":"https://YOUR-HOST/chime.mp3","mime":"audio/mpeg"}}`.
Commands accept only the asset name, never a supplied URL. Static URLs are not
short-lived and therefore must contain only deliberately public, harmless audio.
Playback is bounded and stopped on completion, activation failure or cancellation.
Long responses may be truncated; this is not continuous room audio or full-duplex VC.
See [PyChromecast documentation](https://github.com/home-assistant-libs/pychromecast/blob/master/README.rst).

### Printer

Configure a local CUPS queue using your OS's normal printer setup, then add
`queue:"office"` to the relay printer policy. Only loopback CUPS port 631 is used;
no shell, vendor command, direct arbitrary printer URL, or email-to-printer gateway.
Use a dedicated queue with no banner sheets and one-sided/one-copy defaults as
appropriate. The service account must have permission to submit to that queue.

Only fixed short text templates `posture`, `birthday`, `break`, `reminder` can print.
Private conversations, credentials, coordinates, face embeddings, uploaded documents,
PDFs, images and arbitrary text are not accepted. IPP requests specify one copy,
page 1 only, no job sheets and attribute fidelity. Policy requires `text/plain`,
at least one allowed page, cooldown, and at most three jobs/device/UTC day.
Attempts count toward quotas even when failed, to prevent retry storms.
Status distinguishes `submitted` from confirmed `completed`; some printers complete
later and require checking CUPS. Cancellation cannot recall paper already printed
or guarantee cancellation of a job accepted by CUPS.
See [IPP encoding](https://www.rfc-editor.org/rfc/rfc8010.html) and
[CUPS options](https://openprinting.github.io/cups/doc/options.html).

## Bot configuration and commands

Merge `home/config.bot.example.json`'s **home section** into each bot's existing
private `BOT_INTEGRATIONS_CONFIG` JSON file (or existing `BOT_INTEGRATIONS_JSON`).
Do not replace its other integration sections. Each bot uses its own hub client
credential; never give a bot the relay/Hue/TP-Link credentials. No home configuration
means normal Discord behavior without home network calls. New preferences default off.

```text
!home
!home do bedroom_lamp brightness {"value":35}
!home do decorative_sign power {"on":false}
!home do office_printer print_note {"template":"posture"}
!home confirm <request-id>
!home speak bedroom_clock Take a break.
!home actions on
!home alarms on
!home output bedroom_clock
!home output off
```

`output` is DM-only and opts into occasional DM-response playback, not continuous
recording. It also needs `AUTONOMOUS_SAFE` and `allow_roommate:true` on that device
at both ends. Voice preferences and quiet hours remain authoritative. `alarms on`
requires an administrator-configured local-time alarm plus `AUTONOMOUS_SAFE` and
`allow_alarm:true`. Only explicit `allow_alarm_quiet:true` allows an alarm outside
device hours. Alarm time uses the user's existing timezone preference. Alarms run
at most once/device/bot/local day; this is not a reliable safety/wake-up alarm clock.

`!home actions on` permits deterministic suggestions, not physical permission.
Rules support only `irritated` (mood <= -5), `calm_night` (mood >= 3 after 21:00),
and Scaramouche's January 3 birthday. Review the example rules before enabling.
The normal proactive opt-in, quiet hours, shared per-device/user cooldown, and both
device policies gate these actions. No LLM-generated IPs, URLs or raw commands are
used. Scheduler hooks reuse the existing reminder task; no duplicate bot heartbeat.

Modes:

| Mode | Meaning |
| --- | --- |
| DISABLED | No action, including test |
| MANUAL | Explicit allowlisted user requests only |
| CONFIRM | Request produces a user/bot-bound confirmation, valid for <=30 seconds |
| AUTONOMOUS_SAFE | Only preconfigured, opted-in, bounded triggers plus manual requests |

Additional `confirmation_required:true` can require confirmation in another mode.
Automatic rules never confirm themselves; they will not execute a proposal silently.
Failed/expired confirmation requires a fresh request. The current scheduler does
not deliver autonomous confirmation proposals as a separate notification; use manual
`!home do` for confirmed actions. `hours:[0,0]` means all day; defaults are 08–22 UTC.

Owner-only **DM** diagnostics: `!home status`, `devices`, `agent`, `permissions`,
`audit`, `test <device>`. Both the bot's existing OWNER_ID and the hub's `admins`
must authorize the owner. Diagnostics expose logical IDs, modes, allowed actions,
relay heartbeat, cooldown and last result—not network addresses or secrets.
An online relay is not proof a physical device is available; `test` is a bounded
read-only probe and still uses policy/cooldown. Availability remains marked unverified
until you perform live tests; audit results show the actual last probe/action result.

## OwnTracks and privacy

Set a per-user account under hub `owntracks`, `enabled:true`, strong unique HTTP
Basic username/password, numeric user ID, allowed bot names, and named zones.
Configure OwnTracks **HTTP mode**, endpoint
`https://home.example.com/owntracks/my_phone`, valid TLS, and those Basic credentials.
The bot never polls your phone. OwnTracks sends updates; the bot consumes already
received zone events. See [OwnTracks HTTP setup](https://owntracks.org/booklet/tech/http/)
and [payload format](https://owntracks.org/booklet/tech/json/).

Zones have local names such as HOME/WORK, latitude, longitude and radius in meters
(clamped to 10–5000). Use at most 20 non-overlapping zones. For transition messages,
OwnTracks region `desc` must equal a configured name; only enter/leave are accepted.
Location fixes are classified then discarded. Unknown transitions, stale timestamps,
inaccurate fixes and events for users without opt-in are rejected. Debounce is at
least 60 seconds (default 300); duplicate/old transitions do not create chatter.
An unrelated zone's leave event cannot erase the current zone.

In a DM to each bot:

```text
!home location on
!home location off
!home location delete
```

The server opt-in is shared per person, while reaction preferences are per bot;
opting out/deleting through either bot stops server ingestion for that person.
Re-enabling on one bot also re-enables server ingestion; turn both bot preferences
off if you want neither to react. Add the user to each bot's `home.users` for polling.
Reactions require existing proactive/DM permissions, DM timing, non-quiet hours and
a shared one-hour cooldown. They are private, character-distinct, and explicitly
describe a received update, never claim constant observation. Events are consumed
without a delayed backlog if reactions are disallowed. Exact coordinates, addresses
and location routines never enter LLM prompts, ordinary chat memory or action audits.

Stored live location data is only zone, source timestamp, event kind, user and bot.
Events/current-zone state expire after one day; bot delivery uses only 15-minute-old
or newer events. `off`/`delete` delete that user's live location records and disable
ingestion. If hub is offline, the bot stops local reactions immediately and tells
you to retry server deletion; it does not claim a remote deletion succeeded.
Previously sent Discord DMs and external backups are not erased by this command.
Configured zone coordinates remain in private config, not event history.

## Persistence, audit and event routing

Existing per-bot `user_preferences` gains four additive fields:
`home_presence_enabled`, `home_actions_enabled`, `home_alarms_enabled`,
`voice_output_target`. Existing users and preferences are preserved.
Existing shared cooldown storage coordinates the bots when configured to share it.

Each hub/relay SQLite file holds replay/rate receipts, runtime disable/proposal
state, minimal action audit, and ephemeral events (location only on the hub).
Audit fields are timestamp, request ID, bot, user, logical device, action, trigger,
result. No payload/audio/credential/face-memory/chat-body columns. Audits expire in
30 days; proposals/nonces expire promptly. Cleanup runs during idle service periods.
Short-lived raw audio is RAM-only, not SQLite. A compromised host/database is still
a privacy risk: use OS disk encryption, restricted permissions and protected backups.

`HomeBot` is the central bot event/action boundary. Named events drive fixed private
reactions; action results remain structured/audited. Scaramouche additionally receives
only a generic successful-action event in its existing self-model, without device
details or location history. No long-term location-routine profile is built.

## Emergency disable and failures

In an owner DM: `!home disable` (global) or `!home disable bedroom_lamp` (one device).
Use corresponding `enable` after review. Runtime disable persists through restart;
enable cannot override disabled config, modes, actor allowlists or environment kill.
Set `HOME_AUTOMATION_ENABLED=false` in hub and relay service environments and restart
to enforce a deployment-level kill. OwnTracks ingestion is separate: disable accounts
or opt out if desired. Discord remains usable with home services off.

Disable cancels in-flight relay tasks and stops best-effort Cast playback. It cannot
undo a light/plug command already sent or paper already accepted. Per-device disable
may conservatively cancel another currently active action on the same relay.
If hub connectivity is lost, the relay cancels work; no stale action is replayed
after reconnection. Action failure is generic and private diagnostics retain only
safe result codes. No repeated channel error spam or automatic owner-alert loop.

Troubleshooting order: validate both config files; check IDs/keys/TLS/time sync;
check relay heartbeat; confirm both `enabled` flags and runtime disables; verify
user/bot/guild/time/mode allowlists; inspect cooldown/quota; run `!home test`;
then inspect the local vendor/CUPS setup. Do not paste full configs or logs with
credentials in chat. Never bypass TLS or widen permission scopes to mask an error.

## Validation and extending providers

Automated tests cover signed real loopback HTTP/WebSocket roundtrips, replay,
confirmation, reconnect/duplicate connections, kill switches, timeout/offline,
OwnTracks privacy, temporary audio, adapter requests/cleanup, quotas, preferences,
commands and scheduler gates. Vendor hardware/TTS calls are mocked. To rerun:

```sh
python -m pytest tests/test_home_bridge.py tests/test_home_network.py tests/test_home_providers.py tests/test_home_bot.py -q
python -m pytest -q
```

Production uses TLS only. `mock:true` is strictly for local tests: transport may
use loopback HTTP/WS and every relay provider becomes a mock. Do not deploy that
flag to production. `--validate` does not contact devices. No physical devices,
real OwnTracks phone or production cloud deployment were verified in this batch.
In Wanderer's checkout run `python -m pytest -q` (it also has root-level test files);
run the full hub/relay tests from Scaramouche, where those services live.

To add a provider: define a strict protocol action/parameter schema and policy type;
implement asynchronous `execute(device, action, parameters, media)`/`close()`;
add explicit config validation, deadlines, cleanup and mock tests; register it in
the relay; synchronize the small protocol/client modules in both bot repositories.
Never add a generic executor, bypass local policy or give the LLM device credentials.

Remaining bounds: one hub worker, one action/relay at a time; no high-availability
queue, no device-state subscriptions, no continuous audio, no arbitrary print/image
uploads, no automatic location-profile learning. Printing supports only fixed notes;
Cast is short-form playback. Real model/firmware compatibility, printer page handling,
TLS routing and audible playback require owner setup and live verification.
