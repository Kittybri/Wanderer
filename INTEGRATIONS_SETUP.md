# Optional integrations

For Google Calendar/Tasks, use [Connected Accounts](CONNECTED_ACCOUNTS.md), not
manual per-user tokens. The legacy configuration instructions below remain relevant
to the other adapters and owner-only allowlisted Sheets, not Google onboarding.

## Current source-of-truth boundaries (October 2026)

- Google Calendar/Tasks belong to the private, user-owned
  [Connected Accounts](CONNECTED_ACCOUNTS.md) OAuth flow. The older
  `google.accounts.DISCORD_USER_ID` JSON credentials must **not**
  silently authorize Calendar or Tasks after a user disconnects.
- The legacy, separately configured Google Sheets allowlist is an
  **owner-only** integration. It is not part of public Google Connect.
- Google Docs `!fixdoc` is an inherited service-account/worker feature,
  **not** Calendar/Tasks Connected Accounts OAuth. The released legacy
  path may overwrite a document without a new confirmation. Do not expose
  it to normal users while [the private-preview safety repair]
  (https://github.com/Kittybri/Wanderer/pull/16) remains unmerged and
  unvalidated; that PR keeps the command/aliases but changes edit
  authorization and confirmation.
- Oracle deployment is the relevant host in this project, not Railway.
  Verify current paths and active SHAs on the host before following old
  deployment examples. No deployment is implied by these docs.
- Production Google OAuth verification and Phase 2 Docs/Drive scopes
  are separate tasks. Do not use a service-account document permission
  as a substitute for explicit account-bound OAuth authorization.

Set one structured configuration with `BOT_INTEGRATIONS_CONFIG=/absolute/path/integrations.json` or `BOT_INTEGRATIONS_JSON='{...}'`. Never commit it.
On the Oracle host, keep the file outside the repository when practical and restrict it with `chmod 600`.

Sections are `github` (`token`, `allowed_repositories`, `dry_run`), `spotify` (`client_id`, `client_secret`, access/refresh tokens, `expires_at`, `user_id`), `google.accounts.DISCORD_USER_ID` (legacy owner-only Sheets allowlists and credentials; **not** user-owned Calendar/Tasks onboarding), `steam.api_key`, and `myanimelist.client_id`. Use only required OAuth scopes. Google accounts are separated by Discord user ID. Calendar creates and bot-event updates are previews unless explicitly confirmed; arbitrary user events cannot be updated. Sheets writes require an allowlisted spreadsheet ID. No adapter exposes deletion. Letterboxd scraping is disabled because there is no generally available stable supported API.

`!integrations` shows readiness without printing credentials. `!githubissue owner/repo | title | body` creates a bounded proposal; execute the stored proposal using `!githubissue confirm REQUEST_ID` only after reviewing it and ensuring GitHub `dry_run` is false.

Discord presence requires Presence Intent. Soundboard requires `SOUNDBOARD_GUILD_IDS`, `SOUNDBOARD_ASSETS_JSON`, FFmpeg, PyNaCl, davey, and Connect/Speak permissions; the Python voice dependencies are declared in `requirements.txt`. Priority Speaker cannot be toggled by discord.py during playback; configure a Discord role manually if desired.

The soundboard JSON maps only `sigh`, `scoff`, `slow_clap`, `buzzer`, `exhale`, or `chuckle` to local, authorized audio files. No audio asset is bundled. Restart the bot after changing configuration.

`TATTLETALE_COOLDOWN_SECONDS` controls verified public-channel callbacks (default seven days, bounded to one hour–30 days).
