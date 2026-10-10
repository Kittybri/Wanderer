# P0 Batch C: Integration rehearsal and release preparation

STATUS: DRAFT, NOT AUTHORIZED FOR MERGE OR ORACLE DEPLOYMENT. This is a proposed operator checklist, not evidence of live-server testing.

## Candidate lineage and conflicts

Scaramouche candidate: https://github.com/Kittybri/scaramouche/pull/33 includes PR #32 and the full-suite CI workflow from #27. Wanderer candidate: https://github.com/Kittybri/Wanderer/pull/23 includes PR #22 and full-suite CI from #17. Do not merge the included changes twice. Verify the exact candidate and release-head SHAs immediately before a build.

Both repositories contain multiple independent draft PRs targeting the same release branch. The highest-density textual conflict is the preservation.yml command in each repository: most sibling PRs edit the same lines to add their own tests. Merge by combining all intended test filenames rather than taking any one version of the command. Scaramouche #25, #26, #28-#32 and Wanderer #14-#16, #18-#22 overlap there.

Wanderer PR #16 (Google Docs preview/revision guard) and #18 (owner/admin recovery controls) also edit bot.py. Their base-line hunks are in different regions from #23 main partner-routing edits, but must be reconciled and retested after a true three-way integration. Voice PR #13 is disjoint in its changed filenames. Other candidate PRs touch provider diagnostics, dependencies, Google verification files, tarot, and docs. Do not blindly overwrite complete files or cherry-pick unrelated feature rewrites.

The original romance behavior is required: Scaramouche retains conditional 45% romance-user tagging when a romance user is selected; Wanderer retains its separate conditional 45% partner-bot mention. Neither bot may falsely attribute its partner's message to a bystander. Both keep permitted mentions and their distinct personalities. PR #32 and #22 have outdated original descriptions. Use the owner correction and the newer candidate implementation as the actual review scope.

## Shared SQLite migration and rollback review

The change is additive: both versions create the same duo_reply_anchors table on shared SQLite initialization, with channel_id primary key, awaited-bot identity, saved source message and author IDs, and creation time. Existing duo_sessions columns are left intact. A repeated startup should be idempotent. Offline upgrade and competing-connection tests use temporary files only.

The new table has no automatic expiry sweep outside the duo-session cleanup path. It can retain orphaned rows after natural session expiry until the same channel is reset or explicitly cleared. This is a bounded privacy/retention cleanup follow-up, not a reason to drop the table in production.

Record the actual runtime SQLite filenames and paths from the Oracle systemd units and environment before planning anything. Do not assume older examples under /opt are active. With explicit operator approval, pause BOTH writer processes in a maintenance window to obtain a mutually consistent snapshot of the two local SQLite files and shared SQLite file. Use SQLite's online backup API or a known-safe consistent backup procedure; do not copy an active WAL database main file alone. Validate backups with PRAGMA integrity_check, restrict file permissions, and do not commit backup bytes, private conversations, or keys.

Dry-run staged migrations on restored copies of all three databases, not the Oracle originals. Initialize Scaramouche and Wanderer against the isolated copies, check schema integrity, existing duo state, romance and user-consent preferences, privacy deletion, OAuth state, and two-user isolation. Verify the restore procedure itself. Mixed old/new bot versions writing shared state are not verified; deploy as an approved coordinated pair rather than rolling one live bot independently.

Rollback means reverting BOTH code SHAs and restoring the coherent predeployment database snapshot only if data/schema integrity requires it. The additive anchor table may be left in place for older code, which should ignore it; do not automatically drop it. Restoring a predeployment DB snapshot loses subsequent state writes and must be explicitly authorized. Google token/master-key migrations and any remote workers require separate rollback planning.

## Proposed staging checklist (no steps executed here)

1. Inspect exact repo SHAs, GitHub CI results, Oracle units, Python and SQLite versions, effective data paths, active OAuth/worker dependencies, backups and secrets handling, without printing secrets.
2. Review each conflicting PR hunk; consolidate preservation test commands and reconcile Wanderer Docs/admin bot.py edits in an isolated integration branch. Do not merge to release yet.
3. Run compileall and the entire pytest suite on exact combined heads; verify the new SQLite upgrade, first-writer source selection, deleted source, simultaneous channels, privacy and consent preservation, provider failures, and service restart tests.
4. Use private Discord staging accounts and a staging guild for human-authorized live testing. Confirm true Discord reply ancestry, eligible mentions, both distinct conditional 45% branches, misattribution guard, deleted source behavior, two concurrently due sessions, prevention of repeated bot-to-bot replies, and opt-outs.
5. Separately validate actual DAVE/Opus voice and Google integrations with owner-approved test accounts. Wanderer Docs editing requires preview/confirmation and revision checks before any real write. Home/physical actions remain disabled unless separately approved.
6. Require recorded evidence for each gate. Define both known-good Oracle SHAs, backups, recovery ownership, and post-release health metrics. An approved deploy should move both bot binaries together and stop immediately on privacy leakage, unexplained ping loops, wrong-user writes, or corrupt shared state.

## Current blockers

GitHub-only evidence does not verify Oracle deployment versions, runtime paths, real Discord behavior, or shared live data. The parallel overdue-session worker race is not completely prevented by the first-writer anchor rule. Branch protection on both release branches was disabled when audited. Worker/Cloudflare check relevance needs separate classification because the live bot host is Oracle. The unmerged sibling PRs still need a combined integration test branch before merge approval.
