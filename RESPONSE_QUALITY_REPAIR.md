# Wanderer text-only response repair

Base: `537bc0d4b9ac462f7df3d743bc5c5d7d9a96264c`.
Branch: `fix/wanderer-response-fallback-leak`. No merge authorized.

## Caller map captured before separation

All direct calls in `bot.py`, plus the callback registration, were inspected.
The following are the complete original `get_response` call sites (function
names are stable references; line numbers move during the repair).

| Classification | Caller | Existing distinguishing arguments / ownership |
| --- | --- | --- |
| VOICE | `VOICE_CONVERSATION` callback registration; `VoiceConversation.start`'s nested `respond` | Passes `get_response` as callback. Member/session check, original user/channel/text, safety appended to `extra_context`, `is_owner`, VC `channel_obj`, `is_dm=False`, `defer_delivery=True`. Same callback retained. |
| VOICE | `voice_cmd` | Six positional arguments, existing defaults; same entry retained. |
| TEXT | `_handle_message_pipeline` protective branch | `direct_to_me=True`, `defer_delivery=True`, protective context, channel/user identity. |
| TEXT | `_handle_message_pipeline` normal branch | Explicit targeting, DM flag, extra context, owner and channel object. |
| TEXT | `spar_cmd`, `confess_cmd`, `therapy_cmd`, `lore_cmd`, `translate_cmd`, `whoami_cmd` | Six positional arguments; creator command adds `is_owner=True`. |
| TEXT | `search_cmd`, `solve_cmd` | `use_search=True`. |
| TEXT | `dm_cmd` | `is_dm=True`. |
| TEXT | `slash_wanderer` | Channel, DM and direct-target flags. |
| DUO | `_run_duo_prompt_for_actor` | Session setup first, actor identity, extra context, channel and DM flag. |
| DUO | `verdict_cmd`, `both_cmd`, `duet_cmd`, `argue_cmd`, `compare_cmd`, `interrogate_cmd`, `choose_cmd`, `trial_cmd`, `mission_cmd`, `truthdare_cmd` | Session/duo instructions in extra context and channel object. |
| BACKGROUND / DUO | `_duo_autoplay_loop` | `direct_to_me=False`, `DUO_AUTOPLAY` context; existing bounded session ownership retained. |
| BACKGROUND | `_maybe_jealous_partner_interjection` | Explicit `direct_to_me=False`, `is_dm=False`, jealousy context and human message identity. |

There are 26 original direct call expressions: two message-pipeline sites,
one voice command, and the remaining named sites above. The callback registration
is an additional indirect VOICE caller. No OTHER call site was found.
After separation only `voice_cmd` and the explicit `get_text_response` adapter
call `get_response` directly. The voice registration is unchanged.

## Boundary and voice contract

`get_response(..., _text_policy=False)` keeps the existing default policy.
`get_text_response` explicitly sets the keyword to true. No global/thread/task
mode is used, so concurrent text cannot switch a voice call's policy.
The model/context/memory core is shared rather than copied.

Legacy `qai`, `_rewrite_reply_once`, `_maybe_self_edit_reply`, provider methods,
voice-note rewrite, voice command, TTS and send_voice retain their prior code.
Shared fallback and phrase helpers default to legacy behavior. The original
two self-edits, anti-repeat behavior, prompt length selection, cooldown silence,
protective fallback, return/defer and cancellation semantics remain in voice.
These known voice limitations are deliberately NOT repaired here.

Tests project only explicit text-policy flags to false and compare the complete
remaining AST with hashes independently captured from the exact base commit.
They also hash every voice Python file, voice_handler, requirements,
provider_config and anti_repeat byte-for-byte. Expectations are not generated
from the repaired candidate. Live voice is not exercised in this batch.

## Root paths and fallback inventory

