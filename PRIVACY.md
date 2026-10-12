# Wanderer Bot — Privacy Policy

**Last updated: October 11, 2026**

Wanderer is a fan-made Discord character bot. This policy explains what the bot's code accesses, stores, and sends to other services when you use it. Discord also handles your messages and account information under its own privacy policy.

## Information the bot handles

- **Discord identity and settings:** Your user ID, username or display name, server and channel IDs, activity times, and the settings you choose, such as romance or NSFW mode, direct messages, and proactive replies. If you provide a birthday or time zone for a feature, those settings can also be stored.
- **Conversations and memory:** Messages you send to the bot, its replies, summaries, remembered topics and jokes, game activity, and relationship or mood values used for continuing interactions. These records can include personal details you choose to share.
- **Channel context:** To answer in context, the bot can read recent messages in a channel where it has access, including messages from people other than the person prompting it. The bot may send a shortened excerpt of that context and display names or mentions to its AI provider. It does not need to permanently save every message it reads for context.
- **Attachments and requests:** When you send or refer to an image, video, file, document, or link, the bot may download or read it to respond. A text description of media and your accompanying message may be saved in conversation memory. Search queries and a location you give to the weather command are also processed to answer you.
- **Owner face profile:** The owner can use `!enrollface` with an image or video to create a face-matching template. The template and owner ID are stored in the shared database. Face matching runs locally on the bot host; the original enrollment image is not saved as a face-profile file by this feature. The owner can inspect the profile with `!faceinfo` and delete the active profile with `!deleteface` or `!forgetface`.

## Why it uses this information

The bot uses this information to respond in character, remember conversations and preferences, manage games and relationship features, deliver optional direct messages, describe media, generate voice replies, recognize the enrolled owner's face, and answer search, weather, document, or video requests. Its code does not use this information for advertising.

## Services that receive information

- **Discord:** Carries messages, commands, and bot replies. Discord retains its own copies according to its policies.
- **Groq:** Receives prompts, relevant conversation memory and channel context to generate replies. Selected video frames and content from user-supplied learning material can be sent for analysis.
- **xAI:** Receives an image and related prompt when the image-description feature is used.
- **Fish Audio or Google text-to-speech:** Receives reply text when voice output is generated. Google text-to-speech is a fallback when Fish Audio is unavailable.
- **DuckDuckGo and the US National Weather Service:** Receive a search query or supplied weather location when those features are used. The weather lookup may first send the location to a National Weather Service location search.
- **Google Docs and linked websites:** A document shared with the bot can be read or edited through Google APIs when the relevant command is used. Opening a link or fetching a user-supplied page sends a request to that site.
- **Configured video or document worker:** If the operator enables a remote render worker, notes, document links, instructions, and related content used by video or document-editing commands are sent to that worker. Otherwise video rendering runs locally.

The bot operator's hosting provider processes stored data as part of running the bot. These services have their own retention and privacy practices. Only share content you are comfortable having processed for the features you use.

## Storage and retention

The bot stores its memory, settings, and owner face template in SQLite databases on its configured host. Some interaction state is kept in a shared database for features involving Scaramouche when the bots run together. The code has no automatic expiration for conversation history or saved preferences. It makes periodic database backups, which can contain older records and are not automatically removed by `!reset` or `!deleteface`. Media is downloaded for processing; the memory database generally stores descriptions and conversation text rather than the original image or video file. Discord and the services above may retain their own copies separately.

## Your choices and deletion

- Use `!reset` (or `!wipe`) to clear your stored conversation messages and much of the bot's remembered topics, jokes, and relationship state. This command **does not delete your entire account row, all preferences, every game or shared record, the face profile, or backups**.
- Use `!proactive off` to stop proactive replies and `!dms off` to stop optional direct messages.
- The owner can use `!deleteface` (or `!forgetface`) to remove the active face profile. The owner must separately request removal of any copies in backups.
- To request a fuller deletion, correction, or a copy of data associated with your Discord user ID, contact the bot owner in the Discord server where you use Wanderer. Say which bot and user ID the request concerns. Do not put private details in a public GitHub issue. The owner must handle records and backups outside the scope of the commands above and any copies under their control.

## Age and changes

Use the bot only if you meet Discord's minimum age requirement in your location. If you believe a younger person has used it, contact the owner to request deletion. This policy may change when the bot's features or providers change; the updated date above shows the latest revision.

Wanderer is an unofficial fan project and is not affiliated with HoYoverse.
