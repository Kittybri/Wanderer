# Preservation-first repository

## Mandatory invariants
- Do not remove, rename, replace, consolidate, disable, or silently stop registering an existing user-facing feature or command unless the CURRENT task explicitly authorizes that specific change.
- Work within the requested subsystem. Do not refactor unrelated protected systems for cleanup.
- Older code is not obsolete merely because newer architecture exists. Before removing an implementation, determine whether it provides distinct user-facing behavior.
- If an architectural change requires losing protected behavior, STOP and report the conflict rather than deleting it.
- Preserve prefix aliases, slash commands, dynamic registration, and public help discoverability unless explicitly authorized otherwise.
- Preserve privacy/deletion coverage and user isolation through moves, restorations, and migrations. Preserve authorization, credential guards, stored confirmations, and interaction arbitration. Never restore a less secure old handler just to satisfy a name check.
- Do not replace the restored Tarot implementation with an older snapshot.
- Preserve Scaramouche and Wanderer's distinct character presentation; shared infrastructure is not permission to homogenize personalities.
- Do not bulk-sync a partial slash tree: inspect remote/local registration and protect unrelated commands.

## Protected feature families
Tarot; RPG/games; birthdays; voice; privacy deletion; memory; relationships;
duo/cross-bot interactions; Google Connected Accounts and Calendar/Tasks;
cloud integrations; home/device integrations; search/factual grounding;
media/image/vision; owner/admin/recovery controls; document/file tools;
provider/model handling; command/help registration.

## Required workflow
1. Inspect branch, worktree, current manifests, and historical audit before editing. Preserve uncommitted work and newer commits.
2. Read PRESERVATION.md and the version-controlled preservation manifests when changing protected behavior.
3. Run command-surface and feature-manifest tests BEFORE committing, in addition to affected regression tests. Run full suites before deploying.
4. Never regenerate an expected manifest merely to make a failing removal test pass. A removal/rename requires explicit current user authorization plus a reviewed change record naming the old surface, replacement/migration, rationale, privacy impact, and validation.
5. A known missing or unsafe feature belongs in the audit as unresolved, not as a falsely supported manifest feature. Do not silently erase unresolved entries.
6. Record actual live evidence separately from automated tests. Do not claim UI clicks or provider actions that were not exercised.
7. CODEOWNERS is review routing, not enforced branch protection. Do not modify repository rulesets without authorization.

## Layout
Keep existing production file locations. Flat modules are protected through this
file, CODEOWNERS, runtime manifests, and tests; no folder migration is required.
