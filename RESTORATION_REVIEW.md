# Safe restoration review — 2026-10-08

This continuation preserves the existing Tarot/Google/voice implementations. It
does not merge either PR or authorize Docs/Drive, Google Production, or new scopes.
See [the canonical Scaramouche staging record](https://github.com/Kittybri/scaramouche/blob/fix/restore-tarot-commands/STAGING_VALIDATION.md) for measured validation/deployment evidence. Historical
source hashes and every original surface remain in preservation/historical_audit.json.

## Scaramouche restored behavior

- Harbinger Gauntlet: !rpg1 (!quest1, !harbinger1), !rpgstats1 (!queststats1),
  !rpg1reset (!rpgreset1), !gamerank1 (!rpgrank1, !medals1). Both original worlds,
  Earth/Teyvat origins, seven elements, eleven bosses, nine tactical rounds plus
  the round-ten dice encounter, completion medals, provider-generated scenarios.
  Current chaos/party games are separate and untouched.
- Progress and medals are local user+guild scoped. Existing unscoped local RPG
  rows migrate to DM scope, never an inferred guild. Expiring panels bind user,
  guild, channel and opaque persistent revision; duplicate/stale/deleted panels
  cannot award twice or recreate deleted data. Reissuing the command revokes
  previous panels. Loss preserves the result until an explicit reset confirmation;
  the old automatic destructive reset is not reproduced. Stats are self-only;
  leaderboards show only current guild members. No generic history replay.
- !birthday (!dob, !birthdate, !setbirthday): own date, optional year/age,
  private settings query, on/off/clear. Greetings use the registered destination,
  timezone, quiet hours, proactive/DM/mute preferences and annual delivery claim.
  Existing local dates are retained privately until the owner enables a channel.
  Relationship-aware Scaramouche greetings do not publish private memory callbacks.
  The original January-3 character birthday/world schedule is not replaced.
- !world, !worldadd, !cases, !achievements (!gallery): reuse compatible shared
  archive tables; read current durable duo-story cases without a duplicate writer.
  Entries cannot overwrite another user's same-named artifact. Channel content
  stays in its channel; achievement galleries are private and per-user.
  Explicit gifts/props unlock the remembered-artifact achievement.
- /scaramouche, /dashboard (relationship, arc, duostate, scene, achievements),
  /world (state, cases, add), /prefs (voice, utility, duoauto, rpdepth, speaker),
  /duo (state, start) use current supported handlers. Personal responses are
  ephemeral, public duo scenes require an explicit invocation. Individual root
  upserts preserve Google/Tarot and unrelated registrations; no partial bulk sync.
- !servers provides a configured-owner-only private guild inventory. OWNER_ID=0
  fails closed. It performs no membership or moderation action.

## Deliberate safety adaptations, not silent equivalences

Old cross-user birthday registration, globally inferred announcement destinations,
public birth-date queries and raw private-memory birthday callbacks are not
restored. Old shared birthday profiles are not replayed into live users: local
existing dates alone are migrated; explicit re-registration selects a destination.
Deletion clears both restored rows and legacy local/shared profile residue.

The world gallery can display existing shared achievements from either bot.
Keyword-only legacy auto-achievement inference (private confession, leaked opinion,
contradictory memory, mercy/betrayal/victory) is not treated as evidence that a
private event occurred. Those inferred awards are UNSAFE_TO_RESTORE_AS_IS without
a causal, privacy-scoped event producer. Current character behavior and duo story
persistence remain; this does not claim all historical award triggers were ported.
The archive is not a replacement for the current PersistentWorld scheduler.

RPG prompts contain fictional campaign state only. No old database backups are
replayed. Memory deletion cancels admitted restored prefix/slash work before
store deletion; durable revisions fence late RPG generators and buttons.

## Recovery/admin dispositions

The machine-readable audit includes every historical command and alias, purpose,
current equivalent, old authorization model and exact risk. Missing Scaramouche
commands kept UNSAFE_TO_RESTORE_AS_IS:

| Commands | Reason / prerequisite |
|---|---|
| backupmemory | Raw shared backup can include credentials; requires protected retention, encryption and deletion coverage. selfbackup/persistence are not full equivalents. |
| banchannel, unbanchannel, bannedchannels | Missing all-path admission backend; command-only restoration would falsely promise enforcement. |
| rebanchannels | Ambiguous historical text replay can recreate stale bans. |
| blockall, reban | Unconfirmed bulk targeting/inferred membership and unsolicited output. |
| blockdm, unblockdm | Ambiguous global target selection and absent current DM admission backend. |
| dmlist, whois | Cross-user private identity/profile enumeration lacks a current scoped export contract. |
| logs | Raw third-party chat export can expose secrets and deleted/private data. |
| owneronly | Legacy in-memory switch does not cover all current event/background paths. |
| leaveserver | Immediate guild departure lacks durable exact-target confirmation. |
| rebuildmemory, rebuildrank, rebuildstats, rebuildrelationship | History replay can resurrect forgotten content; needs tombstone-aware scoped recovery and confirmation. |

Wanderer already registers its legacy admin/recovery commands. They were not
removed, expanded, or invoked in this batch. PRESENT means implementation exists,
not that every inherited handler is security-certified: notably legacy raw-log
export, immediate leaveserver, history-rebuild and OWNER_ID-conditional backup
deserve a separately authorized hardening review. These are not restored to Scara.

## Deferred and renamed

- fixdoc/docfix/gdocfix/editdoc: INTENTIONALLY_DEFERRED_PHASE_2 for Scara.
  Wanderer's inherited registered handler is unchanged and not exercised/certified.
  No Docs/Drive scopes, service-account writes or real provider writes here.
- exportface/faceexport and importface/restoreface: unresolved unsafe biometric
  portability in both bots. Current per-user enrollment, recognition and deletion
  remain; those are not import/export equivalents.
- Existing NSFW → Unrestricted naming/migration stays intact; no old aliases added.
- Existing direct installers replace Cog containers; no giant bot.py/Cog refactor.
- No currently registered command is intentionally removed in this continuation.

## Verification boundary

Automated tests exercise all eleven RPG bosses, point/medal deduplication,
legacy round-boundary migration, wrong-user/channel rejection, deletion during
generation, date parsing/leap day, delivery deduplication and preferences,
world user/channel isolation, current case resolution, slash registration,
privacy cancellation, owner denial and preservation negative cases.
Live bot startup/Discord registration is separate from human RPG button clicks
or waiting for a real birthday. No such human end-to-end run is claimed.