| Path | Purpose and defect | Text policy |
| --- | --- | --- |
| `_groq_blocking` / `_groq_quick_blocking` | Provider exceptions become empty strings; unchanged shared provider core. | Bounded text recovery treats empty results as unavailable, not an answer. |
| `_guarded_fallback_reply` | Empty/error/rejected results selected Wanderer `_FALLBACK_LINES`; exhausted cooldown could return empty. | Explicit text flag returns honest failure for direct requests, silence for ambient work. |
| `_provider_pause_reply` | Groq exhaustion/rate limit could suppress a repeated direct request. | Explicit text flag yields one bounded notice per processed direct request; provider circuit/key cooldown and Discord pacing remain. |
| `get_response` generation retry | Matching opening words counted as repetition; a later empty draft overwrote a useful draft. | Compare whole answer content, trim stale interjections, preserve best valid draft; two generation attempts maximum. |
| `_maybe_self_edit_reply` → `_rewrite_reply_once` → `qai` | Rewrite recovery itself could return a canned fallback and replace a valid answer; main flow could self-edit twice. | Separate text edit: one raw attempt; exceptions/empty/internal instructions keep the original. Two total generation/edit attempts, no second post-edit. |
| Post-sanitization / main text send | Sanitization could leave nothing; top-level generation errors used punctuation/one-line reactions. | Final text validation returns an honest notice for direct failures; guarded send distinguishes delivery failure from intentional silence. |
| Protective path | Bypasses optional character systems; prior generic breathing line could replace the requested support. | Existing priority retained; actual answer or honest service notice. |
| Search | Search bundle normally returns empty results on error; outer exception may fail request. | Original question retained; existing no-result path continues; raised errors yield honest failure. No invented search results. |
| Optional chat triggers | Random brevity, milestone/anniversary/hat/food/silence responses could consume direct substantive requests. | Substantive direct requests retain ordinary answer ownership; short banter retains character bits. Visible short chat generations use `text_qai`. |
| Background / duo | Legacy `qai` also serves unrelated RPG, birthday, internal memory and other protected features. | Those independent feature callers are not globally rewritten. Migrated `get_text_response` background callers retain ambient silence on failure. |

The old `_FALLBACK_LINES` remain unchanged for the explicitly preserved legacy
path and recognition of bad text drafts. They are not called by the new normal
text recovery policy. Internal retry guidance has a separate constant and
structured `ReplyKind`/`ResponseResult`, not a user-visible fallback pool.
Known sentinel detection is supplemented by editing-language detection; this is
a deterministic guard, not a guarantee that arbitrary model prose is correct.

Sanitized six-hour staging log review at investigation time: 5 self-edit events,
0 matched rate-limit/provider-error/suppression/send-failure events. Logs do not
record sufficient provenance to attribute each user-reported historical line
to one exact generation. Source paths above reproduce the mechanism; no claim
of transcript-by-transcript production attribution is made.

## Validation checkpoint

Pre-deployment candidate checks (2026-10-08):

- Complete Wanderer suite: **432 passed, 1 skipped**, one existing local
  urllib3/LibreSSL warning; 86.14 seconds.
- Focused response/pipeline/arbitration/preservation/voice suites:
  **215 passed, 1 skipped**, same local warning; 26.96 seconds.
- New response policy, runtime pipeline and voice-boundary coverage: 84 tests.
- Runtime preservation/import: 177 prefix commands, 25 slash entries,
  zero manifest errors; preserved help output 30,935 characters.
- Compile checks and `git diff --check`: pass.
- Secret-pattern scan of all seven changed/new files: zero matches.
- Protected voice files, voice dependency files and legacy projected generation
  functions match their pre-repair release hashes.

Deployment and live evidence will be appended here. The older combined
`STAGING_VALIDATION.md` is in Scaramouche's checkout and is deliberately not
edited in this Wanderer-only batch. No Scaramouche, Google, voice infrastructure,
database migration, dependency or restored-feature implementation change is part
of this repair. No real provider writes or Discord voice actions are authorized.

## Staging deployment evidence (2026-10-08)

Functional candidate deployed: `0813e0f38ff574b4d158cb788db28351784a0d05`.
Working directory: `/opt/scara-wanderer-staging-fallback/releases/wanderer-text-0813e0f38ff5`.

