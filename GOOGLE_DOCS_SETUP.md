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

