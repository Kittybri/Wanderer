# Server chaos games

## Scope and architecture

This batch is OFF unless a guild is explicitly enabled in the existing integrations JSON. Deterministic mechanics make no model calls. Scaramouche initiates theatrical schemes; Wanderer offers fair dice challenges, reviews court defenses and exposes recorded phantom pings. Neither bot gains moderation powers.

Runtime wiring lives in `bot.py`; `server_chaos/service.py` owns commands, consent, provenance, bounded events and a reconnect-safe five-second recovery task. `state.py` reuses WorldStore's shared `persistent_world_events` storage through its existing API for chaos receipts, budget and controls. `restoration.py` handles write-ahead cosmetic mutations. Existing GrudgeJournal, shared cooldowns, duo_sessions, birthday recovery and advanced-VC cleanup are reused. No voice, Fish Audio, home relay or dependency redesign.

The bots MUST use the same physical shared SQLite database for cross-bot court, budget, restoration and rivalry coordination. Personal preferences remain in each bot's existing database. A database path with the same spelling on different machines is not shared storage.

## Setup

Back up both existing databases before deployment. Add a `server_chaos` section to the existing JSON selected by `BOT_INTEGRATIONS_CONFIG`; do not replace other sections. Example (replace all numeric IDs):

```json
{
  "server_chaos": {
    "guilds": {
      "123456789": {
        "enabled": true,
        "mode": "MANUAL",
        "allowed_channels": [234567890],
        "allowed_roles": [345678901],
        "features": {
          "sovereign": true,
          "wager": true,
          "court": true,
          "parody": true,
          "ping": true,
          "gossip": true,
          "interference": true
        },
        "parody_mode": "MANUAL",
        "mutations": [
          {"type": "channel", "id": 234567890, "field": "name", "value": "scaramouches-court"},
          {"type": "role", "id": 345678901, "field": "name", "value": "Court Audience"}
        ],
        "max_actions": 3,
        "max_duration": 300,
        "cooldown_days": 3,
        "announcement_channel": 234567890,
        "events": ["birthday", "challenge", "tournament"],
        "timezone": "America/Los_Angeles"
      }
    }
  }
}
```

For Wanderer, enable `wager`, `court`, `interference` and the same eligible channels; omit sovereign mutations and leave prank-initiating features false. He refuses those schemes regardless. Give each bot only necessary Discord permissions: View Channel/Read Message History/Send Messages; Manage Channels for configured channel edits, Manage Roles only for configured powerless cosmetic role names, Change Nickname for its own nickname. Roles must be unmanaged, non-default, below the bot and have zero permission bits. Do not grant Administrator for this feature.

Controls require Manage Server or the configured owner. Runtime `enable` cannot override a disabled deployment configuration. No production configuration is changed by this PR.

## Commands

Use `!chaos help` or `!wanchaos help`; these are also linked from existing help.

| Scaramouche | Wanderer | Purpose |
| --- | --- | --- |
| !chaos status / budget | !wanchaos status / budget | Configuration, budget, pending recovery |
| !chaos enable / disable / restore-all | !wanchaos enable / disable / restore-all | Manager controls |
| !chaos sovereign | not offered | Start configured cosmetics |
| !chaos event challenge / tournament | not offered | Manager-attested event |
| !wager open @user dice bragging | !challenge open @user dice bragging | Voluntary invitation |
| !wager accept / reject / cancel ID | !challenge accept / reject / cancel ID | Host-specific invitation action |
| !wager balance | !challenge balance | Own fictional balance |
| !court open @user | not offered | Reply to real public evidence |
| !court accept ID / defend ID contest / cancel ID | !defense equivalents | Invited participant's court response |
| !pranks status / off | !wanpranks status / off | Consent and cancellation |
| !pranks parody / ping / gossip / court on (or off) | !wanpranks equivalents | Individual per-bot consent |
| !pranks translate | not offered | Reply to eligible public text |
| !pranks phantom @user | not offered | Consenting target prank |
| !pranks gossip @recipient | not offered | Reply to eligible public source |

Consent-off and personal cancellation remain available when the feature is disabled. `!pranks off` / `!wanpranks off` also work in DMs. Users must opt into the relevant feature on the relevant bot; opting in cannot consent for another user. Wager acceptance and court acceptance are explicit, expiring invitations.

## Chaos budget

One transactional guild budget covers both bots. Capacity is six; one point decays each 30 minutes. Events are at least five minutes apart. Sovereign costs five and suppresses every new chaos event for at least an hour, with a default three-day major-event cooldown. Status reports CALM, NORMAL, CHAOTIC or COOLDOWN. Per-user shared cooldowns add three days for parody/gossip and seven days for phantom ping. Failed attempts may still consume reservations: conservative throttling is intentional.

## Server Sovereign and recovery

Supports allowlisted channel names/topics, slowmode 0–10 seconds, powerless cosmetic role names, and the bot's own nickname. At most five actions, default three; duration 10–900 seconds, default 300. No role assignment, permissions edits, object deletion, kicks, bans, webhooks or member nickname changes.

Modes: MANUAL, EVENT, AUTONOMOUS_SAFE. Birthday checks use January 3 in the configured timezone. Challenge/tournament triggers are manager attestations, not automatic tournament detection. AUTONOMOUS_SAFE additionally permits a 1/1000 hourly attempt under the same cooldown/budget. Mood never grants authority.