- Exact committed archive deployed; runtime preservation probe passed on Oracle.
- `wanderer-staging`: active, gateway/readiness marker observed, zero startup
  tracebacks, zero automatic restarts; one authorized controlled restart.
- Scaramouche and connection-service PIDs/working directories unchanged;
  neither was restarted.
- Original environment files and existing Wanderer systemd drop-ins compared
  before/after by hashes held only in memory: unchanged. Only the new Wanderer
  working-directory/release-label override was installed; no voice settings changed.
- Connected-account, bot-grant and OAuth-session rows compared in memory:
  unchanged. No credentials or private row data recorded in evidence.
- SQLite `quick_check`: `ok` for Wanderer, shared-state and Tarot stores.
- No provider writes, Google configuration changes or live voice actions.
- Re-running pytest inside the production virtualenv was unavailable because
  pytest is not installed there. No runtime dependencies were installed or
  changed. The complete/focused results above are from the committed candidate
  in the local test environment; the Oracle runtime import/manifest probe passed.

Live TEXT verification is **pending human Discord login**. The approved staging
channel opens an account chooser requesting login for both staging accounts.
No synthetic live messages have been sent, so no live response-quality pass is
claimed. Remaining sequence: casual greeting, harmless substantive/factual
question, direct follow-up, opener-similarity exercise, both-bot mention. Provider
failure has been tested offline; do not deliberately exhaust the shared live
provider quota or disrupt voice to simulate it.

Checkpoint status: `WANDERER_TEXT_STILL_BLOCKED` (live text checks only).

## Live continuation and targeted correction (2026-10-09)

The login blocker above was cleared. Initial checks used the approved disposable
Kittybi account in General (`1486228109027180597`) of the private Wanderer guild.
These results are historical evidence for candidate `0813e0f`, not a final pass:

- Greeting: PASS. Request `1558013447717785764`, reply `1558013458484568095`:
  “All set. What's the test?”
- Factual explanation: FAIL, incomplete sentence. Request `1558013559022034995`,
  reply `1558013572729147443` stopped after “so the ice becomes”.
- Direct follow-up: PASS. Request `1558013707592794135`, reply
  `1558013723640332332` correctly explained lower density and displacement.
- Subsequent background/partner output exposed remaining legacy recovery paths:
  `1558049066078834689` (“Try that again without the recycled opener.”),
  `1558049129089990667` (“Say what you mean.”), and
  `1558149157028495384` (“I am listening. Briefly.”).

The factual request logged a self-edit but its provider finish metadata was not
retained. Inspection reproduced acceptance of a `finish_reason=length` partial
rewrite; this is a demonstrated mechanism, not a claim that the historical
provider finish reason is known. Text generation/rewrite now checks for normal
completion before accepting content. A truncated rewrite preserves the complete
original; failed first generation follows bounded recovery. Legacy voice provider
extraction is unchanged and explicitly covered by the regression test.

The text-only partner handler, unsent simulation, proactive loop, voluntary-DM
loop and rival-event loop now use checked text recovery. Ambient failures yield
no fabricated reply; direct failures retain the honest service notice. Partner
phrase handling preserves content. Existing session ownership, eligibility,
timing, static personality pools and loop suppression are unchanged. Unrelated
RPG/birthday/internal-summary `qai` callers and voice remain on their prior path.

New tests cover non-normal provider finish reasons, keeping a complete original
after a truncated rewrite, direct-versus-ambient failure, unsent-task cleanup
without a send, and all five migrated background/partner routes.

One initial full-suite run had 435 passes, one skip and one failure caused by the
sandbox denying a localhost bind in the existing callback test. The suite was
rerun with localhost access and passed; this was not a code regression. No callback
code, credentials, or configuration was changed.

Final pre-deployment checks for the corrected candidate:

