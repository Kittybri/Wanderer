# Google Docs legacy bridge: operational safety

This document describes an inherited legacy service-account/worker integration,
**not** Google Connected Accounts Phase 1 OAuth. The `!fixdoc` command remains
present in the release candidate and is **not a verified safe general-user write
API**. Do not announce broad Google Docs integration or add Docs/Drive OAuth
scopes on the strength of this legacy bridge.

## Current release limitations
The historical `!fixdoc` implementation can overwrite the contents of a
Google document shared with the service account without an independent exact
write confirmation. It may send document text to the text-generation provider.
An external `/docfix` worker is a separate trust boundary and is not
automatically safe merely because the bot can reach it.

**Do not use the old flow on irreplaceable or sensitive documents.**
Keep service-account sharing disabled until authorization, confirmation,
privacy review and backups have been validated.

## Pending safer implementation
Wanderer [draft PR #16](https://github.com/Kittybri/Wanderer/pull/16)
prepares a safer owner-only workflow:
1. Send `!fixdoc <Google document link> [instructions]` privately.
2. Wanderer reads the service-account-accessible document and creates a
   complete private TXT preview without writing to Google.
3. Read the preview, then send `!fixdoc confirm TOKEN` in the DM within
   ten minutes. The token is one-use and tied to the requesting operator.
4. The bot checks the original text and Google Docs revision, then makes
   a revision-bound update. Missing or changed revisions fail closed.
5. Remote worker-only edits remain blocked until an equivalent reviewed
   confirmation/authorization protocol exists.

The preview workflow is **NOT live until that draft is tested, merged,
deployed and confirmed**. Do not follow these future instructions against
an older running release and assume they already protect writes.

## Service account and secrets
For the separate, owner-controlled legacy integration, Google Docs API
may use an operator-managed Google service account via
`GOOGLE_SERVICE_ACCOUNT_FILE` or protected
`GOOGLE_SERVICE_ACCOUNT_JSON` environment configuration. Do not commit
service-account JSON, API keys, tokens, example live IDs or share unreviewed
documents with it. Restrict file access on Oracle.

Sharing a document as Editor grants broad rights to the service account;
it does not independently prove which Discord user owns the document.
The Phase 2 design requires per-user authorization and policy review.

## What to validate before enabling
- Fail-closed when `OWNER_ID` is absent or the actor is not the owner.
- Reject public-channel operation and missing private DM previews.
- Confirm only the exact one-use proposal, never regenerated text.
- Refuse modified/expired documents and concurrent-revision conflicts.
- A privacy reset cancels pending preview contents.
- Actual OAuth Calendar/Tasks grants remain untouched.
- Real document testing uses a disposable account and document backup.

Oracle-specific paths and services must be confirmed against the live host
before any deployment. The old Railway example is obsolete and must not be
used as an instruction to move hosting.