Before each Discord edit, a transaction saves original/applied values, actor, target, feature, session, timestamps and restore deadline. A separate audit receipt retains outcomes. Restart resumes pending work, including edits whose network response was ambiguous. Restoration fetches current state: restore only if it still equals the applied value; preserve a different manual edit; mark deleted objects terminal; retain permission/network failures for retry. Leases prevent normal duplicate workers. Active receipts are prioritized over old audit entries.

Discord has no conditional edit API: an admin edit exactly between the fresh read and restore cannot be excluded atomically. Avoid simultaneous manual edits while emergency restoration runs.

Names already owned/configured by the birthday decoration manager are rejected to avoid conflicting restorers. `restore-all` disables new chaos, restores tracked cosmetics, cancels unfinished games/deliveries, cleans up the bot's own prank messages, invokes existing VC game cleanup and restores the captured guild-specific birthday receipts. Each bot retries its own pending recovery. Check status afterward; it is a request, not a guarantee of immediate recovery.

Legacy slowmode receipts created before this batch lack the bot-applied value. They are retained and reported for manual reconciliation rather than risking overwrite of newer administrator changes. New `!scaraslowmode` edits use the write-ahead manager with existing admin checks.

## Wagers

Scaramouche supports coin_flip, dice, high_card and disclosed one_in_six odds (challenger 1/6). Secrets-based randomness, never an LLM, chooses the result. Supported stakes: bragging or ONE fictional favor token; balances begin at ten. Favor tokens cannot purchase money, credentials, permission or real-world obligations. Wanderer offers only fair dice/bragging.

Five-minute invitations require the named human's acceptance in the same channel on the hosting bot. One BEGIN IMMEDIATE transaction validates acceptance, records the actual winner and transfers the token once. Duplicate commands cannot charge twice; insufficient balances cancel settlement safely. Expired/departed/cancelled games close harmlessly. Random ties are bounded.

## Court and rivalry

Court uses a target's actual harmless public quote, or a verified same-channel PETTY playful report from GrudgeJournal. No private/restricted channels, threads, embeds or attachments. The source is fetched again and its hash checked. Report sources must opt in. Evidence is not quoted before the target accepts.

The accepted case presents an existing puzzle. Defense is deliberately bounded to its answer, `admit`, `contest` or cancellation—no private free-form testimony. Wanderer may agree, overrule, dismiss stale evidence or find the solved puzzle not guilty. A single structured `server:court` turn uses existing duo_sessions and cannot overwrite an active text/voice duo. If no configured Wanderer responds, Scaramouche dismisses harmlessly after the bounded wait. Verdicts have no moderation consequences.

Court decisions and verified prank exposure update existing bot relationship/memory by bounded amounts. Structured `[Server game]` messages cannot start recursive partner chat. No separate relationship engine or model call is added.

## Parody, phantom ping and gossip

Parody requires Scaramouche's existing Autocorrect function, source-author consent and MANUAL or rare PARTY mode (1/1000 eligible messages). Original text is never edited/deleted. Responses explicitly identify Scaramouche's words as parody. A narrow game vocabulary, existing safety filters, cooldowns and per-source claims reject serious/sensitive text and repeat use. Wanderer cannot execute this transform.

Phantom ping requires target opt-in, an allowed public channel and daytime 09:00–21:00 in the user's timezone, plus their quiet hours. Only that user is mentionable. A durable receipt precedes send, then the bot deletes its own message after a short interval. Crash recovery without a saved message ID requires matching nonce, author and time; ambiguity is retained rather than deleting unrelated messages. No push-notification or perception claim is made. Wanderer may expose a recent verified deletion only with his own target consent, channel and quiet-hour checks.

Gossip is a labeled opt-in game. Both source author and recipient must consent; the recipient must allow DMs and be outside quiet hours. Source must be currently public and readable by the recipient. Exact source/hash/consents are rechecked before an at-most-once delivery attempt. The DM includes the actual quote and public jump link, not invented attribution. It never mines DMs/private threads/restricted channels.

## Persistence and privacy

Four default-OFF columns are added idempotently to existing user_preferences: chaos_parody, chaos_ping, chaos_gossip, chaos_court. The only new table is chaos_wallet (guild/user primary key, nonnegative balance); the existing shared event store holds all other chaos state. Existing duo and social-memory storage are reused.

Receipts contain IDs, hashes, generic event summaries and necessary before/after cosmetic values—not private message archives or credentials. Terminal chaos receipts are pruned after 30 days; active recovery, shared controls/budget and wallet accounting are retained. Opt-out/forget cancels pending personal activity and suppresses exposure; it does not erase accounting or discard restoration/audit obligations. Previously delivered Discord messages cannot be recalled as if never seen. Existing relationship-memory erasure remains governed by the existing forget pipeline.

## Troubleshooting and limitations

- Commands missing: ensure this branch was deployed and restarted; use the bot-specific names above.
- Disabled: deployment config AND runtime control must allow the guild/feature.
- No prank: consent, public source, allowed channel, safe vocabulary, quiet hours and budget all apply.
- Recovery pending: restore permissions/connectivity, inspect status, retry restore-all; do not delete recovery receipts.
- Court absent: verify both bots use the same shared database and Wanderer's channel/court/interference settings.
- Maintenance exception: one sanitized owner DM per process and a status flag; receipts remain for recovery.
- No live Discord operations were performed during implementation. Automated tests mock Discord and use temporary SQLite databases.
- Global presence takeover, wager cosmetic-role assignments, witness testimony, trivia wagers, automatic tournament detection and grudge-reduction prizes are not implemented. The supported scope is the safe subset described above.
- Recovery requires a running bot. Durable state cannot restore Discord while both processes remain offline.
