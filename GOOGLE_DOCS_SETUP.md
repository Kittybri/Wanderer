# Google Docs Bot Setup

This project now supports direct Google Docs editing through:

- `!fixdoc <google-doc-link> [instructions]` in Discord
- `POST /docfix` on the existing worker

## What you do not need

- You do **not** need to create a normal password for the bot.
- You do **not** need browser automation.

The correct setup is a Google **service account** with a JSON key.

## What you need to create in Google Cloud

1. Create or open a Google Cloud project.
2. Enable the **Google Docs API**.
3. Create a **service account**.
4. Create a **JSON key** for that service account.
5. Save the JSON file somewhere safe on the machine that runs the bot or worker.

Official references:

- [Create credentials](https://developers.google.com/workspace/guides/create-credentials)
- [Google Docs Python quickstart](https://developers.google.com/docs/api/quickstart/python)
- [Service accounts](https://developers.google.com/identity/protocols/oauth2/service-account)

## Environment variables

Use one of these:

- `GOOGLE_SERVICE_ACCOUNT_FILE=C:\path\to\service-account.json`
- `GOOGLE_SERVICE_ACCOUNT_JSON={...full JSON...}`

Recommended:

- use `GOOGLE_SERVICE_ACCOUNT_FILE` locally
- use `GOOGLE_SERVICE_ACCOUNT_JSON` on Railway if you later want the bot host to access Docs directly

## Share the document with the service account

After creating the service account, Google gives it an email like:

`your-bot@your-project.iam.gserviceaccount.com`

Open your Google Doc and share it with that email as an **Editor**.

Without that step, the bot cannot edit the doc.

## Discord usage

Example:

```text
!fixdoc https://docs.google.com/document/d/your-doc-id/edit tighten the wording but keep the meaning
```

`!fixdoc` is limited to the bot operator (`OWNER_ID`) and only works in a DM with the bot: the service account can
edit every document shared with it, so anyone who saw a link could otherwise have rewritten it. The bot sends the
complete proposed text as a private attachment; nothing is written until you send `!fixdoc confirm <token>` in the
same DM within 10 minutes, and the edit is refused if the document changed since the preview. Documents over 10,000
characters are not previewed. Editing through the worker is not used for this, because it cannot show a preview.

## Worker security

The worker refuses to start without `VIDEO_RENDER_SECRET` (at least 16 characters, in its environment or in
`video_render_worker.env`), and every request must carry the same value. It listens on `127.0.0.1` by default, which
is what the cloudflared tunnel in `start_video_render_stack.bat` connects to; set `VIDEO_RENDER_HOST=0.0.0.0` only if
the bot must reach it directly over your network. Requests may only set the voice-related `env_overrides` the bot
sends; anything else is ignored.

## Worker usage

If your worker is exposed through your tunnel, call:

`POST /docfix`

JSON body:

```json
{
  "bot_name": "scaramouche",
  "display_name": "Kittybri",
  "doc_url": "https://docs.google.com/document/d/your-doc-id/edit",
  "instructions": "Fix wording, grammar, and clarity but preserve meaning."
}
```

Header:

```text
X-Render-Secret: your-shared-secret
```

