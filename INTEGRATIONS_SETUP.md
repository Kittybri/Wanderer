# Optional integrations

For Google Calendar/Tasks, use [Connected Accounts](CONNECTED_ACCOUNTS.md), not
manual per-user tokens. The legacy configuration instructions below remain relevant
to the other adapters and owner-only allowlisted Sheets, not Google onboarding.

Set one structured configuration with `BOT_INTEGRATIONS_CONFIG=/absolute/path/integrations.json` or `BOT_INTEGRATIONS_JSON='{...}'`. Never commit it.
On the Oracle host, keep the file outside the repository when practical and restrict it with `chmod 600`.

Sections are `github` (`token`, `allowed_repositories`, `dry_run`), `spotify` (`client_id`, `client_secret`, access/refresh tokens, `expires_at`, `user_id`), `google.accounts.DISCORD_USER_ID` (per-user OAuth tokens plus `allowed_spreadsheets`), `steam.api_key`, and `myanimelist.client_id`. Use only required OAuth scopes. Google accounts are separated by Discord user ID. Calendar creates and bot-event updates are previews unless explicitly confirmed; arbitrary user events cannot be updated. Sheets writes require an allowlisted spreadsheet ID. No adapter exposes deletion. Letterboxd scraping is disabled because there is no generally available stable supported API.

`!integrations` shows readiness without printing credentials. `!githubissue owner/repo | title | body` previews; add `| confirm` and set GitHub `dry_run` to `false` for a real, rate-limited write.

Discord presence requires Presence Intent. Soundboard requires `SOUNDBOARD_GUILD_IDS`, `SOUNDBOARD_ASSETS_JSON`, FFmpeg, PyNaCl, davey, and Connect/Speak permissions; the Python voice dependencies are declared in `requirements.txt`. Priority Speaker cannot be toggled by discord.py during playback; configure a Discord role manually if desired.

The soundboard JSON maps only `sigh`, `scoff`, `slow_clap`, `buzzer`, `exhale`, or `chuckle` to local, authorized audio files. No audio asset is bundled. Restart the bot after changing configuration.

`TATTLETALE_COOLDOWN_SECONDS` controls verified public-channel callbacks (default seven days, bounded to one hour–30 days).
