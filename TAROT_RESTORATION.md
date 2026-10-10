# Tarot restoration and missing-command audit — 2026-10-07

## Cause and scope

The current Git/release candidates did not include tarot_system.py, tarot command
handlers, or help entries. The pre-Git Oracle deployment retained the module, deck
and history database. No tarot file/command addition or removal was found in the
available Git history. Therefore this is a deployment-source parity gap predating
the recent Google changes, not evidence that Google registration deleted the tarot
implementation. The exact earlier migration that omitted it is not established.

Restored from /opt/scara-wanderer-bots/tarot_system.py (source SHA-256
622915269532186bd6e97b04ac99652a110aa478517119c29416b77eab1e9b33), which is newer than
the local snapshot and includes the three-part Celtic Cross output fix. Existing
78-card artwork is reused without changes or regeneration. No database content is
included in Git.

## Restored surface

| Bot | Prefix commands (historical names preserved) | Slash commands |
| --- | --- | --- |
| Scaramouche | !scaratarot, !scaradaily, !scarahistory, !scarasettings | /tarot, /dailycard, /tarothistory, /tarotsettings |
| Wanderer | !tarot, !dailycard, !tarothistory, !tarotsettings | /tarot, /dailycard, /tarothistory, /tarotsettings |

Historical aliases remain registered. Help prominently lists tarot alongside
Google. Tarot keeps the three spread choices, sequential reveal, original card
art, lore/standard meanings, reversals, private/public preference, detail setting,
daily draws, clarification, card explanation, follow-ups and saved history.

Focused hardening for the recovered code: no bulk overwrite of Scaramouche's
remote slash tree; private slash entry/error delivery; no accidental public fallback
if DMs are closed; bounded provider requests and deterministic reading fallback;
credential/serious-context guards including modal follow-ups; owner-bound UI;
serialized buttons; SQLite connections closed; additive session table prevents
stale cross-process UI from recreating deleted tarot records. Both reset sagas and
topic-forget now include tarot. Historical readings/preferences are retained on
deployment; only a requested reset/forget deletes matching data.

## Other differences found — NOT all repaired by this batch

Baseline: earlier Oracle source snapshots under oracle_ops/remote_snapshots,
including Cog COMMANDS registries and slash groups. Current side: actual imported
discord.py registry, including dynamically installed features. Compare names AND
aliases. This is not a claim that every historical command is safe to restore or
that every current command has been live exercised.

Scaramouche's additional absent functionality includes:
- RPG commands: rpg1, rpgstats1, rpg1reset, gamerank1 and their aliases.
- Birthday registration: birthday / dob / birthdate / setbirthday.
- Document editing: fixdoc / docfix / gdocfix / editdoc.
- Memory/relationship/rank recovery: rebuildmemory, rebuildrank, rebuildstats,
  rebuildrelationship and aliases.
- achievements, world, worldadd, cases, gallery.
- bothealth, backupmemory, provider status and older owner/admin controls:
  dmlist, logs, owneronly, servers, leaveserver, channel/block management and aliases.
- Local slash handlers: /scaramouche, /dashboard, /prefs, /duo, /world. Existing
  remote registrations may still appear despite their local handlers being absent.
  They are deliberately not deleted or claimed fixed here.

Wanderer's remaining non-rename gap: provider status / aistatus / wanderstatus.

Intentional/non-equivalent changes that must not be blindly reverted:
- nsfw was explicitly renamed to unrestricted at the user's request.
- Legacy face export/import aliases are absent in the current user-scoped,
  consent-based face subsystem; do not reintroduce older owner/global biometric
  access merely to make a name comparison pass.
- Scaramouche has selfbackup/taskhealth, but these are not assumed equivalent to
  every old backupmemory/bothealth function.

Exact machine-readable historical names: tests/legacy_command_surface.json.
Current registered names: tests/current_command_surface.json. The existing actual
bot-import regression now checks the entire current manifest to catch future
accidental removals. Run tools/audit_command_surface.py for the outstanding delta.

A follow-up compatibility restoration must adapt the remaining Scaramouche
features to current privacy, permissions, persistence and interaction arbitration,
with dependency checks and tests. Copying the entire older bot.py/Cogs over the
current release would discard later hardening and is NOT an acceptable repair.

## Deployment contract

Use an immutable code release per bot; retain the prior WorkingDirectory for
rollback. Preserve Google environment/client/key/store and callback service.
Set TAROT_DECK_DIR to the existing 78-card bot_deck directory and TAROT_DB_PATH
to the original /opt/scara-wanderer-data/tarot.sqlite3 for BOTH bots, after an
online SQLite backup and integrity check. Never put history or tokens in archives.
Only restart the two bot units; do not restart/reconfigure the connection service.
No Google API, voice implementation, domain/DNS, or other feature changes.

Tests use synthetic data only. Live rendering can exercise all 78 existing art
files and all three spreads without contacting Groq or posting to Discord.
Successful Discord registration is distinct from a human clicking the UI.

## Automated candidate validation

Final complete suites: Scaramouche 794 passed, 1 skipped, 1 warning (122.77s);
Wanderer 338 passed, 1 skipped, 1 warning (67.76s). The skip remains the optional
local Opus roundtrip; the warning is the local urllib3/LibreSSL environment.
Each includes 20 new tarot regression cases plus whole-command-surface assertions.
Compile checks, diff whitespace checks and nine-file staged secret-pattern scans
passed for both repositories (zero credential findings).

The first Scaramouche full run exposed Python 3.9 event-loop dependence in the
recovered store's import-time lock (20 failures / 53 setup errors cascading from
that import). Locks/semaphores now initialize on demand inside async operations;
a regression prohibits import-time async primitive construction. The affected
pipeline/context/tarot rerun passed 90 tests before the successful final full run.
No failing candidate was deployed.

## Live restoration evidence — 2026-10-07 18:35 PDT

Deployed functional candidates:
- Scaramouche: `28da58e125e06a6bc7752b970a3e9cac8a7b9213`
- Wanderer: `5f64866c8335b8ed9fc1170240085e3c0278d86c`

Both bot services are active, with one controlled restart each and NRestarts=0.
New-start inspected error counts are zero. The connection service was not restarted
or reconfigured; its process and working directory remained unchanged.

Both candidates verified all 78 original artwork files and rendered all three
spreads on Oracle. The original tarot SQLite database was backed up before the
additive session migration. Existing preferences, daily draws and history rows
were compared before/after and are unchanged. Tarot quick_check is ok; the bot
and shared-state databases also each report ok.

Discord's live global-command API lists /tarot, /dailycard, /tarothistory and
/tarotsettings for BOTH bots. Existing /google remains registered. Scaramouche's
five older remote slash registrations were preserved, not bulk-deleted; their
missing local handlers remain an outstanding audit finding. No human end-to-end
Discord tarot button/reading test was observed during this deployment.

Google account/grant rows and protected environment-file hashes are unchanged.
The callback health endpoint returned HTTP 200 with successful TLS verification.
No provider write occurred. Host sample: 322/951 MiB available RAM and
179/3062 MiB swap used. No voice, DNS or Google configuration was changed.

Deployment uses only the new 80-tarot.conf systemd drop-in per bot. Rollback is to
move that drop-in aside, reload systemd and restart the bot units; prior releases
remain available. The original tarot database backup is root-protected under
config-backups/tarot-restoration-20261007 in the existing staging root.

Full candidate test totals remain Scaramouche 794 passed / 1 skipped and Wanderer
338 passed / 1 skipped. Subsequent evidence commits are documentation-only.
Draft repair PRs: Scaramouche #24 and Wanderer #11; neither is merged.