- Full suite: **440 passed, 1 skipped**, 81.86 seconds.
- Focused response/arbitration/preservation/voice suite: **223 passed, 1 skipped**,
  37.97 seconds. New response/voice-boundary coverage totals 92 tests.
- Existing skip: optional real Opus coverage without `VOICE_OPUS_LIBRARY`;
  existing warning: local urllib3/LibreSSL build.
- Runtime command/import validation: 177 prefix commands, 25 slash entries,
  help 30,935 characters, zero manifest errors.
- Compile: pass (temporary writable bytecode-cache path used after the sandbox
  denied the default macOS cache); `git diff --check`: pass.
- Staged six-file credential scan: zero findings; additional key-pattern scan
  across all seven batch files: zero findings.
- Voice legacy AST and byte-hash checks pass without updating the baseline.

## Corrected deployment and final live checks (2026-10-09)

Exact tested/deployed functional SHA:
`19b37b254725ca71299525325b00100965ce589b`.
Release directory:
`/opt/scara-wanderer-staging-fallback/releases/wanderer-text-19b37b254725`.

Only Wanderer was redeployed, with one further controlled restart (two total
controlled restarts across this repair batch). Active/readiness confirmed, zero
startup tracebacks and zero automatic restarts. The on-host preservation probe
again returned 177 prefix commands, 25 slash entries, zero errors. Scaramouche
and callback PIDs/working directories, protected environment/voice configuration
hashes, and Google connection/grant/session rows matched before/after deployment.
Wanderer, shared-state and Tarot SQLite `quick_check` each returned `ok`.

Remaining live checks used the already signed-in primary Kittybri account in the
same approved General channel. No account switch, voice-channel operation or
voice preference change was performed.

| Scenario | Actual evidence | Result |
| --- | --- | --- |
| Casual greeting | Earlier request/reply `1558013447717785764` / `1558013458484568095`; already passed, not repeated | PASS on initial candidate |
| Factual retest | Mention request `1558202792286490665` triggered existing automatic audio-note delivery `1558202816038961162`; no audio playback/voice-quality claim. Existing `/wanderer` text entry then returned complete two-sentence density/lattice explanation in `1558202979864023230` | PASS, corrected candidate via slash text |
| Follow-up | Earlier request/reply `1558013707592794135` / `1558013723640332332`; complete explanation, already passed | PASS on initial candidate |
| Shared opening, different substance | Requests `1558274301327843410` and `1558274414049755333` both asked for “The useful distinction is”; replies `1558274318213980361` and `1558274428503326720` explained evaporation/boiling and melting/freezing. Second answer varied the opening but retained useful substance | PASS; identical generated opening acceptance additionally covered offline |
| Both-bot mention | Synthetic fictional-explorer request `1558274612427493458`; Wanderer reply `1558274628558921760` named curiosity/perseverance, Scaramouche reply `1558274628709785641` independently addressed the human | PASS, no Wanderer fallback or immediate feedback loop observed |
| Provider failure | Offline injected errors/exhaustion/empty/internal/length-limited completions; direct notices versus ambient silence | PASS automated; no deliberate live outage or quota exhaustion |

No internal retry/fallback phrase appeared in the corrected candidate's deliberate
live text checks. This finite observation does not certify arbitrary future model
prose or every unrelated legacy command. Background/partner failure routes are
covered by automated checks; no forced timer/config changes were made to trigger
every autonomous feature live. Existing static personality pools remain intact.
The evaporation answer's phrasing “whole liquid vaporize abruptly” is imprecise;
it was a complete answer rather than fallback leakage, not a scientific-accuracy
certification. No unrelated factual or personality redesign was made.

Voice behavior changed: **NO**. Voice implementation/dependency files changed:
**NO**. Legacy voice generation/rewriting/default fallback contracts remain locked
to the original release; no live voice validation is claimed. The complete caller
classification remains at the start of this document. No merge, Scaramouche
deployment, Google configuration change, or Phase 2 work occurred.

Final scoped status: `WANDERER_TEXT_FIXED_VOICE_UNCHANGED`.
