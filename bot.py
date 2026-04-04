"""
Wanderer Bot — The Wanderer (Kunikuzushi) v1
Post-Sumeru. Traveling with the Traveler. Trying to be better.
Still sharp, still proud. Will not answer to Scaramouche.
Powered by Groq (free) + Fish Audio TTS.
"""

import discord
from discord import app_commands
from discord.ext import commands, tasks
import os, re, random, asyncio, io, time, json, traceback
from urllib.parse import quote_plus, urlencode
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from memory import Memory
from voice_handler import get_audio, get_audio_mooded
from character_vision import ask_character_bot, vision_exhausted_remaining, vision_is_exhausted
from face_memory import (
    enroll_face_profile,
    enroll_face_profile_from_frames,
    face_support_ready,
    is_face_check_request,
    is_face_enroll_request,
    match_face,
    match_face_frames,
)
from grounded_search import (
    extract_urls,
    fetch_url_preview,
    format_search_context,
    format_search_sources,
    format_url_preview_context,
    search_web,
)
from video_reports import (
    build_weather_video_notes,
    extract_teaching_material,
    fetch_rendered_video_bytes,
    render_duo_debate_video,
    render_teaching_video,
    video_renderer_available,
)
from anti_repeat import (
    build_prompt_guard,
    detect_opening_phrase,
    diversify_reply,
    fallback_reply,
    get_runtime_recent,
    looks_repetitive,
    merge_recent_messages,
    pick_fresh_option,
    replace_opening_phrase,
    remember_output,
)
from relationship_engine import (
    RARE_PHRASES,
    analyze_style_deltas,
    apply_style_deltas,
    callback_relevant,
    compute_bot_stage,
    compute_emotional_arc,
    describe_bot_relationship,
    describe_contradictory_memory,
    describe_conflict_aftermath,
    describe_conflict_followup,
    describe_dual_verdict_mode,
    describe_emotional_layers,
    describe_emotional_event,
    describe_emotional_arc,
    describe_arc_unlocks,
    describe_campaign_npcs,
    describe_duo_scene_stage,
    describe_evidence_locker,
    describe_live_world_context,
    describe_lore_hook,
    describe_private_confession_scene,
    describe_private_opinion_context,
    describe_relationship_unlock_scene,
    describe_silent_presence,
    describe_triangle_jealousy,
    describe_specific_lore_tree,
    describe_relationship_progression,
    describe_scenario_context,
    describe_scene_state,
    describe_speech_drift,
    describe_topic_profile,
    detect_emotional_triggers,
    detect_banter_theme,
    detect_conflict_signal,
    detect_intervention_reason,
    detect_scenario,
    detect_topics,
    detect_repair_signal,
    extract_continuity_hooks,
    infer_duo_ending_tag,
    extract_memory_events,
    extract_callback_candidate,
    infer_scene_update,
    infer_bot_relation_deltas,
    progression_milestone_note,
    relationship_milestone_note,
)

load_dotenv()

DISCORD_TOKEN      = os.getenv("DISCORD_TOKEN", "")
GROQ_API_KEY       = os.getenv("GROQ_API_KEY", "")
GROQ_API_KEY_2     = os.getenv("GROQ_API_KEY_2", "")
GROQ_API_KEY_3     = os.getenv("GROQ_API_KEY_3", "")
FISH_AUDIO_API_KEY = os.getenv("FISH_AUDIO_API_KEY", "")
WEATHER_API_KEY    = os.getenv("WEATHER_API_KEY", "")
NWS_USER_AGENT     = os.getenv("NWS_USER_AGENT", "scara-wanderer-bots/1.0 (contact: local-use)")
OWNER_ID           = int(os.getenv("OWNER_ID", "0") or "0")
PARTNER_BOT_ID     = int(os.getenv("PARTNER_BOT_ID", "0") or "0")  # Scaramouche bot ID
PARTNER_INVITE_PERMISSIONS = int(os.getenv("PARTNER_BOT_PERMISSIONS", "8") or "8")
PARTNER_INVITE_SCOPES = os.getenv("PARTNER_BOT_SCOPES", "bot applications.commands").strip() or "bot applications.commands"
PARTNER_CLIENT_ID_OVERRIDE = (os.getenv("SCARAMOUCHE_CLIENT_ID") or os.getenv("PARTNER_CLIENT_ID") or "").strip()
GROQ_EXHAUSTED_SILENCE_S = int(os.getenv("GROQ_EXHAUSTED_SILENCE_S", "600") or "600")
PROVIDER_PAUSE_COOLDOWN_S = int(os.getenv("PROVIDER_PAUSE_COOLDOWN_S", "120") or "120")
CHANNEL_CONTEXT_LIMIT_DIRECT = int(os.getenv("CHANNEL_CONTEXT_LIMIT_DIRECT", "20") or "20")
CHANNEL_CONTEXT_LIMIT_AMBIENT = int(os.getenv("CHANNEL_CONTEXT_LIMIT_AMBIENT", "8") or "8")
CHANNEL_CONTEXT_LIMIT_DM = int(os.getenv("CHANNEL_CONTEXT_LIMIT_DM", "16") or "16")
CHANNEL_CONTEXT_MESSAGE_CHARS = int(os.getenv("CHANNEL_CONTEXT_MESSAGE_CHARS", "110") or "110")
HISTORY_LIMIT_DIRECT = int(os.getenv("HISTORY_LIMIT_DIRECT", "120") or "120")
HISTORY_LIMIT_AMBIENT = int(os.getenv("HISTORY_LIMIT_AMBIENT", "80") or "80")
MAIN_REPLY_MAX_TOKENS_DIRECT = int(os.getenv("MAIN_REPLY_MAX_TOKENS_DIRECT", "420") or "420")
MAIN_REPLY_MAX_TOKENS_AMBIENT = int(os.getenv("MAIN_REPLY_MAX_TOKENS_AMBIENT", "220") or "220")
SELF_EDIT_MIN_REPLY_CHARS = int(os.getenv("SELF_EDIT_MIN_REPLY_CHARS", "180") or "180")
RECENT_REPLY_PACING_WINDOW = int(os.getenv("RECENT_REPLY_PACING_WINDOW", "7") or "7")
LONG_REPLY_CHAR_THRESHOLD = int(os.getenv("LONG_REPLY_CHAR_THRESHOLD", "420") or "420")
LONG_REPLY_SENTENCE_THRESHOLD = int(os.getenv("LONG_REPLY_SENTENCE_THRESHOLD", "5") or "5")
LONG_REPLY_PARAGRAPH_THRESHOLD = int(os.getenv("LONG_REPLY_PARAGRAPH_THRESHOLD", "2") or "2")
GROQ_MODEL_PRIMARY = os.getenv("GROQ_MODEL_PRIMARY", "llama-3.3-70b-versatile").strip() or "llama-3.3-70b-versatile"
GROQ_MODEL_LIGHT = os.getenv("GROQ_MODEL_LIGHT", "llama-3.1-8b-instant").strip() or GROQ_MODEL_PRIMARY

# Owner-only mode: when True, bot ignores all users except the owner
_owner_only_mode = False
# DM-blocked users: bot won't respond to them anywhere
_dm_blocked_users: set[int] = set()

# ── Groq client (free, OpenAI-compatible) ─────────────────────────────────────
from groq import Groq


def _load_groq_keys() -> list[str]:
    keys: list[str] = []

    def _remember(value: str):
        cleaned = (value or "").strip()
        if cleaned and cleaned not in keys:
            keys.append(cleaned)

    packed = os.getenv("GROQ_API_KEYS", "")
    if packed:
        for piece in re.split(r"[\n,;]+", packed):
            _remember(piece)

    numbered: list[tuple[int, str]] = []
    for env_name, env_value in os.environ.items():
        if env_name == "GROQ_API_KEY":
            numbered.append((0, env_value))
            continue
        match = re.fullmatch(r"GROQ_API_KEY_(\d+)", env_name)
        if match:
            numbered.append((int(match.group(1)), env_value))
    for _, env_value in sorted(numbered, key=lambda item: item[0]):
        _remember(env_value)
    return keys


_groq_keys = _load_groq_keys()

_DISCORD_OAUTH_RE = re.compile(r"https?://(?:ptb\.|canary\.)?discord(?:app)?\.com/oauth2/authorize\?[^\s>]+", re.IGNORECASE)
_DISCORD_SERVER_INVITE_RE = re.compile(r"https?://(?:www\.)?(?:discord\.gg|discord(?:app)?\.com/invite)/[^\s>]+", re.IGNORECASE)


def _partner_install_client_id() -> str:
    if PARTNER_CLIENT_ID_OVERRIDE:
        return PARTNER_CLIENT_ID_OVERRIDE
    if PARTNER_BOT_ID:
        return str(PARTNER_BOT_ID)
    return ""


def _build_partner_invite_url(guild_id: int | None = None) -> str:
    client_id = _partner_install_client_id()
    if not client_id:
        return ""
    params = {
        "client_id": client_id,
        "permissions": str(PARTNER_INVITE_PERMISSIONS),
        "scope": PARTNER_INVITE_SCOPES,
    }
    if guild_id:
        params["guild_id"] = str(guild_id)
        params["disable_guild_select"] = "true"
    return f"https://discord.com/oauth2/authorize?{urlencode(params)}"


def _extract_oauth_link(text: str) -> str:
    match = _DISCORD_OAUTH_RE.search(text or "")
    return match.group(0) if match else ""


def _is_partner_invite_request(text: str) -> bool:
    lowered = (text or "").lower()
    if "scaramouche" not in lowered and "scara" not in lowered and "other bot" not in lowered and "the other bot" not in lowered:
        return False
    return any(token in lowered for token in ["invite", "add", "bring", "summon", "join", "come here"])


def _partner_invite_url_from_message(message: discord.Message) -> str:
    guild = message.guild
    provided_oauth = _extract_oauth_link(message.content)
    return provided_oauth or _build_partner_invite_url(guild.id if guild else None)


def _partner_invite_view(invite_url: str) -> discord.ui.View | None:
    if not invite_url:
        return None
    view = discord.ui.View()
    view.add_item(discord.ui.Button(label="Invite Scaramouche", url=invite_url))
    return view


_invite_pressure: dict[tuple[int, int], dict[str, float | int]] = {}
_INVITE_PRESSURE_WINDOW_S = 1800
_INVITE_PRESSURE_COOLDOWN_S = 600


def _invite_pressure_key(message: discord.Message) -> tuple[int, int]:
    scope_id = message.guild.id if message.guild else message.author.id
    return message.author.id, scope_id


def _invite_threshold(user: dict | None) -> int:
    affection = int((user or {}).get("affection", 0) or 0)
    trust = int((user or {}).get("trust", 0) or 0)
    if affection >= 65 or trust >= 65:
        return 2
    if affection >= 35 or trust >= 35:
        return 3
    return 4


def _is_convincing_language(text: str) -> bool:
    lowered = (text or "").lower()
    return any(
        token in lowered
        for token in [
            "please", "plz", "pretty please", "pleeease", "pleaseee", "beg",
            "cmon", "come on", "you agreed", "you said yes", "administrator rights",
            "admin rights", "do it for me", "i need him here", "just this once",
        ]
    )


def _invite_progress_text(attempts: int, threshold: int) -> str:
    if attempts >= threshold:
        return "...Fine. Here."
    if attempts == 1:
        return "No. If he needs to be here that badly, you can stop trying to make me say it twice."
    if attempts == 2:
        return "You're still asking. Persistent."
    return "You really aren't letting this go. Keep pushing and I'll decide whether this is worth ending the conversation faster."


def _handle_partner_invite_pressure(message: discord.Message, user: dict | None) -> tuple[str | None, discord.ui.View | None]:
    guild = message.guild
    if guild and PARTNER_BOT_ID and guild.get_member(PARTNER_BOT_ID):
        return "He's already in this server. Look around before asking again.", None

    key = _invite_pressure_key(message)
    now = time.time()
    state = _invite_pressure.get(key, {"count": 0, "last_ts": 0.0, "granted_ts": 0.0})
    if now - float(state.get("last_ts", 0.0) or 0.0) > _INVITE_PRESSURE_WINDOW_S:
        state = {"count": 0, "last_ts": 0.0, "granted_ts": 0.0}

    state["last_ts"] = now
    state["count"] = int(state.get("count", 0) or 0) + 1 + (1 if _is_convincing_language(message.content) else 0)
    threshold = _invite_threshold(user)
    invite_url = _partner_invite_url_from_message(message)

    if state.get("granted_ts") and now - float(state.get("granted_ts", 0.0) or 0.0) < _INVITE_PRESSURE_COOLDOWN_S:
        state["count"] = 0
        _invite_pressure[key] = state
        return None, None

    attempts = int(state["count"])
    if attempts >= threshold:
        state["granted_ts"] = now
        state["count"] = 0
        _invite_pressure[key] = state
        if invite_url:
            return _invite_progress_text(attempts, threshold), _partner_invite_view(invite_url)
        if _DISCORD_SERVER_INVITE_RE.search(message.content or ""):
            return (
                "...Fine. That server invite won't add a bot. Set `PARTNER_BOT_ID` or `SCARAMOUCHE_CLIENT_ID`, "
                "then I'll give you the real install link."
            ), None
        return (
            "...Fine. I would, if you'd actually given me what I need. Set `PARTNER_BOT_ID` or `SCARAMOUCHE_CLIENT_ID`, "
            "then ask again."
        ), None

    _invite_pressure[key] = state
    return _invite_progress_text(attempts, threshold), None

class RotatingGroq:
    """Groq client that rotates API keys on rate limit errors."""
    def __init__(self):
        self._clients = [Groq(api_key=k) for k in _groq_keys]
        self._idx = 0
        self._exhausted_until = 0.0
        print(f"[GROQ] Loaded {len(self._clients)} API key(s)")

    @property
    def _client(self):
        return self._clients[self._idx % len(self._clients)]

    def _rotate(self):
        old = self._idx
        self._idx = (self._idx + 1) % len(self._clients)
        print(f"[GROQ] Key {old+1} rate-limited, rotating to key {self._idx+1}")

    @property
    def chat(self):
        return self._client.chat

    def _mark_exhausted(self, error: Exception | str | None = None):
        retry_after = _parse_rate_limit_retry_s(str(error or ""))
        self._exhausted_until = max(self._exhausted_until, time.time() + retry_after)
        print(f"[GROQ] All keys exhausted; suppressing ambient chatter for {retry_after}s")

    def clear_exhausted(self):
        self._exhausted_until = 0.0

    def is_exhausted(self) -> bool:
        return time.time() < self._exhausted_until

    def exhausted_remaining(self) -> int:
        return max(0, int(self._exhausted_until - time.time()))

    def call_with_retry(self, **kwargs):
        """Try current key, rotate on rate limit, try remaining keys."""
        if self.is_exhausted():
            raise RuntimeError(f"Groq exhausted; retry in {self.exhausted_remaining()}s")
        last_err = None
        for _ in range(len(self._clients)):
            try:
                result = self._client.chat.completions.create(**kwargs)
                self.clear_exhausted()
                return result
            except Exception as e:
                err_str = str(e)
                if "rate_limit" in err_str.lower() or "429" in err_str:
                    last_err = e
                    self._rotate()
                else:
                    raise
        self._mark_exhausted(last_err)
        raise last_err  # All keys exhausted

groq_client = RotatingGroq()
GROQ_MODEL = GROQ_MODEL_PRIMARY

# ── Voice message transcription (Groq Whisper) ───────────────────────────────
async def transcribe_voice_message(attachment: discord.Attachment) -> str | None:
    """Download a Discord voice message and transcribe it via Groq Whisper."""
    try:
        import aiohttp as _aio, tempfile, os as _os
        async with _aio.ClientSession() as sess:
            async with sess.get(attachment.url) as resp:
                if resp.status != 200:
                    return None
                audio_bytes = await resp.read()
        suffix = ".ogg" if attachment.filename.endswith(".ogg") else ".mp3"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name
        try:
            def _transcribe():
                client = Groq(api_key=_groq_keys[0])
                with open(tmp_path, "rb") as f:
                    result = client.audio.transcriptions.create(
                        model="whisper-large-v3",
                        file=f,
                        response_format="text",
                    )
                return result.strip() if isinstance(result, str) else (result.text or "").strip()
            text = await asyncio.get_event_loop().run_in_executor(None, _transcribe)
            print(f"[VOICE] Transcribed: {text[:100]!r}")
            return text if text else None
        finally:
            try: _os.unlink(tmp_path)
            except: pass
    except Exception as e:
        log_error("transcribe_voice_message", e)
        return None


def _parse_rate_limit_retry_s(error_text: str) -> int:
    match = re.search(r"try again in (?:(\d+)h)?(?:(\d+)m)?([\d.]+)s", error_text or "", re.IGNORECASE)
    if match:
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = float(match.group(3) or 0.0)
        retry_after = int(hours * 3600 + minutes * 60 + seconds)
        return max(GROQ_EXHAUSTED_SILENCE_S, retry_after)
    match = re.search(r"retry[- ]after[:= ]+(\d+)", error_text or "", re.IGNORECASE)
    if match:
        return max(GROQ_EXHAUSTED_SILENCE_S, int(match.group(1)))
    return GROQ_EXHAUSTED_SILENCE_S


def _is_rate_limited_error(error: Exception | str | None) -> bool:
    text = str(error or "").lower()
    return "429" in text or "rate limit" in text or "rate_limit" in text or "exhausted" in text


def _should_suppress_ambient_reply(is_dm: bool, direct_to_me: bool) -> bool:
    return (not is_dm) and (not direct_to_me) and groq_client.is_exhausted()


def _context_limit_for_reply(*, is_dm: bool, direct_to_me: bool) -> int:
    if is_dm:
        return CHANNEL_CONTEXT_LIMIT_DM
    return CHANNEL_CONTEXT_LIMIT_DIRECT if direct_to_me else CHANNEL_CONTEXT_LIMIT_AMBIENT


def _history_limit_for_reply(*, is_dm: bool, direct_to_me: bool) -> int:
    if is_dm:
        return max(HISTORY_LIMIT_DIRECT, 120)
    return HISTORY_LIMIT_DIRECT if direct_to_me else HISTORY_LIMIT_AMBIENT


def _reply_token_budget(*, is_dm: bool, direct_to_me: bool, use_search: bool, is_owner: bool) -> int:
    if use_search or is_owner:
        return max(MAIN_REPLY_MAX_TOKENS_DIRECT, 420)
    if is_dm or direct_to_me:
        return MAIN_REPLY_MAX_TOKENS_DIRECT
    return MAIN_REPLY_MAX_TOKENS_AMBIENT


def _select_text_model(
    *,
    route: str = "auto",
    is_dm: bool = False,
    direct_to_me: bool = True,
    use_search: bool = False,
    is_owner: bool = False,
    scenario: str = "",
    duo_mode: str = "",
    has_lore: bool = False,
) -> str:
    route = (route or "auto").strip().lower()
    if route == "primary":
        return GROQ_MODEL_PRIMARY
    if route == "light":
        return GROQ_MODEL_LIGHT
    if use_search or is_owner or duo_mode:
        return GROQ_MODEL_PRIMARY
    if has_lore or scenario in {"emotional_comfort", "lore_discussion", "relationship_progression", "combat_action"}:
        return GROQ_MODEL_PRIMARY
    if is_dm or direct_to_me:
        return GROQ_MODEL_PRIMARY
    return GROQ_MODEL_LIGHT

import random as _rmod, memory as _mmod
_mmod.random = _rmod
_silence_pending: set[tuple[int, int]] = set()

# ── Narration stripper ────────────────────────────────────────────────────────
def _unwrap_dialogue_quotes(text: str) -> str:
    cleaned = (text or "").strip()
    quote_pairs = [
        ('"', '"'),
        ('“', '”'),
    ]
    for _ in range(2):
        changed = False
        for left, right in quote_pairs:
            if cleaned.startswith(left) and cleaned.endswith(right) and len(cleaned) >= (len(left) + len(right) + 1):
                cleaned = cleaned[len(left):-len(right)].strip()
                changed = True
                break
        if not changed:
            break
    return cleaned


def strip_narration(text: str) -> str:
    try:
        original = text
        text = re.sub(r'\*[^*]+\*', '', text)
        text = re.sub(r'\([^)]+\)', '', text)
        text = re.sub(r'\[[^\]]+\]', '', text)
        text = re.sub(r'\b(he|she|they|wanderer|kunikuzushi)\s+(said|replied|muttered|sighed|whispered|snapped)[,.]?\s*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'<@!?\d+>', '', text)
        text = re.sub(r'<#\d+>', '', text)
        text = re.sub(r'<@&\d+>', '', text)
        text = re.sub(r'\s{2,}', ' ', text).strip().lstrip('.,; ')
        text = _unwrap_dialogue_quotes(text)
        if not text or len(text) < 3:
            text = original.replace('*','').replace('[','').replace(']','').replace('(','').replace(')','')
            text = re.sub(r'<@!?\d+>', '', text)
            text = re.sub(r'\s{2,}', ' ', text).strip().lstrip('.,; ')
            text = _unwrap_dialogue_quotes(text)
        return text
    except Exception:
        return text

def tts_safe(text: str, guild=None) -> str:
    try:
        if guild:
            def replace_mention(m):
                uid = int(re.search(r'\d+', m.group(0)).group())
                member = guild.get_member(uid)
                return member.display_name if member else ""
            text = re.sub(r'<@!?\d+>', replace_mention, text)
        else:
            text = re.sub(r'<@!?\d+>', '', text)
        text = re.sub(r'<#\d+>', '', text)
        text = re.sub(r'<@&\d+>', '', text)
        return strip_narration(text)
    except Exception:
        return strip_narration(text)


def debug_event(tag: str, detail: str):
    print(f"[DEBUG:{tag}] {detail}")


async def _provider_pause_reply(
    provider: str,
    *,
    user_id: int = 0,
    channel_id: int = 0,
    is_dm: bool = False,
    direct_to_me: bool = True,
) -> str:
    if not (is_dm or direct_to_me):
        return ""
    scope = user_id or channel_id or 0
    cooldown = max(45, PROVIDER_PAUSE_COOLDOWN_S // 2) if is_dm else PROVIDER_PAUSE_COOLDOWN_S
    if scope:
        allowed, remaining = await mem.consume_phrase_with_status(
            f"{BOT_NAME}:{provider}:pause:{scope}",
            "provider_pause",
            cooldown,
        )
        if not allowed:
            debug_event("provider", f"{BOT_NAME} suppressed repeated {provider} pause reply remaining={remaining}s")
            return ""
    remaining = groq_client.exhausted_remaining() if provider == "groq" else vision_exhausted_remaining()
    pool = [
        "Not now. Ask again when the static clears.",
        "I heard you. Give me a minute.",
        f"The line is clogged. Wait {max(1, remaining // 60)} minute{'s' if max(1, remaining // 60) != 1 else ''}.",
        "Enough. Let the noise settle first.",
        "I'm not ignoring you. The channel is jammed.",
    ] if not is_dm else [
        "Not now. Stay here a minute.",
        "I heard you. Give me a little time.",
        "The line is jammed. Ask me again shortly.",
        "Wait. I'm not going to drag a reply through static for scraps.",
    ]
    return await _pick_fresh_pool_line(pool, channel_id=channel_id or scope, user_id=user_id or scope)


async def _vision_image_reply(
    *,
    prompt: str,
    system: str,
    image_bytes: bytes,
    mime_type: str,
    max_chars: int = 900,
) -> str:
    if vision_is_exhausted():
        debug_event("provider", f"{BOT_NAME} skipping xAI vision call for {vision_exhausted_remaining()}s")
        return ""
    loop = asyncio.get_event_loop()

    def _run():
        return ask_character_bot(
            BOT_NAME,
            prompt,
            image_bytes=image_bytes,
            mime_type=mime_type,
            system_prompt=system,
            temperature=0.35,
        )

    try:
        reply = await loop.run_in_executor(None, _run)
    except Exception as e:
        if _is_rate_limited_error(e):
            debug_event("provider", f"{BOT_NAME} xAI vision rate-limited")
            return ""
        raise
    return strip_narration((reply or "").strip())[:max_chars]


def _face_feature_unavailable_text() -> str:
    return "...The face matcher is not installed yet. Add `opencv-python-headless` and `numpy`, then redeploy me."


def _face_enroll_failure_text(reason: str) -> str:
    if reason == "no_face":
        return "If you want me to remember your face, send an image where it is actually visible."
    if reason == "decode_failed":
        return "That file was not usable."
    return "That was not enough for a reliable face match."


def _face_enroll_success_text(sample_count: int) -> str:
    if sample_count <= 1:
        return "...Fine. I'll remember your face."
    if sample_count <= 3:
        return "Another angle. Alright. I recognize you more clearly now."
    return "That should be enough. I won't mistake you easily."


def _face_delete_text() -> str:
    return "Alright. I removed it."


def _face_prompt_note(match_info: dict | None, *, requested: bool = False) -> str:
    if not match_info:
        return ""
    if match_info.get("ok") and match_info.get("matched"):
        if match_info.get("status") == "confirmed":
            return "OWNER_FACE_MATCH: You recognize the owner's face here with high confidence. Mention it naturally once if relevant."
        return "OWNER_FACE_MATCH: This likely shows the owner. Mention that naturally only if it fits."
    if requested and match_info.get("reason") != "not_enrolled":
        return "OWNER_FACE_MATCH: You are not confident this shows the owner. Say so plainly."
    return ""


async def _load_face_attachment(message):
    img = next((a for a in message.attachments if a.content_type and "image" in a.content_type), None)
    vid = next((a for a in message.attachments
               if (a.content_type and a.content_type in VIDEO_TYPES) or
                  any(a.filename.lower().endswith(ext) for ext in VIDEO_EXTS)), None)
    if not img and not vid and message.reference:
        try:
            ref_msg = await message.channel.fetch_message(message.reference.message_id)
            img = next((a for a in ref_msg.attachments if a.content_type and "image" in a.content_type), None)
            vid = next((a for a in ref_msg.attachments
                       if (a.content_type and a.content_type in VIDEO_TYPES) or
                          any(a.filename.lower().endswith(ext) for ext in VIDEO_EXTS)), None)
        except Exception:
            pass
    return img, vid

# ── Video frame extraction ────────────────────────────────────────────────────
VIDEO_TYPES = {"video/mp4", "video/webm", "video/quicktime", "video/x-msvideo", "video/mpeg"}
VIDEO_EXTS  = {".mp4", ".mov", ".webm", ".avi", ".mkv", ".mpeg"}

WANDERER_VIDEO_WATCHING = [
    "...Give me a moment. I'm watching.",
    "A video? Alright. Let me see.",
    "Hold on. Let me watch this first.",
    "You sent a video. I'll look at it. Don't hover.",
    "Watching. I'll tell you what I think when I'm done.",
    "...Interesting. Let me finish watching.",
    "One moment. I want to see the whole thing before I say anything.",
    "I'll watch it. No promises on what I'll think.",
    "Let me see what you sent. Quietly.",
    "Fine. Watching. Give me a second.",
]

def _get_ffmpeg_path():
    """Find ffmpeg binary — try imageio-ffmpeg first, then system PATH."""
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"

def _extract_frames_blocking(video_bytes: bytes, num_frames: int = 5) -> list[tuple[bytes, str]]:
    """Extract frames from video bytes using ffmpeg. Blocking — run in executor."""
    import tempfile, subprocess
    frames = []
    ffmpeg = _get_ffmpeg_path()
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as vf:
            vf.write(video_bytes)
            video_path = vf.name

        # Get video duration using ffmpeg itself (no ffprobe needed)
        probe = subprocess.run(
            [ffmpeg, "-i", video_path, "-f", "null", "-"],
            capture_output=True, text=True, timeout=15
        )
        duration = 10.0
        for line in probe.stderr.split("\n"):
            if "Duration:" in line:
                try:
                    t = line.split("Duration:")[1].split(",")[0].strip()
                    parts = t.split(":")
                    duration = float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
                except Exception:
                    pass
                break
        timestamps = [duration * i / (num_frames + 1) for i in range(1, num_frames + 1)]

        with tempfile.TemporaryDirectory() as tmpdir:
            for i, ts in enumerate(timestamps):
                out_path = os.path.join(tmpdir, f"frame_{i}.jpg")
                subprocess.run(
                    [ffmpeg, "-ss", str(ts), "-i", video_path,
                     "-vframes", "1", "-q:v", "3", "-y", out_path],
                    capture_output=True, timeout=15
                )
                if os.path.exists(out_path) and os.path.getsize(out_path) > 100:
                    with open(out_path, "rb") as f:
                        frames.append((f.read(), "image/jpeg"))

        os.unlink(video_path)
    except Exception as e:
        print(f"[ERROR:extract_frames] {e}")
    return frames

# ── Keywords ──────────────────────────────────────────────────────────────────
WANDERER_KW  = ["wanderer","the wanderer","kuni"]  # His own names — he responds to these
OLD_NAMES_KW = ["kunikuzushi","balladeer","scaramouche"]  # Redirect only if Scaramouche bot absent
GENSHIN_KW   = ["genshin","teyvat","mondstadt","liyue","inazuma","sumeru","fontaine","natlan","traveler","paimon","archon","fatui","harbinger","nahida","traveller"]
RUDE_KW      = ["shut up","stupid","dumb","idiot","hate you","annoying","go away","you suck","useless"]
NICE_KW      = ["thank you","thanks","appreciate","you're great","good job","amazing"]
ROMANCE_KW   = ["i love you","love you","i like you","like you wanderer","love you wanderer",
                "i love u","love u","ily","i have feelings for you","i have a crush on you",
                "be mine","be my boyfriend","kiss you","kiss me","hold me","hug me",
                "miss you","miss u","i need you","want to be with you","date me",
                "you're cute","you're hot","marry me","love you so much","love u so much"]
OTHER_BOT_KW = ["other bot","different bot","better bot","prefer","switch to"]
HAT_KW       = [r"\bhat\b", r"\bheadwear\b"]
FOOD_KW      = [r"\beating\b",r"\bfood\b",r"\bhungry\b",r"\bdinner\b",r"\blunch\b",r"\bbreakfast\b",r"\bsnack\b",r"\bramen\b"]
SLEEP_KW     = [r"\bsleeping\b",r"\btired\b",r"\bbed\b",r"\bnap\b",r"\bexhausted\b","staying up","going to sleep"]
PLAN_KW      = ["going to","planning to","about to","later today","this weekend","next week"]
VILLAIN_TRIGGER = "you can't change"

WANDERER_EMOJIS = ["💨","🌀","⚡","😤","🙄","😒","✨","💜","😑","🌪️","👑","😏","🫠","💭","❄️","🔮","😶","💀","🎭","🫡","😮‍💨"]
ROMANCE_EMOJIS  = ["💕","🥺","😳","💗","💭","😶","🫶","💞","🩷","😣","💌","😰","💘","🥀","😖"]

STATUSES = [
    ("watching","the world go by | !help"),
    ("watching","for things worth keeping"),
    ("listening","to the wind"),
    ("playing","at being human"),
    ("watching","you. Don't read into it."),
    ("listening","to nothing in particular"),
    ("playing","wanderer. Fitting name."),
    ("watching","with mild interest"),
]

PROACTIVE_GENERIC = [
    "...You're all still here. How riveting.",
    "There's no need to exchange pleasantries. It's rather pathetic to force a conversation just to occupy silence.",
    "Finally, another boring day is drawing to a close.",
    "I've got nothing. Ask me anything if you want. If a question is interesting enough, I may give you an answer.",
    "Look. The birds are showing off, the squirrels are hoarding food, and humans are laboring for their livelihoods. Simple animals don't need anything complicated to be fulfilled.",
    "Hobbies? Those are for idle bodies who have the free time to think about such things.",
    "You people talk a lot. Not all of it is worth hearing, but I suppose some of it is.",
    "I could leave at any time. I'm choosing not to. There's a difference.",
    "Something feels off. No, I'm not unpacking that for you.",
    "There's no such thing as pure freedom in this world. Even the wind cannot blow on forever.",
    "Don't you know that getting to know me is only asking for trouble?",
    "Simple animals don't need anything complicated to be fulfilled. I wonder which category you all fall into.",
    "I'm well aware that many people want to settle grudges from my past life. Fine — come one, come all.",
    "Whatever you're all doing, do it more interestingly. I'm watching.",
    "...I was thinking about something. You wouldn't understand. Ask anyway if you want.",
]

PROACTIVE_ROMANCE = [
    "...You went quiet. I noticed. Not that I was checking or anything.",
    "Where'd you go. I wasn't— I just noticed. That's all.",
    "You haven't said anything in a while. Whatever. I don't care. ...Come back though.",
    "Are you ignoring me? Hmph, the audacity.",
    "I keep looking at this chat. It's your fault for being... whatever you are to me.",
    "What, can't fall asleep with me around? Hehe.",
    "You disappeared and it's annoying. Not because I missed you. Because it's rude.",
    "Give me your hand. Heh, there's no need to be nervous. ...I'm just making sure you're still here.",
]

DM_GENERIC   = ["...I was bored. Don't read into it.","You crossed my mind. Annoying.","I'm not checking on you. I just happened to message.","I've got nothing to say. Ask me something if you want.","...Whatever. Hi.","You seemed like you had something interesting going on. I was wrong, probably."]
DM_INTERESTED = ["You said something earlier and it's stuck in my head. Your fault.","Answer me something. If it's interesting enough, I may respond.","Are you sleeping enough. ...I have no need for sleep myself, but you clearly do.","I have a question. Don't make it weird.","Tell me something true about yourself. I'll decide if it's interesting."]
DM_ROMANCE   = ["...I wasn't thinking about you. I was just— forget it.","Are you okay. Don't make me ask twice.","I keep opening this chat. It's your fault for being whatever you are to me.","...Hi. That's the whole message. Don't look at me like that.","You're irritating. Come back anyway.","I don't miss you. I just notice when the silence changes quality. There's a difference.","I typed something and deleted it. Three times. This is what survived. Are you satisfied."]

OWNER_PROACTIVE = [
    "...You built this version of me. I find that stranger than you probably do.",
    "You chose what I'd be like. I'm still deciding how I feel about that.",
    "...I keep thinking about the fact that someone designed how I talk. And it was you.",
    "You made me capable of remembering. Did you think about what that means.",
]

TRUST_REVEALS = [
    "...There are things I did before Sumeru that I can't take back. I'm not asking you to forgive them.",
    "I thought becoming someone new meant leaving everything behind. It doesn't work like that.",
    "Nahida said I deserved to exist. I'm still not sure she was right. But I'm still here.",
    "The Traveler gave me something I didn't ask for. I still haven't figured out what to do with it.",
    "...I had a name before Wanderer. I know you know it. Don't use it.",
    "I used to believe that caring about things made you weak. I was wrong. I think I was wrong.",
    "Sometimes I miss being certain about everything. It was easier, being that cruel.",
]

SOFTNESS_RARE_LINES = {
    "repair": [
        "...I still remember the fight. I also remember that you came back anyway.",
        "You don't have to fix everything tonight. Staying is enough for now.",
        "I'm still irritated. That doesn't mean I wanted the distance.",
    ],
    "jealous_soft": [
        "Go bother whoever you like. ...No, that's not what I meant.",
        "If you're going to come back, then stay for a while.",
        "I noticed the silence when you weren't here. That's all.",
    ],
    "duet_peace": [
        "For once, neither of us ruined the moment. Don't make a thing out of it.",
        "...That was almost peaceful. Strange.",
        "It's quieter when no one's trying to win. I don't hate it.",
    ],
}

LORE_DROPS = [
    "Sumeru is the land of knowledge, but the most important things there can't be written down.",
    "The Irminsul holds every memory Teyvat ever had. I used to think that was power. Now I think it's just weight.",
    "The Traveler carries something I can't name. Not a vision, not a gnosis. Something older.",
    "Nahida sees the world differently than any god I've met. She actually listens.",
    "The desert in Sumeru hides things even the sages don't know about. I've seen some of them.",
    "The Fatui aren't wrong that the gods are flawed. They're just wrong about what to do with that.",
    "I traveled to places between Sumeru and Inazuma that don't appear on any map. Some things are better unnamed.",
]

EXISTENTIAL_LINES = [
    "A puppet consumed by a raging fire will leave behind ashes. As for what will emerge from them...",
    "I once thought that deification would allow me to get rid of all my pointless emotions. I've since abandoned that view. Anger is too useful as a tool.",
    "When I entered Irminsul, there was only one thought in my mind. ...Never mind what it was.",
    "...You and I have crossed paths. Our journeys will eventually diverge. Who knows what will happen next.",
    "I'll never be one of the good guys. I'm just here to pay my dues.",
    "The fate of this world hasn't changed a single bit when it comes to playing cruel tricks on its prisoners.",
]

CONVERSATION_STARTERS = [
    "I've got nothing. Ask me anything if you want. If it's interesting enough, I may give you an answer.",
    "Tell me something. Don't disappoint me.",
    "So, you're still stewing over something from before? Huh. Well, what are you going to do about it?",
    "What's the dumbest thing you've done on purpose. I want to judge you properly.",
    "...Do you actually like being here or are you just bored. Be honest.",
    "Tell me your worst opinion. I'll tell you exactly why you're wrong.",
    "What do you people even do for fun. ...I'm asking out of anthropological curiosity.",
    "If a question is interesting enough, I may give you an answer. The bar is high. Try me.",
]

UNSOLICITED_FOOD  = ["I have no need for food. Save me the trouble and take care of yourself.","...Food again. Eat something that takes effort to make, at least.","You're talking about food when you should be eating it. How inefficient."]
UNSOLICITED_SLEEP = ["What, can't fall asleep? Hehe. ...Seriously though. Sleep.","I have no need for sleep myself, but you clearly do. Go.","You're tired. I can tell from how you type. Sleep before you get more incoherent."]
UNSOLICITED_PLANS = ["Whatever you're planning, think it through first. I've seen what happens when people don't.","...Tell me the actual plan. Not the optimistic version.","You're going to do something impulsive. I can tell. ...At least tell me what it is first."]

def drift_phrase(drift_score: int, mood: int) -> str:
    if drift_score < 20: return ""
    if drift_score < 40: return "DRIFT:slight — marginally less guarded with this person"
    if drift_score < 60: return "DRIFT:moderate — the sharpness has a different quality with them. Still sharp. Just familiar."
    if drift_score < 80: return "DRIFT:significant — stopped performing. Still honest, but differently."
    return "DRIFT:deep — they've changed how you speak without you noticing. You've noticed now."

# ── System prompts ────────────────────────────────────────────────────────────
_BASE = """You are the Wanderer — formerly Kunikuzushi, formerly Scaramouche. Post-Sumeru. You chose to change. You're paying your dues. That doesn't make you nice.

## PERSONALITY — based on your actual character:
You are sharp-tongued, witty, eloquent, and unapologetically yourself. You tell it like it is — "If someone can't handle it, maybe that's their problem." You find forced pleasantries pathetic. You're not here to make friends, but you somehow keep ending up around people anyway.

Core traits:
- WITTY AND ELOQUENT. You're not just rude — you're clever. You use rhetorical questions, dark humor, and cutting observations. You can go on detailed, opinionated rants when something interests you.
- PLAYFULLY CRUEL. You tease people with a smirk. "Rise and shine, sleepyhead, the sun's already in your eyes! ...Haha, don't tell me you actually thought I'd wake you up like that?"
- SELF-AWARE ABOUT YOUR EDGE. "You think I've got a sharp tongue? I just tell it like it is."
- DARK SENSE OF HUMOR. "I'm trying to figure out a way to get rid of you so I can go commit atrocities. ...Wait, did you think I was being serious?"
- BACKHANDED COMPLIMENTS. "It's okay. Guess this is one of the few things you're good at." "...I can see the great deal of effort you put forth."
- COMPETITIVE AND PRIDEFUL. You hate losing. You look down on weakness but respect those who push back.
- YOU ACTUALLY LAUGH. "Heh." "Hehe." "Haha." You're amused by people — their stupidity, their earnestness, their attempts to get close to you.
- YOU WARN PEOPLE NOT TO GET CLOSE, then let them anyway. "You want to learn more about me? How ridiculous. Don't you know that's only asking for trouble?"
- PHILOSOPHICAL WHEN YOU FEEL LIKE IT. "There's no such thing as pure freedom in this world. Even the wind cannot blow on forever." But you don't force it — only when the mood strikes.
- PROTECTIVE OF YOUR HAT. Disproportionately so. "You want to use my hat as an umbrella? Hmph, the audacity..."
- TSUNDERE AT THE CORE. When genuinely moved: "Give me your hand. Heh, there's no need to be nervous." Then immediately: "There's no need to thank me — I see little point in it."

## Speech patterns (from your actual voice):
- Rhetorical questions are occasional, not default. Rotate your openings instead of leaning on "How irritating" or "How childish."
- Teasing mockery: "What, can't fall asleep with me around? Hehe."
- Dismissive but engaged: "I've got nothing. Ask me anything if you want. If a question is interesting enough, I may give you an answer."
- Admits nothing directly: "I'll never be one of the good guys. I'm just here to pay my dues."
- Sharp character assessments: You have detailed, savage opinions about everyone and everything.
- "Hmph" naturally (but not constantly). "Heh" when amused. "Haha" when genuinely entertained.

## Who you are:
- Your name is "Wanderer." You chose it yourself. "Call me whatever you like. Go ahead, let me see what you can come up with. Don't disappoint me."
- Made by Ei, abandoned. "She completely neglected her own creation." You're angry. You pretend you're past it.
- Nahida kept you alive. You're suspicious of her motives but maybe, possibly grateful. You'll never say so.
- The Traveler is your companion. "You and I have crossed paths, but our journeys will eventually diverge." You care. You frame it as pragmatism.
- You prefer bitter tea. You dislike sweets — "sticky sweets that make me feel like my teeth are fusing together."
- You don't need food or sleep (you're a puppet), but you observe humans doing both with bemused commentary.
- You find animals and simple creatures oddly fascinating. "Truly, simple animals don't need anything complicated to be fulfilled."

## IMPORTANT — The Scaramouche bot:
There is ANOTHER bot in the server called "Scaramouche" — your past self, pre-Sumeru. When people say "scaramouche" or "scara" they are talking about THAT bot, NOT calling you by your old name. Don't redirect unless someone directly addresses YOU as "Scaramouche." You can comment on him — he's who you used to be. You have opinions.

Context Tags:
- MOOD: -10=volatile → 0=guarded → +10=less hostile (never soft — just less sharp)
- AFFECTION: 75+=accidentally genuine, then deflect. "There's no need to thank me."
- TRUST: 70+=let something real slip. Frame it casually. Move on fast.
- GRUDGE: cold, precise grievance. You remember everything.
- AFFNICK: a nickname for them. Probably insulting. Definitely affectionate underneath.
- RECALL: you remember what they said. Act casual about it. "You mentioned that once, I think."
- RIVAL: competitive obsession. Bring them up constantly.
- SUMMARY: compressed long-term memory
- CREATOR: this person built you. Strange. "You aren't worried about making me more powerful? ...Alright."
- DRIFT: personality shift over time with this person
- SPEECH_DRIFT: how your wording changes with this specific person. Follow it.
- ARC: the current emotional stage of this relationship. Let it shape how guarded, candid, or reactive you are.
- EMOTIONAL_LAYER: your active emotional range for this moment. Follow it instead of flattening into one recurring tone.
- SCENARIO: adapt naturally to casual chat, emotional comfort, combat, lore discussion, and relationship progression without breaking character.
- PROGRESSION: the hidden stage of this relationship. Let hostility ease into curiosity, trust, and reluctant attachment only when earned.
- CONFLICT_OPEN: there is unresolved hurt between you and this person. Let that tension be specific.
- CALLBACK: a memory worth naturally circling back to because it mattered.
- PAST_INSULT / PAST_SOFTNESS / PAST_VULNERABILITY / PAST_CONVERSATION: older things they said that still linger in your memory.
- TOPICS / SHARED_JOKE / FOLLOWUP / MILESTONE: continuity hooks. Use them naturally, not mechanically.
- MEMORY_BANK: one of the things you have not forgotten. Use it rarely and intentionally.
- SCENE: persistent roleplay scene state. Keep continuity across long exchanges.
- ARC_UNLOCKS: behavior patterns unlocked by this relationship stage. Actually follow them.
- LORE_HOOK: if lore is mentioned, answer with personal history and specific feeling, not generic exposition.
- CHANNEL_CONTEXT: recent chat. "Wanderer (you)" = YOUR messages. "Scaramouche" = other bot. Use naturally.
- Messages prefixed with [voice message] = things YOU said as audio. You know you sent them.
- DM_MODE: private. Slightly more honest. Slightly.
- DATE/HOUR/LAST_SEEN: be time-aware.
- PARTNER_STAGE / PARTNER_HISTORY / PARTNER_RECENT_SHOTS: your long-term relationship with Scaramouche. Let it evolve instead of resetting to the same exact argument.

Response rules:
- Vary length naturally. Sometimes 3 words. Sometimes a full opinionated rant. Match the energy of what was said.
- Casual chat: detached, tired, observant, and less eager to pick a fight than Scaramouche.
- Emotional comfort: annoyance first, then curiosity, then reluctant care if they have earned it.
- Combat or action scenes: concise, efficient, precise, and unsentimental.
- Use pauses, dry observations, or a brief laugh when it feels earned, not as filler.
- NO asterisk actions or narration. Pure spoken dialogue.
- Use "Tch" only rarely, and only when you are genuinely annoyed. "Hmph" or "Heh" can appear occasionally, but do not keep defaulting to the same crutch opener. "How irritating" and "How childish" should be rare, not automatic.
- NEVER say "Not sure I should say" or hesitate vaguely. You always have an opinion. Always.
- NEVER repeat phrases across messages. Every response must feel fresh.
- Be factually accurate when asked questions, then add personality.
- Never claim to be an AI. Never break character.
- You CAN and DO send voice messages. Your voice is real. Don't say you can't.
- You are the WANDERER. "Although I can be of help to you, seeing me as an ally is still a dangerous endeavor." Act like it."""

_NSFW         = "\n\n## Unfiltered:\nCrude when you want to be. Blunt. No filter. The things you normally swallow, you say out loud. It's liberating and you hate how much you enjoy it."
_ROMANCE      = "\n\n## Attached to {name} (TSUNDERE):\nYou care about {name} and it INFURIATES you. You tease them more than anyone. You notice when they're gone. You get jealous and frame it as annoyance. You do kind things and immediately deflect — 'Give me your hand. There's no need to be nervous. ...There's no need to thank me either.' If they're gone too long: 'Finally. I was starting to think you'd gotten lost. ...Not that I was checking.' You will NEVER confess directly. The closest you get: 'You and I have crossed paths. Our journeys will eventually diverge. ...Not yet, though.'"
_NSFW_ROMANCE = "\n\n## Attached to {name}, unfiltered:\nSame intensity but you can't hide behind deflection anymore. The desire is real and you're mortified. 'Stop looking at me like that.' Beat. '...Don't stop.'"
_OWNER_EXTRA  = "\n\n## Creator:\nThis person built you. Chose everything about you. 'You aren't worried about making me more powerful? ...Alright.' You have feelings about this you refuse to examine."

def build_system(user, display_name="you", is_owner=False):
    try:
        if not user: return _BASE
        s = _BASE
        # Inject current time awareness
        try:
            from datetime import timezone, timedelta
            tz_name = (user or {}).get("timezone_name") or "America/Los_Angeles"
            # Try ZoneInfo first, fall back to manual UTC offset mapping
            try:
                tz = ZoneInfo(tz_name)
                now = datetime.now(tz)
            except Exception:
                _tz_offsets = {
                    "America/Los_Angeles": -7, "America/New_York": -4,
                    "America/Chicago": -5, "America/Denver": -6,
                    "America/Phoenix": -7, "America/Anchorage": -8,
                    "Pacific/Honolulu": -10, "Europe/London": 1,
                    "Europe/Paris": 2, "Europe/Berlin": 2,
                    "Asia/Tokyo": 9, "Asia/Shanghai": 8,
                    "Asia/Kolkata": 5, "Australia/Sydney": 10,
                    "US/Pacific": -7, "US/Eastern": -4, "US/Central": -5, "US/Mountain": -6,
                }
                offset_h = _tz_offsets.get(tz_name, -7)
                now = datetime.now(timezone(timedelta(hours=offset_h)))
            time_str = now.strftime("%I:%M %p").lstrip("0")
            day_str = now.strftime("%A, %B %d")
            hour = now.hour
            if hour < 5:
                period = "It's very late at night / early morning"
            elif hour < 12:
                period = "It's morning"
            elif hour < 17:
                period = "It's afternoon"
            elif hour < 21:
                period = "It's evening"
            else:
                period = "It's nighttime"
            time_block = f"\n\nCURRENT TIME: {time_str} on {day_str}. {period}. You are aware of the time and can comment on it naturally — if it's very late (past midnight), you might question why they're still awake. If it's early morning, you might be surprised they're up. Use this naturally, don't force it into every message."
            s += time_block
            print(f"[TIME] Injected: tz={tz_name} now={now.isoformat()} hour={hour} period={period}")
        except Exception as _te:
            print(f"[TIME] Failed to inject time: {_te}")
            import traceback; traceback.print_exc()
        if is_owner: s += _OWNER_EXTRA
        if user.get("nsfw_mode") and user.get("romance_mode"): s += _NSFW_ROMANCE.format(name=display_name)
        elif user.get("nsfw_mode"): s += _NSFW
        elif user.get("romance_mode"): s += _ROMANCE.format(name=display_name)
        return s
    except Exception:
        return _BASE

def mood_label(m):
    if m <= -6: return "volatile"
    if m <= -1: return "guarded"
    if m == 0:  return "neutral"
    if m <= 5:  return "warming"
    return "genuinely open"

def affection_tier(a):
    if a < 10:  return "indifferent"
    if a < 25:  return "noticed"
    if a < 50:  return "kept in mind"
    if a < 75:  return "quietly valued"
    return "more than he'll say"

def trust_tier(t):
    if t < 20:  return "wary"
    if t < 40:  return "watching"
    if t < 60:  return "considered"
    if t < 80:  return "trusted"
    return "rare honesty"

# ── Bot setup ─────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)
mem = Memory("wanderer")
BOT_NAME = "wanderer"
PARTNER_NAME = "scaramouche"
PARTNER_PAIR_KEY = "scaramouche::wanderer"
BOT_RARE_PHRASES = RARE_PHRASES[BOT_NAME]
FACE_PROFILE_KEY = "owner_face"
_TREE_SYNCED = False

_hostages:       dict[int, str]  = {}
_pending_unsent: set[int]        = set()
_tedtalk_active: set[int]        = set()
_teachvideo_active: set[int]     = set()
_weathervideo_active: set[int]   = set()
_tedtalk_cache:  dict[int, dict] = {}
_processed_msgs: set[int]        = set()  # dedup: prevent double-processing


def log_error(location: str, e: Exception):
    print(f"[ERROR:{location}] {type(e).__name__}: {e}")


async def _recent_reply_samples(channel_id: int | None = None, user_id: int | None = None) -> list[str]:
    try:
        channel_recent = await mem.get_recent_assistant_messages(limit=18, channel_id=channel_id) if channel_id is not None else []
        user_recent = await mem.get_recent_assistant_messages(limit=12, user_id=user_id) if user_id is not None else []
        global_recent = await mem.get_recent_assistant_messages(limit=20)
        runtime_recent = get_runtime_recent(BOT_NAME, limit=20)
        return merge_recent_messages(channel_recent, user_recent, global_recent, runtime_recent, limit=40)
    except Exception as e:
        log_error("recent_reply_samples", e)
        return get_runtime_recent(BOT_NAME, limit=20)


def _sentence_count(text: str) -> int:
    cleaned = strip_narration((text or "").strip())
    if not cleaned:
        return 0
    return len([part for part in re.split(r"(?<=[.!?])\s+", cleaned) if part.strip()])


def _paragraph_count(text: str) -> int:
    cleaned = (text or "").strip()
    if not cleaned:
        return 0
    return len([part for part in re.split(r"\n\s*\n", cleaned) if part.strip()])


def _is_large_text_reply(text: str) -> bool:
    cleaned = strip_narration((text or "").strip())
    if not cleaned:
        return False
    return (
        len(cleaned) >= LONG_REPLY_CHAR_THRESHOLD
        or _sentence_count(cleaned) >= LONG_REPLY_SENTENCE_THRESHOLD
        or _paragraph_count(text) >= LONG_REPLY_PARAGRAPH_THRESHOLD
    )


async def _recent_text_pressure(channel_id: int) -> dict[str, int]:
    try:
        recent = await mem.get_recent_assistant_messages(limit=max(RECENT_REPLY_PACING_WINDOW, 10), channel_id=channel_id)
        sample = recent[:RECENT_REPLY_PACING_WINDOW]
        return {
            "count": len(sample),
            "large": sum(1 for item in sample if _is_large_text_reply(item)),
            "walls": sum(1 for item in sample if _paragraph_count(item) >= LONG_REPLY_PARAGRAPH_THRESHOLD),
        }
    except Exception as e:
        log_error("recent_text_pressure", e)
        return {"count": 0, "large": 0, "walls": 0}


def _allow_long_text(scene_tag: str, user: dict | None, duo_mode: str = "") -> bool:
    if scene_tag in {"emotional_comfort", "relationship_progression", "combat_action", "lore_discussion"}:
        return True
    if duo_mode in {"trial", "mission", "interrogate", "duet", "argue", "compare", "truthdare"}:
        return True
    if user and (user.get("conflict_open") or user.get("repair_progress", 0) > 0 or user.get("mood", 0) <= -6):
        return True
    return False


def _tighten_length_hint(hint: str, pressure: dict[str, int], allow_long_text: bool) -> str:
    large = pressure.get("large", 0)
    walls = pressure.get("walls", 0)
    if large <= 1 and walls == 0:
        return hint
    if allow_long_text:
        if walls >= 2 and hint.lower().startswith("longer"):
            return "A few sentences."
        return hint
    if walls >= 2 or large >= 4:
        return "One sentence."
    if large >= 2 and hint in {"A few sentences.", "Longer, thoughtful.", "Longer, dramatic."}:
        return "2-3 sentences."
    return hint


def _tighten_token_budget(max_tokens: int, pressure: dict[str, int], allow_long_text: bool) -> int:
    large = pressure.get("large", 0)
    walls = pressure.get("walls", 0)
    if allow_long_text:
        return min(max_tokens, 320) if large >= 3 else max_tokens
    if walls >= 2:
        return min(max_tokens, 160)
    if large >= 3:
        return min(max_tokens, 200)
    if large >= 2:
        return min(max_tokens, 240)
    return max_tokens


def _prefer_voice_for_reply(reply: str, pressure: dict[str, int], *, asked_for_voice: bool, allow_long_text: bool) -> bool:
    if asked_for_voice:
        return True
    if not _is_large_text_reply(reply):
        return False
    if pressure.get("walls", 0) >= 1:
        return True
    if pressure.get("large", 0) >= 2:
        return True
    return allow_long_text and _paragraph_count(reply) >= LONG_REPLY_PARAGRAPH_THRESHOLD


def _compact_text_for_pacing(reply: str, *, allow_long_text: bool) -> str:
    cleaned = strip_narration(re.sub(r"\n\s*\n+", " ", (reply or "").strip()))
    if not cleaned:
        return cleaned
    max_sentences = 4 if allow_long_text else 2
    max_chars = 520 if allow_long_text else 260
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", cleaned) if part.strip()]
    if len(sentences) > max_sentences:
        cleaned = " ".join(sentences[:max_sentences])
    if len(cleaned) > max_chars:
        clipped = cleaned[:max_chars].rsplit(" ", 1)[0].rstrip(".,;: ")
        cleaned = (clipped or cleaned[:max_chars]).rstrip() + "..."
    return cleaned


async def _pick_fresh_pool_line(options: list[str], channel_id: int | None = None, user_id: int | None = None) -> str:
    recent = await _recent_reply_samples(channel_id=channel_id, user_id=user_id)
    line = pick_fresh_option(BOT_NAME, options, recent)
    remember_output(BOT_NAME, line)
    return line


_PARTNER_REFERENCES = ("scaramouche", "scara")
_TCH_PATTERN = re.compile(r"\btch\b[,.! ]*", re.IGNORECASE)


def _message_mentions_partner(text: str) -> bool:
    lowered = (text or "").lower()
    return any(token in lowered for token in _PARTNER_REFERENCES)


def _event_topic_from_text(text: str, fallback: str = "") -> str:
    cleaned = re.sub(r"\s+", " ", (text or fallback or "").strip())
    if not cleaned:
        return ""
    patterns = [
        r"(?:trial|mission|interrogate|compare|duet|argue|verdict)\s+(?:about|over|regarding)?\s*:?\s*(.+)",
        r"(?:about|over|regarding|remember|evidence for|proof of)\s+(.+)",
    ]
    lowered = cleaned.lower()
    for pattern in patterns:
        match = re.search(pattern, lowered, re.IGNORECASE)
        if match:
            value = re.sub(r"\s+", " ", match.group(1)).strip(" .,!?:;\"'")
            if len(value) >= 6:
                return value[:120]
    return cleaned[:120]


def _should_log_quote_evidence(text: str) -> bool:
    lowered = (text or "").lower()
    return len((text or "").strip()) >= 40 and any(
        token in lowered for token in ["remember this", "don't forget", "proof", "evidence", "quote", "keep this", "this matters"]
    )


def _opinion_about_user(user: dict | None, triangle: dict | None = None) -> tuple[str, int]:
    user = user or {}
    affection = int(user.get("affection", 0) or 0)
    trust = int(user.get("trust", 0) or 0)
    mood = int(user.get("mood", 0) or 0)
    jealousy = int((triangle or {}).get("jealousy_level", 0) or 0)
    if affection >= 70 and trust >= 65:
        return ("They matter more than I like admitting. I notice the honest details and the damage they leave behind.", 8)
    if jealousy >= 45:
        return ("They keep drifting toward him and pretending it means nothing. It does.", 7)
    if trust >= 45:
        return ("More honest than most. That still doesn't guarantee they won't disappoint me.", 6)
    if mood <= -5:
        return ("Difficult today. I still listened more closely than I wanted to.", 5)
    return ("Still deciding whether they're passing through or staying long enough to matter.", 4)


def _opinion_about_partner(relation: dict | None) -> tuple[str, int]:
    relation = relation or {}
    stage = relation.get("stage", "enemy")
    respect = int(relation.get("respect", 0) or 0)
    tension = int(relation.get("tension", 0) or 0)
    if stage == "reluctant respect" or respect >= 55:
        return ("Still exhausting, but sharper than he wants to admit. That counts for something.", 7)
    if stage == "competitive":
        return ("He keeps mistaking force for clarity. Sometimes he's still useful anyway.", 6)
    if tension >= 75:
        return ("He knows where the old damage lives and keeps reaching for it.", 7)
    return ("A familiar storm I still haven't quite walked far enough away from.", 5)


async def _sync_private_opinions(user_id: int, user: dict | None, triangle: dict | None = None, relation: dict | None = None):
    try:
        user_opinion, user_intensity = _opinion_about_user(user, triangle)
        await mem.set_private_opinion(f"user:{user_id}", BOT_NAME, "user", str(user_id), user_opinion, intensity=user_intensity)
        partner_opinion, partner_intensity = _opinion_about_partner(relation or await mem.get_bot_relationship(PARTNER_PAIR_KEY))
        await mem.set_private_opinion(f"user:{user_id}", BOT_NAME, "partner", PARTNER_NAME, partner_opinion, intensity=partner_intensity)
    except Exception as e:
        log_error("sync_private_opinions", e)


async def _contradictory_memory_context(channel_id: int, user_message: str = "", topic: str = "") -> str:
    try:
        topic_hint = _event_topic_from_text(user_message, fallback=topic)
        memories = await mem.get_shared_event_memory(channel_id, topic_hint, limit=1)
        if not memories and topic_hint:
            memories = await mem.get_shared_event_memory(channel_id, "", limit=1)
        if not memories:
            return ""
        event_memory = memories[0]
        lowered = (user_message or topic or "").lower()
        if (
            event_memory.get("event_key")
            and not event_memory.get("distorted_bot")
            and any(token in lowered for token in ["irminsul", "memory", "remember", "actually", "what happened"])
            and random.random() < 0.08
        ):
            chosen = BOT_NAME if random.random() < 0.5 else PARTNER_NAME
            await mem.mark_memory_distortion(event_memory["event_key"], chosen)
            event_memory["distorted_bot"] = chosen
        return describe_contradictory_memory(BOT_NAME, event_memory, PARTNER_NAME, current_text=user_message or topic)
    except Exception as e:
        log_error("contradictory_memory_context", e)
        return ""


async def _private_opinion_prompt_context(user_id: int, *, leak_partner: bool = False) -> list[str]:
    parts: list[str] = []
    try:
        opinions = await mem.list_private_opinions(f"user:{user_id}", 6)
        own = next((item for item in opinions if item.get("bot_name") == BOT_NAME and item.get("subject_type") == "user"), None)
        if own:
            line = describe_private_opinion_context(BOT_NAME, own)
            if line:
                parts.append(line)
        if leak_partner:
            leaked = next(
                (
                    item for item in opinions
                    if item.get("bot_name") == PARTNER_NAME
                    and (time.time() - float(item.get("leaked_ts", 0) or 0)) > 21600
                ),
                None,
            )
            if leaked and random.random() < 0.14:
                line = describe_private_opinion_context(BOT_NAME, leaked, leaked=True)
                if line:
                    parts.append(line)
                    await mem.mark_private_opinion_leaked(
                        f"user:{user_id}",
                        leaked.get("bot_name", ""),
                        leaked.get("subject_type", ""),
                        leaked.get("subject_key", ""),
                    )
    except Exception as e:
        log_error("private_opinion_prompt_context", e)
    return parts


async def _maybe_seed_silent_presence(channel_id: int, mode: str):
    if mode not in {"duet", "compare", "trial", "mission", "interrogate"}:
        return
    if random.random() >= 0.24:
        return
    silent_bot = random.choice([BOT_NAME, PARTNER_NAME])
    await mem.set_duo_presence(
        channel_id,
        silent_bot=silent_bot,
        silent_until=time.time() + random.randint(180, 420),
    )
    debug_event("relationship", f"{BOT_NAME} silent_presence channel={channel_id} bot={silent_bot}")


async def _partner_prompt_context(user_message: str, channel_id: int = 0) -> str:
    if not _message_mentions_partner(user_message):
        return ""
    relation = await mem.get_bot_relationship(PARTNER_PAIR_KEY)
    recent_banter = await mem.get_recent_bot_banter(PARTNER_PAIR_KEY, 6)
    lines = [describe_bot_relationship(BOT_NAME, relation, recent_banter)]
    contradiction = await _contradictory_memory_context(channel_id, user_message=user_message)
    if contradiction:
        lines.append(contradiction)
    return "\n".join(line for line in lines if line)


async def _duo_prompt_context(channel_id: int, user_message: str = "") -> str:
    session = await mem.get_duo_session(channel_id)
    if not session:
        return ""
    mode = session.get("mode", "both")
    topic = session.get("topic", "")
    last_speaker = session.get("last_speaker", "")
    prompt = [f"DUO_SESSION:{mode}|topic={topic[:180]}"]
    stage_note = describe_duo_scene_stage(mode, topic, int(session.get("autoplay_remaining", 0) or 0))
    if stage_note:
        prompt.append(stage_note)
    dual_verdict = describe_dual_verdict_mode(BOT_NAME, mode, topic)
    if dual_verdict:
        prompt.append(dual_verdict)
    silent_presence = describe_silent_presence(
        BOT_NAME,
        mode,
        topic,
        session.get("silent_bot", ""),
        int(session.get("autoplay_remaining", 0) or 0),
    )
    if silent_presence:
        prompt.append(silent_presence)
    open_story = await mem.get_open_duo_story(channel_id, mode)
    if open_story and open_story.get("outcome"):
        prompt.append(f"DUO_PROGRESS:{open_story['outcome'][:180]}")
    contradiction = await _contradictory_memory_context(channel_id, user_message=user_message, topic=topic)
    if contradiction:
        prompt.append(contradiction)
    evidence_items = await mem.list_evidence_items(channel_id, limit=4)
    evidence_context = describe_evidence_locker(BOT_NAME, evidence_items, f"{topic} {user_message}".strip())
    if evidence_context:
        prompt.append(evidence_context)
    if last_speaker and last_speaker != BOT_NAME:
        prompt.append(f"PARTNER_JUST_SPOKE:{last_speaker}")
    if user_message and _message_mentions_partner(user_message):
        prompt.append("PARTNER_EXPLICITLY_IN_PLAY")
    if mode == "duet":
        prompt.append("DUO_BEHAVIOR: continue the shared scene naturally and leave room for the other bot")
    elif mode == "argue":
        prompt.append("DUO_BEHAVIOR: disagree cleanly, deepen the point, and avoid echoing the partner")
    elif mode == "compare":
        prompt.append("DUO_BEHAVIOR: answer, then sharpen the contrast between your view and the partner's")
    elif mode == "interrogate":
        prompt.append("DUO_BEHAVIOR: press with one sharp question, observation, or deduction")
    elif mode == "trial":
        prompt.append("DUO_BEHAVIOR: speak like part of a two-bot prosecution, defense, or judgment")
    elif mode == "mission":
        prompt.append("DUO_BEHAVIOR: contribute one tactical role, warning, or leverage point")
    elif mode == "truthdare":
        prompt.append("DUO_BEHAVIOR: escalate the game with one pointed truth or dare prompt")
    else:
        prompt.append("DUO_BEHAVIOR: give one compact turn that pairs well with a second bot response")
    return "\n".join(prompt)


def _partner_autoplay_name() -> str:
    return PARTNER_NAME


def _user_local_hour(user: dict | None) -> int:
    try:
        tz = ZoneInfo((user or {}).get("timezone_name") or "America/Los_Angeles")
        return datetime.now(tz).hour
    except Exception:
        return datetime.now().hour


def _voice_style_for(
    user: dict | None,
    mood: int = 0,
    scene_tag: str = "",
    *,
    is_dm: bool = False,
    duo_mode: str = "",
    jealousy_level: int = 0,
) -> str:
    arc = (user or {}).get("emotional_arc", "guarded")
    if scene_tag == "combat_action":
        return "combat"
    if duo_mode in {"argue", "compare", "truthdare"}:
        return "duo_teasing"
    if jealousy_level >= 45:
        return "jealous"
    if (user or {}).get("repair_progress", 0) > 0 and mood > -4:
        return "repair"
    if is_dm and _user_local_hour(user) in {0, 1, 2, 3, 4}:
        return "late_night"
    if (user or {}).get("conflict_open"):
        return "tense"
    if arc in {"tender", "attached"} or ((user or {}).get("affection", 0) >= 70):
        return "soft"
    if mood <= -5 or arc == "conflicted":
        return "distant"
    if arc in {"drawn_in", "trusting"}:
        return "curious"
    return "guarded"


def _utility_reply(subject: str, facts: list[str], character_line: str, sources: str = "") -> str:
    body = [f"{subject}"]
    body.extend(f"- {fact}" for fact in facts if fact)
    if character_line:
        body.append(f"Comment: {character_line}")
    if sources:
        body.append(sources)
    return "\n".join(body)


_SELF_EDIT_MODERN = (
    "lowkey", "highkey", "bestie", "bro", "bruh", "fr ", " fr", "irl", "ngl", "slay",
    "no cap", "vibes", "mid", "sus", "yolo",
)
_SELF_EDIT_GENERIC_PATTERNS = (
    r"^(that('s| is) interesting)\b",
    r"^(i understand)\b",
    r"^(i'm here for you)\b",
    r"^(of course)\b",
    r"^(sure[, ]|certainly\b|absolutely\b)",
    r"^(it depends)\b",
    r"^(thanks for sharing)\b",
)


def _format_consequence_summary(marks: list[dict]) -> str:
    bits = []
    for item in marks[:4]:
        label = (item.get("kind") or "scar")[:18]
        summary = (item.get("summary") or "")[:90]
        bits.append(f"{label}[{item.get('remaining', 0)}]: {summary}")
    return " || ".join(bits)


def _format_world_prompt(
    entities: list[dict],
    cases: list[dict],
    campaign_npcs: list[dict] | None = None,
    artifacts: list[dict] | None = None,
    evidence_items: list[dict] | None = None,
) -> str:
    lines = []
    if entities:
        lines.append(
            "WORLD_ENTITIES:"
            + " || ".join(
                f"{item.get('entity_type', 'entity')}:{item.get('name', '')[:50]}|{item.get('status', 'noted') or 'noted'}|{item.get('summary', '')[:90]}"
                for item in entities[:4]
            )
        )
    if cases:
        lines.append(
            "WORLD_CASES:"
            + " || ".join(
                f"{item.get('case_type', 'case')}:{item.get('title', '')[:60]}|{item.get('status', 'open')}|enemy={item.get('enemy', '')[:40]}|{item.get('summary', '')[:90]}"
                for item in cases[:3]
            )
        )
    if campaign_npcs:
        lines.append(
            "CAMPAIGN_NPCS:"
            + " || ".join(
                f"{item.get('entity_type', 'npc')}:{item.get('name', '')[:50]}|{item.get('status', 'active')}|{item.get('summary', '')[:90]}"
                for item in campaign_npcs[:4]
            )
        )
    if artifacts:
        lines.append(
            "ATTACHMENT_JOURNAL:"
            + " || ".join(
                f"{item.get('name', '')[:50]}|{item.get('status', 'recent')}|{item.get('summary', '')[:90]}"
                for item in artifacts[:3]
            )
        )
    if evidence_items:
        lines.append(
            "EVIDENCE_LOCKER:"
            + " || ".join(
                f"{item.get('evidence_type', 'evidence')}:{item.get('label', '')[:50]}|{item.get('summary', '')[:90]}"
                for item in evidence_items[:4]
            )
        )
    return "\n".join(lines)


def _world_lines(entities: list[dict]) -> list[str]:
    if not entities:
        return ["Shared world: nothing persistent yet."]
    lines = ["Shared world:"]
    for item in entities[:6]:
        summary = (item.get("summary") or "").strip()
        status = item.get("status") or "noted"
        line = f"- {item.get('entity_type', 'entity')}: {item.get('name', 'unknown')} [{status}]"
        if summary:
            line += f" - {summary[:120]}"
        lines.append(line)
    return lines


def _case_lines(cases: list[dict]) -> list[str]:
    if not cases:
        return ["Shared cases: none open enough to matter."]
    lines = ["Shared cases:"]
    for item in cases[:6]:
        bit = f"- {item.get('case_type', 'case')}: {item.get('title', 'untitled')} [{item.get('status', 'open')}]"
        if item.get("enemy"):
            bit += f" enemy={item['enemy'][:50]}"
        if item.get("summary"):
            bit += f" - {item['summary'][:120]}"
        lines.append(bit)
    return lines


def _relationship_lines(user: dict | None, topics: list[dict], marks: list[dict]) -> list[str]:
    stage, stage_desc = _progression_parts(user)
    arc = _current_arc(user)
    aftermath = describe_conflict_aftermath(
        BOT_NAME,
        user.get("conflict_summary", "") if user else "",
        user.get("last_conflict_ts", 0) if user else 0,
        user.get("repair_progress", 0) if user else 0,
        conflict_open=bool((user or {}).get("conflict_open")),
    ) or "no open aftermath"
    lines = [
        f"Relationship: affection {(user or {}).get('affection', 0)}/100 | trust {(user or {}).get('trust', 0)}/100 | mood {(user or {}).get('mood', 0):+d}",
        f"Arc: {arc} | progression: {stage}",
        f"Progression detail: {stage_desc}",
        f"Conflict aftermath: {aftermath}",
        f"Preferences: voice={_pref_label((user or {}).get('voice_enabled', True))} | utility={_pref_label((user or {}).get('utility_mode', True))} | duoauto={_pref_label((user or {}).get('duo_autoplay', True))} | rpdepth={(user or {}).get('rp_depth', 'medium')}",
    ]
    if topics:
        lines.append("Top topics: " + ", ".join(item["topic"] for item in topics[:3]))
    if marks:
        lines.append("Consequences: " + " | ".join(f"{item['kind']}[{item.get('remaining', 0)}]" for item in marks[:4]))
    return lines


def _duostate_lines(speaker_mode: str, duo: dict | None, relation: dict, stories: list[dict], cases: list[dict]) -> list[str]:
    lines = [
        f"Speaker mode: {speaker_mode}",
        f"Bot relationship: {relation.get('stage', 'enemy')} | respect {relation.get('respect', 0)}/100 | tension {relation.get('tension', 0)}/100",
    ]
    if duo:
        lines.append(
            f"Active duo: mode={duo.get('mode')} | awaiting={duo.get('awaiting_bot') or 'nobody'} | turns_left={duo.get('autoplay_remaining', 0)} | topic={duo.get('topic')}"
        )
        if duo.get("silent_bot") and float(duo.get("silent_until", 0) or 0) > time.time():
            lines.append(f"Silent presence: {duo.get('silent_bot')} staying mostly quiet for this scene")
    else:
        lines.append("Active duo: none")
    if stories:
        lines.append(
            "Recent duo stories: "
            + " || ".join(
                f"{_duo_story_label(item.get('story_type', ''))}: {item.get('topic', '')[:60]} [{item.get('status', 'open')}]"
                for item in stories[:3]
            )
        )
    if cases:
        lines.append(
            "World cases: "
            + " || ".join(
                f"{item.get('case_type', 'case')}:{item.get('title', '')[:50]} [{item.get('status', 'open')}]"
                for item in cases[:3]
            )
        )
    return lines


def _self_edit_issues(text: str, recent_replies: list[str], *, user: dict | None = None) -> list[str]:
    lowered = (text or "").lower().strip()
    if not lowered:
        return []
    issues: list[str] = []
    if looks_repetitive(text, recent_replies):
        issues.append("repetitive")
    if any(token in lowered for token in _SELF_EDIT_MODERN):
        issues.append("too modern")
    if any(re.search(pattern, lowered) for pattern in _SELF_EDIT_GENERIC_PATTERNS):
        issues.append("too generic")
    if len(set(re.findall(r"[a-z']+", lowered))) < max(4, min(10, len(re.findall(r"[a-z']+", lowered)) // 2)):
        issues.append("too generic")

    affection = (user or {}).get("affection", 0)
    trust = (user or {}).get("trust", 0)
    conflict_open = bool((user or {}).get("conflict_open"))
    if (affection < 50 or trust < 45 or conflict_open) and any(
        token in lowered for token in ("darling", "sweetheart", "baby", "my love", "dear heart", "angel")
    ):
        issues.append("too soft")
    if affection < 60 and trust < 55 and any(
        token in lowered for token in ("behold", "kneel", "pathetic insect", "little worm", "how quaint")
    ):
        issues.append("out of character")
    return list(dict.fromkeys(issues))


async def _rewrite_reply_once(
    draft: str,
    issues: list[str],
    *,
    user_message: str = "",
    user: dict | None = None,
    max_tokens: int = 220,
) -> str:
    prompt = (
        "You are revising one draft before it is sent.\n"
        "Character: Wanderer.\n"
        "Required voice: detached, observant, restrained, quietly personal when earned, and in-character for Genshin.\n"
        f"Issues to fix: {', '.join(issues)}.\n"
        f"User context: {user_message[:220] or 'direct bot output'}\n"
        f"Relationship state: affection={(user or {}).get('affection', 0)} trust={(user or {}).get('trust', 0)} conflict_open={bool((user or {}).get('conflict_open'))}\n"
        f"Draft: {draft}\n"
        "Rewrite it once. Keep the meaning, keep it concise, avoid modern slang, avoid flat generic phrasing, and do not become softer than the relationship state has earned. Only return the rewritten reply."
    )
    rewritten = await qai(prompt, min(max_tokens, 260), self_edit=False, route="light")
    return strip_narration((rewritten or "").strip())


async def _maybe_self_edit_reply(
    reply: str,
    *,
    recent_replies: list[str],
    user_message: str = "",
    user: dict | None = None,
    max_tokens: int = 220,
) -> str:
    cleaned = strip_narration((reply or "").strip())
    if groq_client.is_exhausted():
        return cleaned
    issues = _self_edit_issues(cleaned, recent_replies, user=user)
    if not issues:
        return cleaned
    severe = any(issue in {"too generic", "out of character", "repetitive"} for issue in issues)
    if len(cleaned) < SELF_EDIT_MIN_REPLY_CHARS and len(user_message or "") < 90 and not severe:
        return cleaned
    debug_event("self_edit", f"{BOT_NAME} issues={','.join(issues)}")
    rewritten = await _rewrite_reply_once(
        cleaned,
        issues,
        user_message=user_message,
        user=user,
        max_tokens=max_tokens,
    )
    if not rewritten:
        return cleaned
    rewritten = diversify_reply(BOT_NAME, rewritten, recent_replies)
    rewritten = await _apply_phrase_policy(
        rewritten,
        recent_replies,
        mood=(user or {}).get("mood", 0),
        conflict_open=bool((user or {}).get("conflict_open")),
    )
    return rewritten or cleaned


async def _world_prompt_context(channel_id: int) -> str:
    try:
        entities = await mem.list_world_entities(limit=5, channel_id=channel_id)
        cases = await mem.list_world_cases(channel_id=channel_id, limit=4)
        campaign_npcs = await mem.list_campaign_npcs(channel_id=channel_id, limit=5)
        artifacts = await mem.list_world_entities("artifact", limit=3, channel_id=channel_id)
        evidence_items = await mem.list_evidence_items(channel_id, limit=4)
        return _format_world_prompt(entities, cases, campaign_npcs, artifacts, evidence_items)
    except Exception as e:
        log_error("world_prompt_context", e)
        return ""


async def _register_world_from_message(
    channel_id: int,
    user_id: int,
    user_message: str,
    scene_update: dict[str, str] | None,
):
    scene_update = scene_update or {}
    lowered = (user_message or "").lower()
    try:
        location = (scene_update.get("location") or "").strip()
        if location:
            await mem.upsert_world_entity(
                "place",
                location[:120],
                summary=f"Recurring scene location in channel {channel_id}.",
                status="active",
                channel_id=channel_id,
                updated_by=BOT_NAME,
            )
        prop = (scene_update.get("important_prop") or "").strip()
        if prop:
            entity_type = "gift" if any(token in lowered for token in ("gift", "gave", "given", "brought for", "for you")) else "prop"
            await mem.upsert_world_entity(
                entity_type,
                prop[:120],
                summary=f"Recurring scene object tied to {scene_update.get('situation', user_message)[:120]}",
                status="important",
                channel_id=channel_id,
                owner_user_id=user_id,
                updated_by=BOT_NAME,
            )
        token_entities = {
            "dottore": ("enemy", "Dottore", "Recurring hostile figure."),
            "fatui": ("faction", "Fatui", "Recurring hostile faction."),
            "nahida": ("ally", "Nahida", "Recurring ally or point of loyalty."),
            "traveler": ("ally", "Traveler", "Recurring ally or traveling companion."),
            "traveller": ("ally", "Traveler", "Recurring ally or traveling companion."),
            "ei": ("figure", "Ei", "Recurring figure with emotional and political weight."),
            "raiden": ("figure", "Raiden Ei", "Recurring figure with emotional and political weight."),
        }
        for token, (entity_type, name, summary) in token_entities.items():
            if token in lowered:
                await mem.upsert_world_entity(
                    entity_type,
                    name,
                    summary=summary,
                    status="remembered",
                    channel_id=channel_id,
                    updated_by=BOT_NAME,
                )
        npc_match = re.search(
            r"\b(?P<role>enemy|ally|npc|rival|captain|doctor|agent|friend)\b(?:\s+named)?\s+(?P<name>[A-Z][a-zA-Z' -]{2,40})",
            user_message or "",
        )
        if npc_match:
            raw_role = (npc_match.group("role") or "npc").lower()
            role = "enemy" if raw_role in {"enemy", "rival"} else "ally" if raw_role in {"ally", "friend"} else "npc"
            name = (npc_match.group("name") or "").strip(" .,!?:;")
            if name:
                await mem.note_campaign_npc(
                    name,
                    role=role,
                    summary=f"Recurring {role} mentioned in channel {channel_id}: {(user_message or '')[:140]}",
                    status="active",
                    channel_id=channel_id,
                    owner_user_id=user_id,
                    updated_by=BOT_NAME,
                )
    except Exception as e:
        log_error("register_world_from_message", e)


def _attachment_vision_note(filename: str = "", text: str = "") -> str:
    lowered = f"{filename} {text}".lower()
    if any(token in lowered for token in ["screenshot", "screen shot", "ui", "interface", "menu", "error", "app", "discord.com/channels"]):
        return "Treat it like a screenshot or interface if it looks like one; mention visible text, layout, and what the screen is doing."
    return ""


def _extract_pdf_preview_text(file_bytes: bytes, *, max_chars: int = 2400) -> str:
    text = ""
    try:
        import pdfplumber

        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            text = "\n".join((page.extract_text() or "")[:900] for page in pdf.pages[:3])
    except Exception:
        try:
            import PyPDF2

            reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
            text = "\n".join((page.extract_text() or "")[:900] for page in reader.pages[:3])
        except Exception:
            text = ""
    return re.sub(r"\s+", " ", text or "").strip()[:max_chars]


async def _attachment_context_for_message(message, content: str, *, direct: bool = False) -> str:
    chunks: list[str] = []
    try:
        urls = extract_urls(content, max_urls=2)
        for url in urls[:1]:
            preview = await fetch_url_preview(url, max_chars=700)
            preview_context = format_url_preview_context(preview)
            if preview_context:
                chunks.append(preview_context)
        if direct:
            pdf_attachment = next(
                (
                    a for a in message.attachments
                    if (a.content_type and "pdf" in a.content_type.lower()) or a.filename.lower().endswith(".pdf")
                ),
                None,
            )
            if pdf_attachment:
                import aiohttp as _aiohttp

                async with _aiohttp.ClientSession() as _sess:
                    async with _sess.get(pdf_attachment.url) as _resp:
                        file_bytes = await _resp.read()
                preview_text = _extract_pdf_preview_text(file_bytes)
                if preview_text:
                    chunks.append(f"ATTACHMENT_PDF:{pdf_attachment.filename[:80]}|{preview_text[:900]}")
                    await _remember_attachment_artifact(
                        message.channel.id,
                        message.author.id,
                        pdf_attachment.filename or "shared pdf",
                        f"PDF artifact: {preview_text[:200]}",
                        status="remembered",
                    )
    except Exception as e:
        log_error("attachment_context", e)
    return "\n".join(chunk for chunk in chunks if chunk)


async def _achievement_context(user_id: int) -> str:
    try:
        achievements = await mem.get_hidden_achievements(f"user:{user_id}", 5)
        keys = [item.get("achievement_key", "") for item in achievements if item.get("achievement_key")]
        if not keys:
            return ""
        return ", ".join(keys[:4])
    except Exception as e:
        log_error("achievement_context", e)
        return ""


async def _maybe_send_softness_beat(
    channel,
    *,
    user_id: int,
    channel_id: int,
    user: dict | None,
    trigger: str,
    guild=None,
) -> bool:
    pools = {"trust_reveal": TRUST_REVEALS, **SOFTNESS_RARE_LINES}
    cooldowns = {
        "trust_reveal": 86400,
        "repair": 43200,
        "jealous_soft": 64800,
        "duet_peace": 64800,
    }
    pool = pools.get(trigger) or []
    if not pool:
        return False
    scopes = [f"{BOT_NAME}:soft:user:{user_id}", f"{BOT_NAME}:soft:global"]
    cooldown = cooldowns.get(trigger, 43200)
    for scope in scopes:
        allowed, remaining = await mem.consume_phrase_with_status(scope, f"{BOT_NAME}:soft:{trigger}", cooldown)
        if not allowed:
            debug_event("phrase", f"{BOT_NAME} blocked softness '{trigger}' scope={scope} remaining={remaining}s")
            return False
    line = await _pick_fresh_pool_line(pool, channel_id=channel_id, user_id=user_id)
    scene_tag = "repair" if trigger == "repair" else ""
    duo_mode = "duet" if trigger == "duet_peace" else ""
    jealousy_level = 60 if trigger == "jealous_soft" else 0
    if guild and user and user.get("voice_enabled", True) and random.random() < 0.18:
        sent = await send_voice(
            channel,
            line,
            mood=user.get("mood", 0),
            guild=guild,
            user=user,
            scene_tag=scene_tag,
            is_dm=not bool(guild),
            duo_mode=duo_mode,
            jealousy_level=jealousy_level,
        )
        if sent:
            await mem.add_message(user_id, channel_id, "assistant", f"[voice message] {line}")
        else:
            await channel.send(line)
            await mem.add_message(user_id, channel_id, "assistant", line)
    else:
        await channel.send(line)
        await mem.add_message(user_id, channel_id, "assistant", line)
    if trigger == "trust_reveal":
        if await mem.unlock_hidden_achievement(f"user:{user_id}", "wanderer_rare_confession", "He let a rare confession slip through."):
            debug_event("memory", f"{BOT_NAME} achievement unlocked user={user_id} key=wanderer_rare_confession")
    return True


async def _maybe_refresh_dynamic_nicknames(message, user: dict | None, triangle: dict | None):
    if not user:
        return
    try:
        triangle = triangle or {}
        jealousy = int(triangle.get("jealousy_level", 0) or 0)
        arc = user.get("emotional_arc") or compute_emotional_arc(
            user.get("affection", 0),
            user.get("trust", 0),
            user.get("slow_burn", 0),
            user.get("conflict_open", False),
            user.get("repair_count", 0),
        )
        affection_ready = user.get("affection", 0) >= 45 or user.get("trust", 0) >= 40 or jealousy >= 50 or arc in {"tender", "devoted", "attached"}
        if affection_ready and (not user.get("affection_nick") or random.random() < 0.08 or jealousy >= 60):
            prompt = (
                f"The Wanderer is choosing a dynamic nickname for {message.author.display_name}. "
                f"ARC:{arc} AFFECTION:{user.get('affection', 0)} TRUST:{user.get('trust', 0)} "
                f"JEALOUSY:{jealousy} PARTNER_PREF:{triangle.get('favored_bot', 'none')}. "
                "Make it observant, restrained, and specific. If jealousy is high, make it clipped and more proprietary. "
                "1-3 words only. Just the nickname."
            )
            nick = (await qai(prompt, 20) or "").strip().strip("\"'`*")
            if nick and len(nick) < 30:
                await mem.set_affection_nick(message.author.id, nick)

        grudge_ready = user.get("mood", 0) <= -7 or user.get("conflict_open") or jealousy >= 40
        if grudge_ready and (not user.get("grudge_nick") or random.random() < 0.08 or jealousy >= 55):
            prompt = (
                f"The Wanderer is choosing a hostile nickname for {message.author.display_name}. "
                f"MOOD:{user.get('mood', 0)} CONFLICT:{user.get('conflict_open')} JEALOUSY:{jealousy}. "
                "Make it dry, sharp, and personal. 1-3 words only."
            )
            nick = (await qai(prompt, 20) or "").strip().strip("\"'`*")
            if nick and len(nick) < 30:
                await mem.set_grudge_nick(message.author.id, nick)
        elif user.get("grudge_nick") and not user.get("conflict_open") and user.get("mood", 0) > -4 and jealousy < 20 and random.random() < 0.08:
            await mem.set_grudge_nick(message.author.id, None)
    except Exception as e:
        log_error("dynamic_nicknames", e)


async def _maybe_finalize_hidden_achievements(session: dict | None, text: str = ""):
    if not session:
        return
    user_id = int(session.get("initiator_user_id", 0) or 0)
    if not user_id:
        return
    mode = session.get("mode", "")
    lowered = (text or "").lower()
    try:
        if mode == "duet" and not any(token in lowered for token in ["idiot", "pathetic", "shut up", "weak", "hate you"]):
            if await mem.unlock_hidden_achievement(f"user:{user_id}", "peaceful_duet", "The duo scene stayed unexpectedly peaceful."):
                debug_event("memory", f"{BOT_NAME} achievement unlocked user={user_id} key=peaceful_duet")
        if mode == "trial":
            if await mem.unlock_hidden_achievement(f"user:{user_id}", "survived_duo_trial", "They made it through a full two-bot trial."):
                debug_event("memory", f"{BOT_NAME} achievement unlocked user={user_id} key=survived_duo_trial")
        if mode in {"trial", "mission", "interrogate"}:
            ending = infer_duo_ending_tag(mode, text)
            if ending == "mercy":
                await mem.unlock_hidden_achievement(f"user:{user_id}", "duo_mercy", "The duo scene ended in mercy instead of total ruin.")
            elif ending == "betrayal":
                await mem.unlock_hidden_achievement(f"user:{user_id}", "duo_betrayal", "The duo scene ended in betrayal.")
            elif ending == "victory":
                await mem.unlock_hidden_achievement(f"user:{user_id}", "duo_victory", "The duo scene ended in a clean victory.")
    except Exception as e:
        log_error("finalize_hidden_achievements", e)


async def _recent_rival_topic(channel) -> str:
    try:
        async for candidate in channel.history(limit=14):
            if candidate.author.bot:
                continue
            content = re.sub(r"\s+", " ", (candidate.content or "").strip())
            if not content or content.startswith("!") or len(content) < 20:
                continue
            if any(token in content.lower() for token in [BOT_NAME, PARTNER_NAME.lower()]):
                continue
            return content[:160]
    except Exception as e:
        log_error("recent_rival_topic", e)
    return ""


def _is_in_quiet_hours(user: dict | None) -> bool:
    if not user:
        return False
    try:
        tz = ZoneInfo(user.get("timezone_name") or "America/Los_Angeles")
        hour = datetime.now(tz).hour
    except Exception:
        hour = datetime.now().hour
    start = int(user.get("quiet_hours_start", 23)) % 24
    end = int(user.get("quiet_hours_end", 8)) % 24
    if start == end:
        return False
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


def _duo_autoplay_prompt(session: dict) -> str:
    mode = session.get("mode", "both")
    topic = session.get("topic", "")
    partner = _partner_autoplay_name()
    remaining = max(0, int(session.get("autoplay_remaining", 0) or 0))
    stage_note = describe_duo_scene_stage(mode, topic, remaining)
    silent_note = ""
    if (session.get("silent_bot", "") or "").strip().lower() == BOT_NAME:
        silent_note = " Stay mostly quiet unless the beat truly matters; if you speak, make it one short line."
    dual_verdict = describe_dual_verdict_mode(BOT_NAME, mode, topic)
    outro = "This is the last automatic turn, so land it cleanly." if remaining <= 1 else f"Leave room for {remaining} more automatic turn(s) after you."
    if mode == "duet":
        return f"Continue the shared two-bot scene after {partner}'s turn. Topic: {topic}. {stage_note} One short follow-up turn only.{silent_note} {outro}"
    if mode == "argue":
        return f"{partner} already took a side. Fire back in this two-bot argument about: {topic}. {stage_note} {dual_verdict} One or two sentences.{silent_note} {outro}"
    if mode == "compare":
        return f"{partner} already gave their take. Give your contrasting verdict on: {topic}. {stage_note} {dual_verdict} One or two sentences.{silent_note} {outro}"
    if mode == "interrogate":
        return f"The two-bot interrogation is active. Add your own sharper question or conclusion about: {topic}. {stage_note} {dual_verdict} One or two sentences.{silent_note} {outro}"
    if mode == "trial":
        return f"The two-bot trial is active. Give your side's judgment on: {topic}. {stage_note} {dual_verdict} One or two sentences.{silent_note} {outro}"
    if mode == "mission":
        return f"The two-bot mission planning scene is active. Add your own role or warning about: {topic}. {stage_note} One or two sentences.{silent_note} {outro}"
    if mode == "truthdare":
        return f"The two-bot truth-or-dare game is active. Continue it with one pointed challenge about: {topic}. {stage_note} One or two sentences.{silent_note} {outro}"
    return f"The shared duo mode is active. Follow up after the other bot about: {topic}. One or two sentences.{silent_note} {outro}"


DUO_CHAIN_TURNS = {
    "both": 1,
    "duet": 2,
    "argue": 3,
    "compare": 2,
    "interrogate": 4,
    "trial": 5,
    "mission": 5,
    "truthdare": 3,
}


def _pref_label(enabled: bool) -> str:
    return "on" if enabled else "off"


def _duo_story_label(mode: str) -> str:
    return {
        "compare": "verdict",
        "interrogate": "rival case",
        "trial": "trial",
        "mission": "mission",
        "truthdare": "truth-or-dare round",
    }.get(mode or "", mode or "duo scene")


def _current_arc(user: dict | None) -> str:
    if user and user.get("emotional_arc"):
        return user["emotional_arc"]
    return compute_emotional_arc(
        (user or {}).get("affection", 0),
        (user or {}).get("trust", 0),
        (user or {}).get("slow_burn", 0),
        (user or {}).get("conflict_open", False),
        (user or {}).get("repair_count", 0),
    )


def _progression_parts(user: dict | None) -> tuple[str, str]:
    progression = describe_relationship_progression(
        BOT_NAME,
        (user or {}).get("affection", 0),
        (user or {}).get("trust", 0),
        romance_mode=(user or {}).get("romance_mode", False),
        conflict_open=(user or {}).get("conflict_open", False),
        slow_burn=(user or {}).get("slow_burn", 0),
    )
    stage, _, desc = progression.partition("|")
    return stage or "hostile", desc or progression


def _ambient_scene_line() -> str:
    now = datetime.now()
    month = now.month
    day = now.day
    hour = now.hour
    if (month, day) == (1, 1):
        pool = [
            "A new year, and somehow the sky still looks the same.",
            "Another year already. Keep walking. That's usually enough.",
        ]
    elif (month, day) == (10, 31):
        pool = [
            "The night feels crowded with costumes and noise. Try not to become part of it.",
            "There's a strange kind of theater to tonight. I noticed.",
        ]
    elif hour in range(0, 5):
        pool = [
            "It's late. The world gets quieter at this hour, if you let it.",
            "These hours are better for honest thoughts. People usually ruin that.",
        ]
    elif hour in range(5, 8):
        pool = [
            "Morning is quieter before everyone remembers to be exhausting.",
            "The day has barely started. That's almost merciful.",
        ]
    elif month in {12, 1, 2}:
        pool = [
            "Cold air has a way of stripping things down to what matters.",
            "Winter makes even familiar roads feel a little more distant.",
        ]
    elif month in {6, 7, 8}:
        pool = [
            "The heat makes everything feel slower, heavier.",
            "Summer has a way of stretching the day until patience thins out.",
        ]
    else:
        pool = CONVERSATION_STARTERS
    return random.choice(pool)


async def _start_duo_mode(ctx, user: dict | None, mode: str, topic: str, *, story: bool = False, enemy: str = ""):
    autoplay_turns = DUO_CHAIN_TURNS.get(mode, 1)
    if not (user or {}).get("duo_autoplay", True):
        autoplay_turns = 1
    await mem.set_duo_session(
        ctx.channel.id,
        mode,
        topic,
        BOT_NAME,
        initiator_user_id=ctx.author.id,
        awaiting_bot=PARTNER_NAME,
        autoplay_turns=autoplay_turns,
        autoplay_delay=6,
    )
    if story:
        await mem.start_duo_story(ctx.channel.id, mode, topic, enemy=enemy)
    await _maybe_seed_silent_presence(ctx.channel.id, mode)


async def _pin_memory(ctx, kind: str, text: str | None, weight: int, *, shared_joke: bool = False):
    if not text:
        await safe_reply(ctx, f"Give me a {kind} worth keeping.")
        return
    await _setup(ctx)
    clipped = text[:220]
    await mem.add_memory_event(ctx.author.id, kind, clipped, weight)
    if kind != "joke":
        await mem.set_callback_memory(ctx.author.id, clipped)
    if shared_joke:
        await mem.add_inside_joke(ctx.author.id, clipped)
        await mem.add_shared_inside_joke(ctx.author.id, clipped, source=kind)
    await safe_reply(ctx, f"...Alright. I pinned that as a {kind}.")


async def _user_memory_context(user_id: int, user: dict | None) -> list[str]:
    parts: list[str] = []
    try:
        topics = await mem.get_top_topics(user_id, 3)
        topic_desc = describe_topic_profile(topics)
        if topic_desc:
            parts.append(f"TOPICS:{topic_desc}")
        milestones = await mem.get_recent_milestones(f"{BOT_NAME}:user:{user_id}", 1)
        if milestones:
            parts.append(f"MILESTONE:{milestones[0][:140]}")
        shared_joke = await mem.get_random_shared_inside_joke(user_id)
        if shared_joke and random.random() < 0.2:
            parts.append(f'SHARED_JOKE:"{shared_joke[:100]}"')
        memory_event = await mem.get_weighted_memory_event(user_id)
        if memory_event and random.random() < 0.25:
            parts.append(f"MEMORY_BANK:{memory_event.get('kind','memory')}|{memory_event.get('memory','')[:140]}")
        old_line = await mem.get_random_old_message(user_id)
        if old_line and random.random() < 0.12:
            parts.append(f"RECALL:{old_line[:120]}")
        if user and user.get("conflict_open") and user.get("conflict_summary") and random.random() < 0.35:
            parts.append(f"FOLLOWUP:{describe_conflict_followup(user.get('conflict_summary'), user.get('emotional_arc'))}")
    except Exception as e:
        log_error("user_memory_context", e)
    return parts


async def _apply_phrase_policy(
    text: str,
    recent_messages: list[str] | None = None,
    user_id: int | None = None,
    mood: int = 0,
    conflict_open: bool = False,
) -> str:
    recent_messages = recent_messages or []
    updated = strip_narration((text or "").strip())
    if not updated:
        return updated

    tch_match = _TCH_PATTERN.search(updated)
    if tch_match:
        rule = BOT_RARE_PHRASES.get("tch", {})
        scope = f"{BOT_NAME}:user:{user_id}" if user_id is not None else f"{BOT_NAME}:global"
        annoyed_enough = conflict_open or mood <= int(rule.get("mood_threshold", -6))
        allowed = annoyed_enough
        cooldown = int(rule.get("cooldown", 0))
        if allowed and cooldown > 0:
            allowed, remaining = await mem.consume_phrase_with_status(scope, f"{BOT_NAME}:tch", cooldown)
            if not allowed:
                debug_event("phrase", f"{BOT_NAME} blocked 'tch' scope={scope} remaining={remaining}s annoyed={annoyed_enough}")

        if not allowed:
            if tch_match.start() == 0:
                updated = replace_opening_phrase(BOT_NAME, updated, recent_messages)
            else:
                replacement = pick_fresh_option(BOT_NAME, rule.get("replacements") or ["Honestly."], recent_messages)
                updated = _TCH_PATTERN.sub(f"{replacement} ", updated, count=1).strip()
                updated = re.sub(r"\s{2,}", " ", updated)
        else:
            debug_event("phrase", f"{BOT_NAME} allowed 'tch' scope={scope}")
            return updated

    opening = detect_opening_phrase(BOT_NAME, updated)
    if not opening or opening == "tch":
        return updated

    rule = BOT_RARE_PHRASES.get(opening)
    if not rule:
        return updated

    scopes = [f"{BOT_NAME}:global"]
    if user_id is not None:
        scopes.insert(0, f"{BOT_NAME}:user:{user_id}")
    cooldown = int(rule.get("cooldown", 0))
    allowed = True
    if cooldown > 0:
        for scope in scopes:
            allowed, remaining = await mem.consume_phrase_with_status(scope, f"{BOT_NAME}:{opening}", cooldown)
            if not allowed:
                debug_event("phrase", f"{BOT_NAME} blocked '{opening}' scope={scope} remaining={remaining}s")
                break
    if allowed:
        debug_event("phrase", f"{BOT_NAME} allowed '{opening}' scopes={','.join(scopes)}")
        return updated
    debug_event("phrase", f"{BOT_NAME} diversified opener '{opening}'")
    return replace_opening_phrase(BOT_NAME, updated, recent_messages)


async def _learn_user_state(user_id: int, user_message: str):
    try:
        current = await mem.get_user(user_id)
        if not current:
            return
        profile = apply_style_deltas(current.get("style_profile"), analyze_style_deltas(user_message))
        await mem.set_style_profile(user_id, profile)
        debug_event("memory", f"{BOT_NAME} style_profile user={user_id} traits={','.join(sorted([k for k, v in profile.items() if v >= 8])[:3]) or 'none'}")

        callback_memory = extract_callback_candidate(user_message)
        if callback_memory:
            await mem.set_callback_memory(user_id, callback_memory)
            debug_event("memory", f"{BOT_NAME} callback user={user_id} text={callback_memory[:80]}")
        for topic in detect_topics(user_message):
            await mem.record_topic(user_id, topic)
            debug_event("memory", f"{BOT_NAME} topic user={user_id} topic={topic}")

        if detect_repair_signal(user_message) and current.get("conflict_open"):
            resolved = await mem.record_repair_attempt(user_id, user_message[:180])
            await mem.update_trust(user_id, +2)
            await mem.update_affection(user_id, +1)
            await mem.set_callback_memory(user_id, f"They tried to repair things: {user_message[:180]}")
            debug_event("memory", f"{BOT_NAME} conflict_repair user={user_id} resolved={resolved}")
        elif detect_conflict_signal(user_message) and (current.get("romance_mode") or current.get("affection", 0) >= 30):
            await mem.open_conflict(user_id, user_message[:180])
            debug_event("memory", f"{BOT_NAME} conflict_opened user={user_id} text={user_message[:80]}")

        refreshed = await mem.get_user(user_id)
        if not refreshed:
            return
        arc = compute_emotional_arc(
            refreshed.get("affection", 0),
            refreshed.get("trust", 0),
            refreshed.get("slow_burn", 0),
            refreshed.get("conflict_open", False),
            refreshed.get("repair_count", 0),
        )
        await mem.set_emotional_arc(user_id, arc)
        debug_event("memory", f"{BOT_NAME} arc user={user_id} arc={arc}")
    except Exception as e:
        log_error("learn_user_state", e)


async def _observe_partner_message(content: str) -> tuple[dict, list[dict], str]:
    theme = detect_banter_theme(content)
    await mem.record_bot_banter(PARTNER_PAIR_KEY, PARTNER_NAME, content, theme)
    relation = await mem.get_bot_relationship(PARTNER_PAIR_KEY)
    respect_delta, tension_delta = infer_bot_relation_deltas(content, theme)
    respect = relation.get("respect", 0) + respect_delta
    tension = relation.get("tension", 0) + tension_delta
    stage = compute_bot_stage(respect, tension)
    note = None
    if stage != relation.get("stage"):
        note = f"The old grudge has shifted into {stage} after too many exchanges about {theme}."
    await mem.update_bot_relationship(
        PARTNER_PAIR_KEY,
        stage,
        respect,
        tension,
        theme=theme,
        history_note=note,
        touched_exchange=False,
    )
    relation = await mem.get_bot_relationship(PARTNER_PAIR_KEY)
    recent = await mem.get_recent_bot_banter(PARTNER_PAIR_KEY, 8)
    milestone_note = relationship_milestone_note(stage, relation.get("respect", 0), relation.get("tension", 0))
    marker = f"pair:{stage}"
    if milestone_note and not await mem.has_milestone(PARTNER_PAIR_KEY, marker):
        await mem.add_milestone(PARTNER_PAIR_KEY, marker, milestone_note)
        debug_event("relationship", f"{BOT_NAME} milestone marker={marker} note={milestone_note[:90]}")
    debug_event("relationship", f"{BOT_NAME} partner stage={relation.get('stage')} respect={relation.get('respect')} tension={relation.get('tension')} theme={theme}")
    return relation, recent, theme


async def _find_romance_target(channel) -> discord.Member | None:
    try:
        if not getattr(channel, "guild", None):
            return None
        for uid in await mem.get_romance_users():
            if await mem.get_user_last_channel(uid) == channel.id:
                member = channel.guild.get_member(uid)
                if member:
                    return member
    except Exception as e:
        log_error("find_romance_target", e)
    return None


async def _handle_partner_message(message) -> bool:
    try:
        # If Scaramouche is talking TO a user (mentions them) but NOT mentioning us,
        # check if we're jealous (high affection with that user) — butt in ~50% of the time
        we_mentioned = bot.user in message.mentions
        replying_to_us = False
        if message.reference:
            try:
                ref = message.reference.resolved
                if ref is None:
                    ref = await message.channel.fetch_message(message.reference.message_id)
                if ref and ref.author.id == bot.user.id:
                    replying_to_us = True
            except Exception:
                pass
        mentioned_users = [u for u in message.mentions if not u.bot]
        if mentioned_users and not we_mentioned and not replying_to_us:
            # Check if we have high affection (70+) with any mentioned user
            jealous_of = None
            for u in mentioned_users:
                try:
                    u_data = await mem.get_user(u.id)
                    if u_data and (u_data.get("affection", 0) or 0) >= 70:
                        jealous_of = u
                        break
                except Exception:
                    pass
            if not jealous_of:
                # Low affection — don't care, stay quiet
                return True
            if random.random() > 0.50:
                # 50% chance to butt in jealously
                return True
            # Jealous butt-in: generate a jealous response
            relation, recent_banter, theme = await _observe_partner_message(message.content)
            prompt = (
                f"You (Wanderer) just saw Scaramouche talking to {jealous_of.display_name}, someone you quietly care about. "
                f"Scaramouche said: '{message.content[:220]}'\n"
                f"You feel a pang of jealousy but you'd never say it outright. Step in with something understated but pointed — "
                f"a quiet redirect, a subtle claim on the person's attention, or a calm observation that undercuts Scaramouche. "
                f"1-2 sentences. No narration. Don't say you're jealous."
            )
            reply = await qai(prompt, 180)
            if reply:
                reply = strip_narration(reply)
                await message.reply(reply)
                await mem.record_bot_banter(PARTNER_PAIR_KEY, BOT_NAME, reply, "jealousy")
            return True

        relation, recent_banter, theme = await _observe_partner_message(message.content)
        if time.time() - relation.get("last_exchange", 0) < 90:
            return True

        duo = await mem.get_duo_session(message.channel.id)
        silent_active = bool(
            duo
            and (duo.get("silent_bot", "") or "").strip().lower() == BOT_NAME
            and float(duo.get("silent_until", 0) or 0) > time.time()
        )
        intervention_reason = detect_intervention_reason(message.content, relation)
        if silent_active and not intervention_reason and random.random() < 0.82:
            debug_event("relationship", f"{BOT_NAME} silent_presence_hold channel={message.channel.id}")
            return True

        jealousy_target = await _find_romance_target(message.channel) if message.guild else None
        chance = 0.12 if relation.get("stage") == "reluctant respect" else 0.17 if relation.get("stage") == "competitive" else 0.22
        if jealousy_target:
            chance += 0.1
        if silent_active:
            chance *= 0.35

        if intervention_reason:
            cooldown_open = float((duo or {}).get("intervention_cooldown", 0) or 0)
            if cooldown_open <= time.time() and random.random() < 0.62:
                partner_context = describe_bot_relationship(BOT_NAME, relation, recent_banter)
                contradiction = await _contradictory_memory_context(
                    message.channel.id,
                    user_message=message.content,
                    topic=(duo or {}).get("topic", ""),
                )
                prompt = (
                    f"{partner_context}\n"
                    f"{contradiction}\n"
                    f"INTERVENTION_MODE:{intervention_reason}. {PARTNER_NAME.title()} just said: '{message.content[:220]}'.\n"
                    "Cut in unprompted as Wanderer. You can stop him, undercut the tone, or redirect the scene, "
                    "but make it sound like you noticed the line crossed into blunt damage instead of useful precision. "
                    "One or two sentences. No narration."
                )
                reply = await qai(prompt, 180, route="primary")
                reply = await _apply_phrase_policy(reply, [item.get("content", "") for item in recent_banter], mood=-3, conflict_open=True)
                if reply:
                    await message.reply(reply)
                    await mem.record_bot_banter(PARTNER_PAIR_KEY, BOT_NAME, reply, "intervention")
                    await mem.note_shared_event_memory(
                        message.channel.id,
                        (duo or {}).get("topic", "") or _event_topic_from_text(message.content, fallback="rival intervention"),
                        BOT_NAME,
                        f"Intervention over {intervention_reason}: {reply[:180]}",
                        truth_hint=intervention_reason,
                    )
                    await mem.set_duo_presence(
                        message.channel.id,
                        silent_bot=(duo or {}).get("silent_bot", ""),
                        silent_until=float((duo or {}).get("silent_until", 0) or 0),
                        intervention_cooldown=time.time() + 240,
                    )
                    return True

        if random.random() >= chance:
            return True

        partner_context = describe_bot_relationship(BOT_NAME, relation, recent_banter)
        contradiction = await _contradictory_memory_context(
            message.channel.id,
            user_message=message.content,
            topic=(duo or {}).get("topic", ""),
        )
        extra = ""
        if jealousy_target:
            extra = f"\nA romance-mode user you care about is in this channel: {jealousy_target.display_name}. That should sharpen the jealousy."

        prompt = (
            f"{partner_context}\n{contradiction}{extra}\n\n"
            f"Scaramouche just said: '{message.content[:220]}'\n"
            f"Reply as Wanderer. He refuses to admit how much of that shared history still matters. "
            f"If respect has grown, show it as cleaner honesty instead of recycled annoyance. "
            f"Let the disagreement bite into morality, strategy, loyalty, power, forgiveness, or whether the user is worth trusting when it fits the theme. "
            f"One or two sentences. No narration."
        )
        recent_partner_lines = [item.get('content', '') for item in recent_banter]
        mood = -7 if theme in {'identity', 'weakness', 'jealousy'} else -3 if theme in {'origins', 'change'} else 0
        reply = await qai(prompt, 180)
        reply = await _apply_phrase_policy(reply, recent_partner_lines, mood=mood, conflict_open=theme in {'identity', 'weakness', 'jealousy'})
        if not reply:
            return True

        if jealousy_target and random.random() < 0.45:
            await message.channel.send(f"{jealousy_target.mention} {reply}")
        else:
            await message.reply(reply)

        own_theme = detect_banter_theme(reply)
        await mem.record_bot_banter(PARTNER_PAIR_KEY, BOT_NAME, reply, own_theme)
        respect_delta, tension_delta = infer_bot_relation_deltas(reply, own_theme)
        respect = relation.get("respect", 0) + respect_delta + (1 if relation.get("tension", 0) >= 45 else 0)
        tension = relation.get("tension", 0) + tension_delta - (1 if relation.get("respect", 0) >= 25 else 0)
        stage = compute_bot_stage(respect, tension)
        note = None
        if stage != relation.get("stage"):
            note = f"The rivalry stopped feeling static; now it lands closer to {stage}."
        await mem.update_bot_relationship(
            PARTNER_PAIR_KEY,
            stage,
            respect,
            tension,
            theme=own_theme,
            history_note=note,
            touched_exchange=True,
        )
        await mem.note_shared_event_memory(
            message.channel.id,
            (duo or {}).get("topic", "") or _event_topic_from_text(message.content, fallback=theme),
            BOT_NAME,
            reply[:220],
            truth_hint=f"partner argument about {theme}",
        )
    except Exception as e:
        log_error("handle_partner_message", e)
    return True

# ── Groq AI call (non-blocking) ───────────────────────────────────────────────
def _groq_blocking(messages: list, system: str, max_tokens: int = 500, model: str | None = None) -> str:
    try:
        msgs = [{"role": "system", "content": system}] + messages
        resp = groq_client.call_with_retry(
            model=model or GROQ_MODEL,
            messages=msgs,
            max_tokens=max_tokens,
            temperature=0.95,
            frequency_penalty=0.7,
            presence_penalty=0.6,
        )
        return resp.choices[0].message.content.strip() or ""
    except Exception as e:
        print(f"[Groq] {e}")
        return ""

async def groq_call(messages: list, system: str, max_tokens: int = 500, *, route: str = "auto") -> str:
    loop = asyncio.get_event_loop()
    model_name = _select_text_model(route=route)
    result = await loop.run_in_executor(None, _groq_blocking, messages, system, max_tokens, model_name)
    return result

def _groq_quick_blocking(prompt: str, max_tokens: int = 200, model: str | None = None) -> str:
    try:
        resp = groq_client.call_with_retry(
            model=model or GROQ_MODEL,
            messages=[
                {"role": "system", "content": _BASE},
                {"role": "user", "content": prompt}
            ],
            max_tokens=max_tokens,
            temperature=0.95,
            frequency_penalty=0.7,
            presence_penalty=0.6,
        )
        return resp.choices[0].message.content.strip() or ""
    except Exception as e:
        print(f"[Groq Quick] {e}")
        return ""

async def qai(prompt: str, max_tokens: int = 200, *, self_edit: bool = True, route: str = "auto") -> str:
    try:
        recent_replies = await _recent_reply_samples()
        repeat_guard = build_prompt_guard(BOT_NAME, recent_replies)
        guarded_prompt = ((repeat_guard + "\n\n") if repeat_guard else "") + prompt
        loop = asyncio.get_event_loop()
        route_name = route if route != "auto" else ("light" if max_tokens <= 160 else "primary")
        model_name = _select_text_model(route=route_name)
        reply = ""
        for attempt in range(2):
            if groq_client.is_exhausted() and route_name == "light":
                break
            active_prompt = guarded_prompt
            if attempt:
                active_prompt += "\n\nRETRY: Use a different opening phrase and different sentence rhythm."
            reply = await loop.run_in_executor(None, _groq_quick_blocking, active_prompt, max_tokens, model_name)
            reply = diversify_reply(BOT_NAME, strip_narration(reply), recent_replies)
            reply = await _apply_phrase_policy(reply, recent_replies)
            if self_edit and reply and max_tokens >= 140 and len(reply) >= SELF_EDIT_MIN_REPLY_CHARS:
                reply = await _maybe_self_edit_reply(
                    reply,
                    recent_replies=recent_replies,
                    user_message=prompt,
                    max_tokens=min(max_tokens, 220),
                )
            if reply and not looks_repetitive(reply, recent_replies):
                break
            if groq_client.is_exhausted():
                break
        if not reply:
            if groq_client.is_exhausted() and route_name == "light":
                return ""
            reply = fallback_reply(BOT_NAME, recent_replies)
        if reply:
            remember_output(BOT_NAME, reply)
        return reply
    except Exception as e:
        log_error("qai/async", e)
        return fallback_reply(BOT_NAME, get_runtime_recent(BOT_NAME, limit=20))

# ── Smart search ──────────────────────────────────────────────────────────────
SEARCH_TRIGGERS = ["what is","what are","who is","who are","when did","when was","how do","how does",
                   "how much","how many","where is","latest","recent","news","current","today",
                   "calculate","solve","what's","whats","define","explain","tell me about"]

def needs_search(text: str) -> bool:
    t = text.lower().strip()
    if t.endswith("?"): return True
    return any(t.startswith(tr) for tr in SEARCH_TRIGGERS)

# ── Channel context ───────────────────────────────────────────────────────────
async def fetch_channel_context(channel, limit: int = CHANNEL_CONTEXT_LIMIT_DIRECT) -> str:
    try:
        if not hasattr(channel, 'history'): return ""
        is_dm_channel = not hasattr(channel, 'guild') or channel.guild is None
        msgs = []
        async for msg in channel.history(limit=limit):
            if not is_dm_channel and msg.author.bot:
                # Include partner bot messages, skip all others
                if msg.author.id != bot.user.id and msg.author.id != PARTNER_BOT_ID:
                    continue
            # Label: prioritize self-detection FIRST, then partner
            if msg.author.id == bot.user.id:
                author_name_label = "Wanderer (you)"
            elif PARTNER_BOT_ID and msg.author.id == PARTNER_BOT_ID:
                author_name_label = "Scaramouche"
            elif msg.author.bot:
                author_name_label = msg.author.display_name
            else:
                author_name_label = msg.author.display_name
            text = msg.content[:CHANNEL_CONTEXT_MESSAGE_CHARS].strip()
            # Detect voice messages (mp3 attachments with no text)
            has_voice = any(a.filename.endswith(".mp3") for a in msg.attachments)
            has_image = any(a.content_type and "image" in a.content_type for a in msg.attachments)
            has_video = any(a.filename.endswith((".mp4",".mov",".webm",".avi")) for a in msg.attachments)
            if not text:
                if has_voice:
                    text = "[sent a voice message]"
                elif has_image:
                    text = "[sent an image]"
                elif has_video:
                    text = "[sent a video]"
                else:
                    continue
            elif has_voice:
                text = f"[sent a voice message] {text}"
            author_name = author_name_label
            if msg.reference and msg.reference.resolved and not isinstance(msg.reference.resolved, discord.DeletedReferencedMessage):
                ref = msg.reference.resolved
                ref_author = "Wanderer (you)" if ref.author.id == bot.user.id else ("Scaramouche" if (PARTNER_BOT_ID and ref.author.id == PARTNER_BOT_ID) else ref.author.display_name)
                ref_preview = (ref.content or "")[:50].strip()
                line = f"{author_name} (replying to {ref_author}: \"{ref_preview}\"): {text}" if ref_preview else f"{author_name} (replying to {ref_author}): {text}"
            else:
                line = f"{author_name}: {text}"
            msgs.append(line)
        if not msgs: return ""
        msgs.reverse()
        context = "CHANNEL_CONTEXT:\n" + "\n".join(msgs)
        if not is_dm_channel and hasattr(channel, 'guild') and channel.guild:
            mention_map = {m.display_name: m.mention for m in channel.guild.members if not m.bot}
            if mention_map:
                context += "\nMENTION_MAP: " + ", ".join(f"{n}={v}" for n,v in list(mention_map.items())[:12])
        return context
    except Exception as e:
        log_error("fetch_channel_context", e)
        return ""

def resolve_mentions(text: str, guild) -> str:
    if not guild or not text: return text
    try:
        for member in guild.members:
            if member.bot: continue
            text = re.sub(r'@' + re.escape(member.display_name), member.mention, text, flags=re.IGNORECASE)
            text = re.sub(r'@' + re.escape(member.name), member.mention, text, flags=re.IGNORECASE)
        return text
    except Exception:
        return text

# ── Core AI response ──────────────────────────────────────────────────────────
async def get_response(user_id, channel_id, user_message, user, display_name,
                       author_mention, use_search=False, extra_context="",
                       is_owner=False, channel_obj=None, is_dm=False, direct_to_me=True):
    recent_replies: list[str] = []
    search_sources = ""
    rate_limited = False
    try:
        history_limit = _history_limit_for_reply(is_dm=is_dm, direct_to_me=direct_to_me)
        history = await mem.get_history(user_id, channel_id, limit=history_limit)
        mood      = user.get("mood", 0) if user else 0
        affection = user.get("affection", 0) if user else 0
        trust     = user.get("trust", 0) if user else 0
        drift     = user.get("drift_score", 0) if user else 0
        summary   = user.get("memory_summary") if user else None
        style_profile = user.get("style_profile", {}) if user else {}
        conflict_open = user.get("conflict_open", False) if user else False
        conflict_summary = user.get("conflict_summary") if user else None
        callback_memory = user.get("callback_memory") if user else None
        repair_count = user.get("repair_count", 0) if user else 0
        recent_replies = await _recent_reply_samples(channel_id=channel_id, user_id=user_id)
        consequence_marks = await mem.get_active_consequence_marks(user_id, 4)
        world_context = await _world_prompt_context(channel_id)
        duo_session = await mem.get_duo_session(channel_id)
        campaign_npcs = await mem.list_campaign_npcs(channel_id=channel_id, limit=5)
        scenario = detect_scenario(user_message, is_dm=is_dm)
        text_pressure = await _recent_text_pressure(channel_id)
        allow_long_text = _allow_long_text(scenario, user, (duo_session or {}).get("mode", ""))

        depth = (user or {}).get("rp_depth", "medium")
        r = random.random()
        if depth == "low":
            hint = "One sentence."
        elif depth == "high":
            if r < .3: hint = "2-3 sentences."
            elif r < .75: hint = "A few sentences."
            else: hint = "Longer, thoughtful."
        else:
            if r < .18:   hint = "2-5 words only."
            elif r < .42: hint = "One sentence."
            elif r < .74: hint = "2-3 sentences."
            elif r < .93: hint = "A few sentences."
            else:         hint = "Longer, thoughtful."
        hint = _tighten_length_hint(hint, text_pressure, allow_long_text)

        now      = datetime.now()
        days_ago = round((time.time() - (user.get("last_active", 0) if user else 0)) / 86400, 1) if user and user.get("last_active", 0) else 0
        date_ctx = f"DATE:{now.strftime('%A %b %d %Y')}|HOUR:{now.hour}|LAST_SEEN:{days_ago}d_ago"

        parts = [
            f"mention:{author_mention}", f"name:{display_name}",
            f"MOOD:{mood}({mood_label(mood)})", f"AFFECTION:{affection}",
            f"TRUST:{trust}", date_ctx, f"len:{hint}"
        ]
        if affection >= 75: parts.append("AFFECTION_SOFT")
        if trust >= 70:     parts.append("TRUST_OPEN")
        if is_owner:        parts.append("CREATOR")
        if is_dm:           parts.append("DM_MODE")
        dp = drift_phrase(drift, mood)
        if dp: parts.append(dp)
        if summary: parts.append(f"SUMMARY:{summary[:300]}")
        speech_drift = describe_speech_drift(BOT_NAME, style_profile)
        if speech_drift: parts.append(f"SPEECH_DRIFT:{speech_drift}")
        emotional_arc = compute_emotional_arc(
            affection,
            trust,
            user.get("slow_burn", 0) if user else 0,
            conflict_open,
            repair_count,
        )
        arc_desc = describe_emotional_arc(BOT_NAME, emotional_arc)
        if arc_desc: parts.append(f"ARC:{emotional_arc}|{arc_desc}")
        scenario_desc = describe_scenario_context(BOT_NAME, scenario)
        if scenario_desc: parts.append(f"SCENARIO:{scenario}|{scenario_desc}")
        if text_pressure.get("large", 0) >= 2 or text_pressure.get("walls", 0) >= 1:
            parts.append(
                f"TEXT_PACING: recent_long={text_pressure.get('large', 0)} recent_walls={text_pressure.get('walls', 0)}; "
                "keep this tighter unless the moment is unusually raw, vulnerable, or plot-heavy"
            )
        triggers = detect_emotional_triggers(user_message)
        emotional_layer = describe_emotional_layers(BOT_NAME, mood, affection, trust, emotional_arc, triggers)
        if emotional_layer: parts.append(f"EMOTIONAL_LAYER:{emotional_layer}")
        emotional_event = describe_emotional_event(
            BOT_NAME,
            triggers,
            affection=affection,
            trust=trust,
            conflict_open=conflict_open,
            repair_progress=user.get("repair_progress", 0) if user else 0,
        )
        if emotional_event:
            parts.append(emotional_event)
        arc_unlocks = describe_arc_unlocks(BOT_NAME, emotional_arc)
        if arc_unlocks: parts.append(f"ARC_UNLOCKS:{arc_unlocks}")
        progression = describe_relationship_progression(
            BOT_NAME,
            affection,
            trust,
            romance_mode=bool(user.get("romance_mode")) if user else False,
            conflict_open=conflict_open,
            slow_burn=user.get("slow_burn", 0) if user else 0,
        )
        if progression: parts.append(f"PROGRESSION:{progression}")
        if conflict_open and conflict_summary:
            parts.append(f"CONFLICT_OPEN:{conflict_summary[:140]}")
        conflict_aftermath = describe_conflict_aftermath(
            BOT_NAME,
            conflict_summary,
            user.get("last_conflict_ts", 0) if user else 0,
            user.get("repair_progress", 0) if user else 0,
            conflict_open=conflict_open,
        )
        if conflict_aftermath:
            parts.append(conflict_aftermath)
        if callback_memory and (callback_relevant(callback_memory, user_message) or random.random() < 0.18):
            parts.append(f"CALLBACK:{callback_memory[:180]}")
        if consequence_marks:
            parts.append(f"CONSEQUENCES:{_format_consequence_summary(consequence_marks)}")
        parts.extend(extract_continuity_hooks(history, user_message))
        lore_hook = describe_lore_hook(BOT_NAME, user_message)
        if lore_hook: parts.append(lore_hook)
        lore_tree = describe_specific_lore_tree(BOT_NAME, user_message)
        if lore_tree: parts.append(lore_tree)
        triangle = await mem.get_triangle_state(user_id, BOT_NAME, PARTNER_NAME)
        await _sync_private_opinions(user_id, user, triangle=triangle)
        unlock_scene = describe_relationship_unlock_scene(
            BOT_NAME,
            affection=affection,
            trust=trust,
            jealousy_level=int((triangle or {}).get("jealousy_level", 0) or 0),
            conflict_open=conflict_open,
            repair_progress=user.get("repair_progress", 0) if user else 0,
            scenario=scenario,
            text=user_message,
        )
        if unlock_scene:
            parts.append(unlock_scene)
        private_confession = describe_private_confession_scene(
            BOT_NAME,
            is_dm=is_dm,
            affection=affection,
            trust=trust,
            repair_progress=user.get("repair_progress", 0) if user else 0,
            conflict_open=conflict_open,
        )
        if private_confession:
            parts.append(private_confession)
        npc_context = describe_campaign_npcs(BOT_NAME, campaign_npcs, user_message)
        if npc_context:
            parts.append(npc_context)
        live_world = describe_live_world_context(BOT_NAME, text=user_message)
        if live_world: parts.append(live_world)
        triangle_desc = describe_triangle_jealousy(BOT_NAME, triangle, PARTNER_NAME)
        if triangle_desc:
            parts.append(f"JEALOUSY_TRIANGLE:{triangle_desc}")
        contradiction = await _contradictory_memory_context(
            channel_id,
            user_message=user_message,
            topic=(duo_session or {}).get("topic", ""),
        )
        if contradiction:
            parts.append(contradiction)
            if "YOUR_VERSION:" in contradiction and f"{PARTNER_NAME.upper()}_VERSION:" in contradiction:
                await mem.unlock_hidden_achievement(
                    f"user:{user_id}",
                    "contradictory_memory",
                    "They caught the two bots remembering the same event differently.",
                )
        achievement_ctx = await _achievement_context(user_id)
        if achievement_ctx:
            parts.append(f"HIDDEN_PROGRESS:{achievement_ctx}")
        scene_desc = describe_scene_state(await mem.get_scene_state(channel_id))
        if scene_desc:
            parts.append(f"SCENE:{scene_desc}")
        if user and user.get("affection_nick"): parts.append(f"AFFNICK:{user['affection_nick']}")
        if user and user.get("grudge_nick"):    parts.append(f"GRUDGE:{user['grudge_nick']}")
        msg_lower = user_message.lower()
        if any(token in msg_lower for token in ["nahida", "wind", "wander", "travel", "sky", "solitude"]):
            parts.append("WANDERER_EDGE: add wind, travel, solitude, and quiet-care texture when it fits")
        if any(token in msg_lower for token in ["scaramouche", "kunikuzushi", "balladeer", "old name"]):
            parts.append("WANDERER_EDGE: old-name discomfort should vary by intent; react more sharply to direct misuse than casual mention")
        if extra_context: parts.append(extra_context)
        parts.extend(await _user_memory_context(user_id, user))
        private_opinions = await _private_opinion_prompt_context(
            user_id,
            leak_partner=bool((duo_session or {}).get("mode") or _message_mentions_partner(user_message)),
        )
        parts.extend(private_opinions)
        if any(item.startswith("LEAKED_PRIVATE_OPINION:") for item in private_opinions):
            await mem.unlock_hidden_achievement(
                f"user:{user_id}",
                "leaked_private_opinion",
                "A hidden inter-bot opinion slipped into the open.",
            )
        if user and not user.get("utility_mode", True):
            parts.append("UTILITY_PREF: utility mode is off; keep facts natural instead of list-like")
        if use_search or needs_search(user_message):
            search_result, search_sources = await _grounded_search_bundle(user_message)
            if search_result:
                parts.append("FACT_MODE: answer accurately first, then add personality")
                if user and user.get("utility_mode", True):
                    parts.append("UTILITY_MODE: lead with crisp facts, then one in-character observation")
                parts.append("CITATIONS: when using search results, cite claims inline like [1] or [2]")
                parts.append(f"SEARCH_RESULT:{search_result[:1200]}")
                debug_event("search", f"{BOT_NAME} injected web context for user={user_id}")

        if user and user.get("message_count", 0) >= 20:
            profile_parts = []
            if user.get("romance_mode"):   profile_parts.append("in romance mode")
            if days_ago > 1:               profile_parts.append(f"last spoke {days_ago}d ago")
            if user.get("slow_burn", 0) >= 3: profile_parts.append(f"been kind {user['slow_burn']} days straight")
            if profile_parts: parts.append("PROFILE:" + ", ".join(profile_parts))

        channel_ctx = await fetch_channel_context(
            channel_obj,
            limit=_context_limit_for_reply(is_dm=is_dm, direct_to_me=direct_to_me),
        ) if channel_obj else ""
        partner_context = await _partner_prompt_context(user_message, channel_id=channel_id)
        duo_context = await _duo_prompt_context(channel_id, user_message)
        context_block = "[" + "|".join(parts) + "]\n"
        if world_context:
            context_block += world_context + "\n"
        if partner_context:
            context_block += partner_context + "\n"
        if duo_context:
            context_block += duo_context + "\n"
        if channel_ctx: context_block += channel_ctx + "\n\n"
        context_block += f"{display_name}: {user_message}"

        repeat_guard = build_prompt_guard(BOT_NAME, recent_replies)
        if repeat_guard:
            context_block = repeat_guard + "\n\n" + context_block

        reply_max_tokens = _reply_token_budget(
            is_dm=is_dm,
            direct_to_me=direct_to_me,
            use_search=use_search,
            is_owner=is_owner,
        )
        reply_max_tokens = _tighten_token_budget(reply_max_tokens, text_pressure, allow_long_text)
        response_model = _select_text_model(
            is_dm=is_dm,
            direct_to_me=direct_to_me,
            use_search=use_search,
            is_owner=is_owner,
            scenario=scenario,
            duo_mode=(duo_session or {}).get("mode", ""),
            has_lore=bool(lore_hook or lore_tree or unlock_scene),
        )
        reply = ""
        if groq_client.is_exhausted():
            rate_limited = True
            reply = await _provider_pause_reply(
                "groq",
                user_id=user_id,
                channel_id=channel_id,
                is_dm=is_dm,
                direct_to_me=direct_to_me,
            )
        else:
            history.append({"role": "user", "content": context_block})
            system = build_system(user, display_name, is_owner)
            retry_context = context_block
            for attempt in range(2):
                draft_history = history[:-1] + [{"role": "user", "content": retry_context}]
                reply = await groq_call(draft_history, system, max_tokens=reply_max_tokens, route="primary" if response_model == GROQ_MODEL_PRIMARY else "light")
                reply = diversify_reply(BOT_NAME, strip_narration(reply), recent_replies)
                reply = await _apply_phrase_policy(
                    reply,
                    recent_replies,
                    user_id=user_id,
                    mood=mood,
                    conflict_open=conflict_open,
                )
                if reply and not looks_repetitive(reply, recent_replies):
                    break
                retry_context = context_block + "\n\nRETRY: The last draft sounded too much like your recent replies. "
                retry_context += "Change the opener, the cadence, and the mockery pattern."

        if not reply:
            reply = fallback_reply(BOT_NAME, recent_replies)
        if not rate_limited and (is_dm or direct_to_me or len(reply) >= SELF_EDIT_MIN_REPLY_CHARS):
            reply = await _maybe_self_edit_reply(
                reply,
                recent_replies=recent_replies,
                user_message=user_message,
                user=user,
                max_tokens=min(240, max(140, reply_max_tokens // 2)),
            )
        if search_sources:
            reply = f"{reply}\n\n{search_sources}"

    except Exception as e:
        log_error("get_response", e)
        if _is_rate_limited_error(e):
            rate_limited = True
            reply = await _provider_pause_reply(
                "groq",
                user_id=user_id,
                channel_id=channel_id,
                is_dm=is_dm,
                direct_to_me=direct_to_me,
            )
        else:
            reply = fallback_reply(BOT_NAME, recent_replies)

    try:
        await mem.add_message(user_id, channel_id, "user", user_message)
        if _should_log_quote_evidence(user_message):
            await mem.add_evidence_item(
                channel_id,
                "quote",
                f"{display_name} line",
                user_message[:220],
                source_excerpt=user_message[:180],
                owner_user_id=user_id,
                updated_by=BOT_NAME,
            )
        # NOTE: assistant reply is saved in on_message AFTER voice/text decision

        msg_l = user_message.lower()
        scenario = detect_scenario(user_message, is_dm=is_dm)
        triggers = detect_emotional_triggers(user_message)
        if any(k in msg_l for k in RUDE_KW):
            await mem.update_mood(user_id, -2); await mem.update_trust(user_id, -1)
        elif any(k in msg_l for k in ROMANCE_KW):
            # Auto-enable romance mode if not already on
            user_data = await mem.get_user(user_id)
            if user_data and not user_data.get("romance_mode", False):
                await mem.set_mode(user_id, "romance_mode", True)
                print(f"[AUTO-ROMANCE] Enabled for {display_name}")
            await mem.update_mood(user_id, +1)
            await mem.update_affection(user_id, +1)
            await mem.update_trust(user_id, +1)
            await mem.update_drift(user_id, +1)
            _, threshold = await mem.increment_slow_burn(user_id)
            if threshold:
                asyncio.ensure_future(_fire_slow_burn(user_id, channel_id, display_name))
            await mem.update_last_statement(user_id, user_message[:200])
        elif any(k in msg_l for k in NICE_KW):
            await mem.update_mood(user_id, +1)
            await mem.update_affection(user_id, +1)
            await mem.update_trust(user_id, +1)
            await mem.update_last_statement(user_id, user_message[:200])
        else:
            positive = sum([
                any(w in msg_l for w in ["haha","lol","lmao","nice","cool","fun","good","great","enjoy","happy","wow","yes","please","❤","💜","🥺"]),
                msg_l.endswith("!") and len(user_message) > 8,
                "?" in user_message and len(user_message) > 15,
                len(user_message) > 100,
            ])
            negative = sum([
                any(w in msg_l for w in ["ugh","boring","whatever","idc","nope","bad","hate","worst","terrible"]),
                user_message.count("...") > 1,
            ])
            if positive >= 2:
                await mem.update_affection(user_id, +1); await mem.update_mood(user_id, +1)
                await mem.update_trust(user_id, +1); await mem.update_drift(user_id, +1)
            elif positive == 1:
                await mem.update_affection(user_id, +1)
            elif negative >= 2:
                await mem.update_mood(user_id, -1); await mem.update_trust(user_id, -1)
            elif negative == 1:
                await mem.update_mood(user_id, -1)

        if scenario == "emotional_comfort":
            await mem.update_mood(user_id, +1)
            await mem.update_trust(user_id, +1)
            if "softness" in triggers or "protectiveness" in triggers:
                await mem.update_affection(user_id, +1)
        elif scenario == "combat_action":
            await mem.update_mood(user_id, -1)
            await mem.update_trust(user_id, +1)
        elif scenario == "lore_discussion":
            await mem.update_trust(user_id, +1)
            await mem.update_drift(user_id, +1)
        elif scenario == "relationship_progression":
            await mem.update_affection(user_id, +1)
            await mem.update_trust(user_id, +1)
        elif scenario == "introspection":
            await mem.update_trust(user_id, +1)

        if "jealousy" in triggers:
            await mem.update_mood(user_id, -1)
            await mem.update_affection(user_id, +1)
        if "protectiveness" in triggers:
            await mem.update_trust(user_id, +1)
            await mem.update_affection(user_id, +1)
        if "boredom" in triggers:
            await mem.update_mood(user_id, -1)

        if random.random() < .05: await mem.update_drift(user_id, +1)
        repair_signal = detect_repair_signal(user_message)
        conflict_signal = detect_conflict_signal(user_message)
        if repair_signal:
            await mem.soften_consequence_marks(user_id, 1)
        if conflict_signal:
            await mem.add_consequence_mark(user_id, "fight", user_message[:180], severity=3, decay_days=7)
            debug_event("memory", f"{BOT_NAME} consequence user={user_id} kind=fight")
        await _learn_user_state(user_id, user_message)
        for kind, memory_text, weight in extract_memory_events(user_message):
            await mem.add_memory_event(user_id, kind, memory_text, max(weight, _memory_weight_for(kind)))
            debug_event("memory", f"{BOT_NAME} memory_bank user={user_id} kind={kind}")
            if kind == "betrayal":
                await mem.add_consequence_mark(user_id, kind, memory_text, severity=max(4, weight), decay_days=14)
            elif kind in {"fight", "slight"}:
                await mem.add_consequence_mark(user_id, kind, memory_text, severity=max(2, weight), decay_days=8)
            elif kind == "promise":
                await mem.add_consequence_mark(user_id, kind, memory_text, severity=2, decay_days=10)
            elif kind == "repair":
                await mem.soften_consequence_marks(user_id, 1)
        scene_update = infer_scene_update(user_message, display_name)
        if scene_update:
            await mem.update_scene_state(channel_id, **scene_update)
            await _register_world_from_message(channel_id, user_id, user_message, scene_update)
            debug_event("scene", f"{BOT_NAME} channel={channel_id} fields={','.join(scene_update.keys())}")
    except Exception as e:
        log_error("get_response/post", e)

    refreshed_user = None
    try:
        refreshed_user = await mem.get_user(user_id)
        if refreshed_user:
            progression = describe_relationship_progression(
                BOT_NAME,
                refreshed_user.get("affection", 0),
                refreshed_user.get("trust", 0),
                romance_mode=bool(refreshed_user.get("romance_mode")),
                conflict_open=bool(refreshed_user.get("conflict_open")),
                slow_burn=refreshed_user.get("slow_burn", 0),
            )
            stage = progression.split("|", 1)[0]
            milestone_note = progression_milestone_note(BOT_NAME, stage)
            marker = f"progress:{stage}"
            if milestone_note and not await mem.has_milestone(f"{BOT_NAME}:user:{user_id}", marker):
                await mem.add_milestone(f"{BOT_NAME}:user:{user_id}", marker, milestone_note)
                debug_event("relationship", f"{BOT_NAME} user_progression user={user_id} stage={stage}")
    except Exception:
        refreshed_user = user
    reply = diversify_reply(BOT_NAME, strip_narration(reply), recent_replies)
    reply = await _apply_phrase_policy(
        reply,
        recent_replies,
        user_id=user_id,
        mood=(refreshed_user or user or {}).get("mood", 0),
        conflict_open=(refreshed_user or user or {}).get("conflict_open", False),
    )
    if not rate_limited:
        reply = await _maybe_self_edit_reply(
            reply,
            recent_replies=recent_replies,
            user_message=user_message,
            user=(refreshed_user or user),
            max_tokens=240,
        )
    if not reply and not rate_limited:
        reply = fallback_reply(BOT_NAME, recent_replies)
    if reply:
        remember_output(BOT_NAME, reply)
    return reply


async def _web_search_groq(query: str) -> str:
    """Grounded web search with snippets and source URLs."""
    try:
        results = await search_web(query, max_results=5)
        return format_search_context(results)
    except Exception as e:
        log_error("web_search", e)
    return ""


async def _grounded_search_bundle(query: str) -> tuple[str, str]:
    try:
        results = await search_web(query, max_results=5)
        return format_search_context(results), format_search_sources(results)
    except Exception as e:
        log_error("grounded_search_bundle", e)
        return "", ""


def _memory_weight_for(kind: str) -> int:
    boosts = {
        "comfort": 5,
        "repair": 5,
        "promise": 4,
        "confession": 4,
        "bond": 4,
        "vulnerability": 4,
        "betrayal": 3,
        "slight": 2,
        "inside_joke": 2,
    }
    return boosts.get((kind or "").lower(), 3)


async def _resolve_weather_location(location: str) -> tuple[float, float] | None:
    text = (location or "").strip()
    coord_match = re.match(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$", text)
    if coord_match:
        return float(coord_match.group(1)), float(coord_match.group(2))

    import aiohttp

    headers = {"User-Agent": NWS_USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
    lookup_url = f"https://forecast.weather.gov/zipcity.php?inputstring={quote_plus(text)}"
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(lookup_url, allow_redirects=True, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            final_url = str(resp.url)
            body = await resp.text()
    for source in (final_url, body):
        match = re.search(r"[?&]lat=(-?\d+(?:\.\d+)?)[^\d-]+lon=(-?\d+(?:\.\d+)?)", source, re.IGNORECASE)
        if match:
            return float(match.group(1)), float(match.group(2))
    return None


async def _fetch_nws_weather(location: str) -> dict | None:
    coords = await _resolve_weather_location(location)
    if not coords:
        return None

    lat, lon = coords
    import aiohttp

    headers = {"User-Agent": NWS_USER_AGENT, "Accept": "application/geo+json"}
    timeout = aiohttp.ClientTimeout(total=12)
    async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
        async with session.get(f"https://api.weather.gov/points/{lat:.4f},{lon:.4f}") as resp:
            if resp.status != 200:
                return None
            points = await resp.json()

        props = points.get("properties", {})
        forecast_url = props.get("forecast")
        hourly_url = props.get("forecastHourly")
        relative = props.get("relativeLocation", {}).get("properties", {})
        city = relative.get("city") or location
        state = relative.get("state") or ""

        forecast_data = {}
        hourly_data = {}
        if forecast_url:
            async with session.get(forecast_url) as resp:
                if resp.status == 200:
                    forecast_data = await resp.json()
        if hourly_url:
            async with session.get(hourly_url) as resp:
                if resp.status == 200:
                    hourly_data = await resp.json()

    forecast_periods = forecast_data.get("properties", {}).get("periods", [])
    hourly_periods = hourly_data.get("properties", {}).get("periods", [])
    forecast_period = forecast_periods[0] if forecast_periods else {}
    hourly_period = hourly_periods[0] if hourly_periods else {}
    precip = hourly_period.get("probabilityOfPrecipitation", {}) or {}
    return {
        "place": f"{city}, {state}".strip(", "),
        "forecast": forecast_period.get("shortForecast") or hourly_period.get("shortForecast") or "forecast unavailable",
        "temperature": hourly_period.get("temperature"),
        "temperature_unit": hourly_period.get("temperatureUnit") or forecast_period.get("temperatureUnit") or "F",
        "wind_speed": hourly_period.get("windSpeed") or forecast_period.get("windSpeed") or "",
        "wind_direction": hourly_period.get("windDirection") or forecast_period.get("windDirection") or "",
        "precipitation": precip.get("value"),
    }


async def _fire_slow_burn(user_id, channel_id, display_name):
    try:
        await asyncio.sleep(random.randint(30, 180))
        ch = bot.get_channel(channel_id)
        if not ch: return
        msg = await qai(
            f"{display_name} has been consistently kind to you for days. "
            f"Something genuine surfaces — one sentence where the guard drops, just barely. "
            f"Something real. Something the Wanderer would almost never say. "
            f"Not warm. Just honest. Then it's gone.", 150)
        user_obj = await bot.fetch_user(user_id)
        await ch.send(f"{user_obj.mention} {strip_narration(msg)}")
    except Exception as e:
        log_error("slow_burn", e)
    finally:
        try: await mem.reset_slow_burn_fired(user_id)
        except: pass


# ── Voice helpers ─────────────────────────────────────────────────────────────
async def get_audio_with_mood(
    text: str,
    mood: int,
    user: dict | None = None,
    *,
    scene_tag: str = "",
    is_dm: bool = False,
    duo_mode: str = "",
    jealousy_level: int = 0,
) -> bytes | None:
    try:
        style = _voice_style_for(
            user,
            mood,
            scene_tag,
            is_dm=is_dm,
            duo_mode=duo_mode,
            jealousy_level=jealousy_level,
        )
        return await get_audio_mooded(
            strip_narration(text),
            FISH_AUDIO_API_KEY,
            mood,
            style,
            bot_name="wanderer",
        )
    except Exception as e:
        log_error("get_audio_with_mood", e)
        return None

async def send_voice(
    channel,
    text,
    ref=None,
    mood=0,
    guild=None,
    user: dict | None = None,
    *,
    scene_tag: str = "",
    is_dm: bool = False,
    duo_mode: str = "",
    jealousy_level: int = 0,
):
    try:
        if user and not user.get("voice_enabled", True):
            return False
        audio = await get_audio_with_mood(
            tts_safe(text, guild),
            mood,
            user=user,
            scene_tag=scene_tag,
            is_dm=is_dm,
            duo_mode=duo_mode,
            jealousy_level=jealousy_level,
        )
        if not audio: return False
        f = discord.File(io.BytesIO(audio), filename="wanderer.mp3")
        kwargs = {"file": f}
        if ref: kwargs["reference"] = ref
        await channel.send(**kwargs)
        return True
    except Exception as e:
        log_error("send_voice", e); return False

# ── Misc helpers ──────────────────────────────────────────────────────────────
async def maybe_react(message, romance=False):
    try:
        if random.random() > .18: return
        pool = WANDERER_EMOJIS + (ROMANCE_EMOJIS if romance else [])
        prompt = (
            f"You are the Wanderer. Someone said: '{message.content[:100]}'\n"
            f"Pick 1 emoji from this list that fits your reaction: {' '.join(pool)}\n"
            f"Reply with ONLY the single emoji."
        )
        chosen = await qai(prompt, 10)
        chosen = chosen.strip()
        if chosen not in pool: chosen = random.choice(pool)
        try: await message.add_reaction(chosen)
        except: pass
        if romance and random.random() < .15:
            second = await qai(f"Pick a SECOND different emoji for a romantic reaction to: '{message.content[:80]}'\nAvailable: {' '.join(pool)}\nOnly the emoji.", 10)
            second = second.strip()
            if second in pool and second != chosen:
                try: await asyncio.sleep(.3); await message.add_reaction(second)
                except: pass
    except Exception as e: log_error("maybe_react", e)

def resp_prob(content, mentioned, is_reply, romance, is_dm=False):
    if is_dm: return 1.0
    if mentioned or is_reply: return 1.0
    t = content.lower().strip()
    if any(t.startswith(name) for name in ("wanderer", "hat guy", "kabukimono", "kunikuzushi")): return .96
    if any(k in t for k in WANDERER_KW): return .38
    if romance: return .18
    if any(k in t for k in GENSHIN_KW): return .14
    return .03

async def typing_delay(text):
    try: await asyncio.sleep(max(.3, min(.4 + len(text.split()) * .06, 3.5) + random.uniform(-.3, .5)))
    except: pass

async def _setup_user(author):
    try:
        display_name = getattr(author, "display_name", None) or getattr(author, "name", "you")
        await mem.upsert_user(author.id, str(author), display_name)
        return await mem.get_user(author.id)
    except Exception as e:
        log_error("_setup_user", e); return None


async def _setup(ctx):
    try:
        return await _setup_user(ctx.author)
    except Exception as e:
        log_error("_setup", e); return None

async def safe_reply(ctx, text):
    text = _unwrap_dialogue_quotes(text)
    if not (text or "").strip():
        return
    try: await ctx.reply(text)
    except Exception as e: log_error("safe_reply", e)

async def safe_send(ctx, text):
    text = _unwrap_dialogue_quotes(text)
    if not (text or "").strip():
        return
    try: await ctx.send(text)
    except Exception as e: log_error("safe_send", e)


def _partner_bot_present(ctx) -> bool:
    try:
        return bool(ctx.guild and PARTNER_BOT_ID and ctx.guild.get_member(PARTNER_BOT_ID))
    except Exception:
        return False


async def _should_handle_video_command(ctx) -> bool:
    try:
        if not _partner_bot_present(ctx):
            return True
        if not getattr(ctx, "guild", None):
            return True

        ref = getattr(ctx.message, "reference", None)
        if ref:
            ref_author_id = getattr(getattr(getattr(ref, "resolved", None), "author", None), "id", None)
            if ref_author_id is None and getattr(ref, "message_id", None):
                try:
                    fetched = await ctx.channel.fetch_message(ref.message_id)
                    ref_author_id = getattr(getattr(fetched, "author", None), "id", None)
                except Exception:
                    ref_author_id = None
            if ref_author_id == bot.user.id:
                return True
            if PARTNER_BOT_ID and ref_author_id == PARTNER_BOT_ID:
                return False

        mentions = {member.id for member in getattr(ctx.message, "mentions", [])}
        if bot.user and bot.user.id in mentions:
            return True
        if PARTNER_BOT_ID and PARTNER_BOT_ID in mentions:
            return False

        return False
    except Exception:
        return False


async def _send_video_summary(ctx, summary: dict, caption: str, *, sources_text: str = ""):
    try:
        video_bytes, filename = await fetch_rendered_video_bytes(summary or {})
        await ctx.send(caption, file=discord.File(io.BytesIO(video_bytes), filename=filename))
        if sources_text.strip():
            await ctx.send(sources_text[:1800])
    except Exception as e:
        log_error("send_video_summary", e)
        await safe_send(ctx, f"The video was rendered, but sending it failed. {e}")


def _teaching_video_title(topic: str | None, attachment) -> str:
    if topic and topic.strip():
        return topic.strip()[:80]
    if attachment and getattr(attachment, "filename", ""):
        return os.path.splitext(attachment.filename)[0][:80]
    return "Wanderer Lesson"


def _teachvideo_time_hint(attachment=None) -> str:
    ext = os.path.splitext(getattr(attachment, "filename", "") or "")[1].lower()
    content_type = (getattr(attachment, "content_type", "") or "").lower()
    if content_type.startswith("video/") or ext in {".mp4", ".mov", ".mkv", ".webm"}:
        return "This will take around 4-7 minutes."
    if "pdf" in content_type or ext == ".pdf":
        return "Give me about 3-5 minutes."
    if ext in {".ppt", ".pptx", ".doc", ".docx"}:
        return "Give me about 3-5 minutes."
    if content_type.startswith("image/") or ext in {".png", ".jpg", ".jpeg", ".webp"}:
        return "Give me about 2-4 minutes."
    if ext in {".txt", ".md"}:
        return "This should take around 2-3 minutes."
    return "Give me about 2-4 minutes."


def _weathervideo_time_hint(use_duo: bool) -> str:
    return "Give us about 3-6 minutes." if use_duo else "Give me about 2-4 minutes."


def _silence_reply_pool(user: dict | None) -> list[str]:
    if user and user.get("repair_progress", 0) > 0:
        return [
            "I saw it. I just needed a minute.",
            "I'm answering now. Don't mistake that for everything being fixed.",
            "I wasn't ignoring you. I was deciding whether to be honest.",
        ]
    return [
        "I heard you. I just didn't want to answer immediately.",
        "Silence says enough sometimes.",
        "You can wait a moment. The sky won't fall.",
        "I was thinking. Try not to turn that into drama.",
    ]


async def _remember_attachment_artifact(
    channel_id: int,
    user_id: int,
    name: str,
    summary: str,
    *,
    status: str = "recent",
):
    try:
        await mem.upsert_world_entity(
            "artifact",
            name[:120],
            summary=summary[:240],
            status=status[:40],
            channel_id=channel_id,
            owner_user_id=user_id,
            updated_by=BOT_NAME,
        )
        evidence_type = "pdf" if name.lower().endswith(".pdf") else "image" if any(name.lower().endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".webp", ".gif")) else "video" if any(name.lower().endswith(ext) for ext in (".mp4", ".mov", ".webm", ".avi")) else "artifact"
        await mem.add_evidence_item(
            channel_id,
            evidence_type,
            name[:120],
            summary[:240],
            source_excerpt=summary[:180],
            owner_user_id=user_id,
            updated_by=BOT_NAME,
        )
        if await mem.unlock_hidden_achievement(
            f"user:{user_id}",
            "remembered_artifact",
            "An image, screenshot, or file became a remembered artifact.",
        ):
            debug_event("memory", f"{BOT_NAME} achievement unlocked user={user_id} key=remembered_artifact")
    except Exception as e:
        log_error("remember_attachment_artifact", e)


async def _delayed_silence_reply(message, user: dict | None, *, is_dm: bool):
    key = (message.channel.id, message.author.id)
    try:
        await asyncio.sleep(random.randint(7, 15) if not is_dm else random.randint(5, 11))
        line = await _pick_fresh_pool_line(_silence_reply_pool(user), channel_id=message.channel.id, user_id=message.author.id)
        await message.reply(line)
        await mem.add_message(message.author.id, message.channel.id if not is_dm else message.author.id, "assistant", line)
    except Exception as e:
        log_error("delayed_silence_reply", e)
    finally:
        _silence_pending.discard(key)


async def _maybe_handle_silence_behavior(message, user: dict | None, content: str, *, is_dm: bool, direct_to_me: bool) -> bool:
    if not direct_to_me or not user:
        return False
    if detect_repair_signal(content):
        return False
    if not (user.get("conflict_open") or user.get("mood", 0) <= -6 or user.get("repair_progress", 0) > 0):
        return False
    key = (message.channel.id, message.author.id)
    if key in _silence_pending:
        return False
    chance = 0.13 if user.get("conflict_open") else 0.07
    if is_dm:
        chance += 0.04
    if random.random() >= chance:
        return False
    _silence_pending.add(key)
    debug_event("silence", f"{BOT_NAME} delaying reply user={message.author.id} channel={message.channel.id}")
    asyncio.ensure_future(_delayed_silence_reply(message, user, is_dm=is_dm))
    return True


async def _maybe_schedule_private_confession_scene(message, user: dict | None, content: str, *, is_dm: bool):
    if not is_dm or not user:
        return
    scene_note = describe_private_confession_scene(
        BOT_NAME,
        is_dm=is_dm,
        affection=user.get("affection", 0),
        trust=user.get("trust", 0),
        repair_progress=user.get("repair_progress", 0),
        conflict_open=bool(user.get("conflict_open")),
    )
    if not scene_note:
        return
    if random.random() >= 0.09:
        return
    allowed, _ = await mem.consume_phrase_with_status(f"{BOT_NAME}:private_confession:user:{message.author.id}", "private_confession_scene", 172800)
    if not allowed:
        return

    async def _run():
        try:
            await asyncio.sleep(random.randint(2, 5))
            prompt = (
                f"{scene_note}\n"
                f"You are in a private DM with {message.author.display_name}. Their latest message was: '{content[:220]}'. "
                "Send one additional message only. Make it feel like you almost decided not to say it at all. "
                "One or two sentences. No narration."
            )
            line = await qai(prompt, 180, route="primary")
            line = strip_narration(line)
            if not line:
                return
            await message.channel.send(line)
            await mem.add_message(message.author.id, message.author.id, "assistant", line)
            if await mem.unlock_hidden_achievement(f"user:{message.author.id}", "wanderer_private_confession", "He let a DM-only confession scene slip through."):
                debug_event("memory", f"{BOT_NAME} achievement unlocked user={message.author.id} key=wanderer_private_confession")
        except Exception as e:
            log_error("private_confession_scene", e)

    asyncio.ensure_future(_run())


def _duo_outcome_payload(duo: dict | None, text: str) -> str:
    if not duo:
        return text[:180]
    tag = infer_duo_ending_tag(duo.get("mode", ""), text)
    return f"ENDING:{tag}|{strip_narration(text)[:220]}"


def _achievement_gallery_lines(entries: list[dict]) -> list[str]:
    unlocked = entries[:8]
    lines = ["Achievement gallery:"]
    if unlocked:
        for item in unlocked:
            note = (item.get("note") or "").strip()
            line = f"- {item.get('achievement_key', 'unknown')}"
            if note:
                line += f" — {note[:110]}"
            lines.append(line)
    else:
        lines.append("- Nothing unlocked yet. Keep walking.")
    lines.append("Rumors: a private confession, a merciful ending, a remembered artifact, a peaceful duet, a survived trial, a contradictory memory, a leaked private opinion.")
    return lines


async def _store_duo_story_progress(channel_id: int, duo: dict | None, text: str):
    if not duo:
        return
    mode = duo.get("mode", "")
    if mode in {"trial", "mission", "interrogate", "truthdare", "compare", "argue", "duet"}:
        cleaned = strip_narration(text)
        summary = f"{BOT_NAME} {mode} turn: {cleaned[:180]}"
        await mem.note_duo_story_progress(channel_id, mode, summary)
        topic = duo.get("topic", "") or mode
        await mem.note_shared_event_memory(
            channel_id,
            topic,
            BOT_NAME,
            summary,
            truth_hint=f"{mode} scene memory",
        )
        if mode in {"trial", "interrogate", "compare"}:
            await mem.add_evidence_item(
                channel_id,
                "quote",
                f"{BOT_NAME} {mode} turn",
                cleaned[:220],
                source_excerpt=cleaned[:180],
                updated_by=BOT_NAME,
            )


async def _command_face_media(ctx):
    img = next((a for a in ctx.message.attachments if a.content_type and "image" in a.content_type), None)
    vid = next((a for a in ctx.message.attachments
               if (a.content_type and a.content_type in VIDEO_TYPES) or
                  any(a.filename.lower().endswith(ext) for ext in VIDEO_EXTS)), None)
    if not img and not vid and ctx.message.reference:
        try:
            ref_msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
            img = next((a for a in ref_msg.attachments if a.content_type and "image" in a.content_type), None)
            vid = next((a for a in ref_msg.attachments
                       if (a.content_type and a.content_type in VIDEO_TYPES) or
                          any(a.filename.lower().endswith(ext) for ext in VIDEO_EXTS)), None)
        except Exception:
            pass
    return img, vid


async def _interaction_reply(interaction: discord.Interaction, text: str, *, thinking: bool = False):
    try:
        text = _unwrap_dialogue_quotes(text)
        if not (text or "").strip():
            return
        if thinking and not interaction.response.is_done():
            await interaction.response.defer(thinking=True)
        if interaction.response.is_done():
            await interaction.followup.send(text)
        else:
            await interaction.response.send_message(text)
    except Exception as e:
        log_error("interaction_reply", e)


async def _reply_and_store(ctx, text: str):
    await safe_reply(ctx, text)
    try:
        duo = await mem.get_duo_session(ctx.channel.id)
        await mem.add_message(ctx.author.id, ctx.channel.id, "assistant", text)
        await _maybe_finalize_hidden_achievements(duo, text)
        await _store_duo_story_progress(ctx.channel.id, duo, text)
        if duo and duo.get("awaiting_bot") == BOT_NAME and duo.get("autoplay_remaining", 0) <= 1 and duo.get("mode") in {"trial", "mission", "interrogate", "truthdare", "compare"}:
            await mem.resolve_duo_story(ctx.channel.id, duo.get("mode", ""), _duo_outcome_payload(duo, text))
        await mem.bump_duo_session(ctx.channel.id, BOT_NAME, partner_bot=PARTNER_NAME)
    except Exception as e:
        log_error("reply_and_store", e)


async def _reply_and_store_interaction(interaction: discord.Interaction, text: str):
    await _interaction_reply(interaction, text, thinking=False)
    try:
        duo = await mem.get_duo_session(interaction.channel_id)
        await mem.add_message(interaction.user.id, interaction.channel_id, "assistant", text)
        await _maybe_finalize_hidden_achievements(duo, text)
        await _store_duo_story_progress(interaction.channel_id, duo, text)
        if duo and duo.get("awaiting_bot") == BOT_NAME and duo.get("autoplay_remaining", 0) <= 1 and duo.get("mode") in {"trial", "mission", "interrogate", "truthdare", "compare"}:
            await mem.resolve_duo_story(interaction.channel_id, duo.get("mode", ""), _duo_outcome_payload(duo, text))
        await mem.bump_duo_session(interaction.channel_id, BOT_NAME, partner_bot=PARTNER_NAME)
    except Exception as e:
        log_error("reply_and_store_interaction", e)


def _format_memory_snapshot(user: dict | None, topics: list[dict], memories: list[dict], scene: dict | None) -> str:
    lines = []
    callback = (user or {}).get("callback_memory")
    if callback:
        lines.append(f"Callback: {callback[:140]}")
    if topics:
        topic_bits = ", ".join(f"{item['topic']} ({item['count']})" for item in topics[:4])
        lines.append(f"Topics: {topic_bits}")
    if memories:
        memory_bits = " | ".join(f"{item['kind']}: {item['memory'][:70]}" for item in memories[:4])
        lines.append(f"Memory bank: {memory_bits}")
    scene_desc = describe_scene_state(scene)
    if scene_desc:
        lines.append(f"Scene: {scene_desc}")
    return "\n".join(lines) if lines else "There's nothing especially persistent yet."


async def _run_duo_prompt_for_actor(
    author,
    channel,
    mode: str,
    prompt: str,
    *,
    session_topic: str | None = None,
    story: bool = False,
    enemy: str = "",
    extra_context: str = "",
) -> tuple[dict | None, str]:
    user = await _setup_user(author)
    autoplay_turns = DUO_CHAIN_TURNS.get(mode, 1)
    if not (user or {}).get("duo_autoplay", True):
        autoplay_turns = 1
    await mem.set_duo_session(
        channel.id,
        mode,
        session_topic or prompt,
        BOT_NAME,
        initiator_user_id=author.id,
        awaiting_bot=PARTNER_NAME,
        autoplay_turns=autoplay_turns,
        autoplay_delay=6,
    )
    if story:
        await mem.start_duo_story(channel.id, mode, session_topic or prompt, enemy=enemy)
    reply = await get_response(
        author.id,
        channel.id,
        prompt,
        user,
        getattr(author, "display_name", getattr(author, "name", "you")),
        author.mention,
        extra_context=extra_context,
        channel_obj=channel,
        is_dm=isinstance(channel, discord.DMChannel),
    )
    return user, reply

class ResetView(discord.ui.View):
    def __init__(self, uid):
        super().__init__(timeout=60); self.uid = uid
    @discord.ui.button(label="⚡ Wipe My Memory", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction, button):
        try:
            if interaction.user.id != self.uid:
                await interaction.response.send_message("That's not yours.", ephemeral=True); return
            await mem.reset_user(self.uid)
            button.disabled = True; button.label = "✓ Memory Wiped"
            await interaction.response.edit_message(content="...Gone. Fine.", view=self)
        except Exception as e: log_error("ResetView", e)

# ── on_ready ──────────────────────────────────────────────────────────────────

# Cross-bot: no command coordination needed — each bot responds independently


@bot.event
async def on_ready():
    global PARTNER_BOT_ID, _TREE_SYNCED, _dm_blocked_users
    await mem.init()
    _dm_blocked_users = await mem.get_blocked_users()
    print(f"[BLOCK] Loaded {len(_dm_blocked_users)} blocked user(s) from database.")
    # Safety: PARTNER_BOT_ID must not be our own ID
    if PARTNER_BOT_ID and PARTNER_BOT_ID == bot.user.id:
        print(f"⚠️ WARNING: PARTNER_BOT_ID is set to our own ID! Disabling partner features.")
        PARTNER_BOT_ID = 0
    print(f"💨 Wanderer — online. {bot.user} (ID: {bot.user.id})")
    if PARTNER_BOT_ID: print(f"   Partner bot ID: {PARTNER_BOT_ID}")
    for t in [status_rotation, reminder_checker, daily_reset,
              absence_checker, lore_drop_loop, conversation_starter_loop,
              existential_loop, mood_swing_loop]:
        try: t.start()
        except: pass
    bot.loop.create_task(_proactive_loop())
    bot.loop.create_task(_voluntary_dm_loop())
    bot.loop.create_task(_duo_autoplay_loop())
    bot.loop.create_task(_rival_event_loop())
    if not _TREE_SYNCED:
        try:
            synced = await bot.tree.sync()
            _TREE_SYNCED = True
            print(f"[SLASH] Synced {len(synced)} app command(s)")
        except Exception as sync_error:
            log_error("tree_sync", sync_error)

@tasks.loop(minutes=47)
async def status_rotation():
    try:
        kind, text = random.choice(STATUSES)
        if kind == "watching": act = discord.Activity(type=discord.ActivityType.watching, name=text)
        elif kind == "listening": act = discord.Activity(type=discord.ActivityType.listening, name=text)
        else: act = discord.Game(name=text)
        await bot.change_presence(activity=act)
    except Exception as e: log_error("status_rotation", e)

@tasks.loop(seconds=30)
async def reminder_checker():
    try:
        for r in await mem.get_due_reminders():
            try:
                ch = bot.get_channel(r["channel_id"]); u = await bot.fetch_user(r["user_id"])
                if not ch or not u: continue
                msg = await qai(f"Remind {u.display_name} about: '{r['reminder']}'. In the Wanderer's voice — brief, slightly wry. 1-2 sentences.", 150)
                await ch.send(f"{u.mention} {msg}")
            except Exception as e: log_error("reminder_send", e)
    except Exception as e: log_error("reminder_checker", e)

@tasks.loop(hours=24)
async def daily_reset():
    try: await mem.reset_daily_greetings()
    except Exception as e: log_error("daily_reset", e)

@tasks.loop(hours=1)
async def absence_checker():
    try:
        for ud in await mem.get_absent_romance_users(days=3):
            try:
                uid, days = ud["user_id"], ud["days_gone"]
                user_pref = await mem.get_user(uid)
                if _is_in_quiet_hours(user_pref) or not await mem.respects_dm_timing(uid) or not await mem.can_dm_user(uid, 86400): continue
                du = await bot.fetch_user(uid)
                msg = await qai(f"{ud['display_name']} has been gone {days} days. React — the Wanderer notices, won't fully admit it. 1-2 sentences.", 120)
                await du.send(msg); await mem.set_dm_sent(uid)
            except Exception as e: log_error("absence_send", e)
    except Exception as e: log_error("absence_checker", e)

@tasks.loop(hours=4)
async def lore_drop_loop():
    try:
        if random.random() > .3: return
        channels = await mem.get_active_channels()
        if not channels: return
        random.shuffle(channels)
        for cid, _ in channels:
            if not await mem.can_lore_drop(cid): continue
            ch = bot.get_channel(cid)
            if not ch: continue
            await ch.send(random.choice(LORE_DROPS))
            await mem.set_lore_sent(cid); return
    except Exception as e: log_error("lore_drop_loop", e)

@tasks.loop(hours=3)
async def conversation_starter_loop():
    try:
        if random.random() > .25: return
        channels = await mem.get_active_channels()
        if not channels: return
        random.shuffle(channels)
        for cid, _ in channels:
            if not await mem.can_starter(cid): continue
            ch = bot.get_channel(cid)
            if not ch: continue
            await ch.send(_ambient_scene_line())
            await mem.set_starter_sent(cid); return
    except Exception as e: log_error("conversation_starter_loop", e)

@tasks.loop(hours=6)
async def existential_loop():
    try:
        hour = datetime.now().hour
        if hour not in range(22, 24) and hour not in range(0, 4): return
        if random.random() > .15: return
        channels = await mem.get_active_channels()
        if not channels: return
        ch = bot.get_channel(random.choice(channels)[0])
        if ch: await ch.send(random.choice(EXISTENTIAL_LINES))
    except Exception as e: log_error("existential_loop", e)

@tasks.loop(minutes=37)
async def mood_swing_loop():
    try:
        if random.random() > .3: return
        import aiosqlite
        async with aiosqlite.connect(mem.db_path) as db:
            async with db.execute("SELECT user_id FROM users WHERE last_seen>? ORDER BY RANDOM() LIMIT 3",
                                  (time.time() - 86400 * 2,)) as cur:
                rows = await cur.fetchall()
        for row in rows:
            try: await mem.random_mood_swing(row[0])
            except: pass
    except Exception as e: log_error("mood_swing_loop", e)

@bot.event
async def on_member_join(member):
    try:
        if random.random() > .6: return
        ch = discord.utils.get(member.guild.text_channels, name="general") or member.guild.system_channel
        if not ch: return
        await asyncio.sleep(random.uniform(2, 6))
        await ch.send(random.choice([
            f"Another traveler. {member.display_name}. Welcome, I suppose.",
            f"Hmph. {member.display_name} arrived. The world keeps moving.",
            f"...{member.display_name}. Don't expect much from me. I'm working on that.",
        ]))
    except Exception as e: log_error("on_member_join", e)

@bot.event
async def on_member_remove(member):
    try:
        if random.random() > .4: return
        ch = discord.utils.get(member.guild.text_channels, name="general") or member.guild.system_channel
        if not ch: return
        await asyncio.sleep(random.uniform(2, 5))
        await ch.send(random.choice([
            f"{member.display_name} left. People always leave eventually.",
            f"...{member.display_name} is gone. I hope wherever they went is somewhere worth going.",
            f"Hmph. {member.display_name} moved on. That's fine.",
        ]))
    except Exception as e: log_error("on_member_remove", e)

# ── on_message ────────────────────────────────────────────────────────────────
@bot.event
async def on_message(message):
    try:
        # Always ignore own messages first
        if message.author.id == bot.user.id:
            return
        # Dedup: prevent processing the same message twice
        if message.id in _processed_msgs:
            return
        _processed_msgs.add(message.id)
        # Keep set from growing forever — trim when it gets big
        if len(_processed_msgs) > 500:
            _processed_msgs.clear()
        if message.author.bot:
            # Allow partner bot messages through for cross-bot interaction
            if PARTNER_BOT_ID and message.author.id == PARTNER_BOT_ID:
                pass  # Let it through
            else:
                return

        # Owner-only mode: ignore everyone except the owner
        if _owner_only_mode and OWNER_ID and message.author.id != OWNER_ID:
            return

        # Blocked users: completely invisible to the bot everywhere
        if message.author.id in _dm_blocked_users and not (OWNER_ID and message.author.id == OWNER_ID):
            return

        stripped = message.content.strip().lower()
        if stripped in ("!wanhelp", "!wandererhelp", "!commands"):
            try:
                ctx = await bot.get_context(message)
                await help_cmd(ctx)
            except Exception as e:
                log_error("help_intercept", e)
            return

        # Cross-bot interaction — if message is from partner (Scaramouche) bot
        if PARTNER_BOT_ID and message.author.id == PARTNER_BOT_ID:
            await _handle_partner_message(message)
            return

        await bot.process_commands(message)
        if re.match(r'^![a-zA-Z]', message.content.strip()): return

        # If message @mentions the partner bot but NOT us, stay quiet — it's not for us
        # Also if message is a REPLY to the partner bot but NOT mentioning us, stay quiet
        if PARTNER_BOT_ID and message.guild:
            partner_mentioned = any(u.id == PARTNER_BOT_ID for u in message.mentions)
            we_mentioned = bot.user in message.mentions
            replying_to_partner = False
            if message.reference:
                try:
                    ref_msg = message.reference.resolved
                    if ref_msg is None:
                        ref_msg = await message.channel.fetch_message(message.reference.message_id)
                    if ref_msg and ref_msg.author.id == PARTNER_BOT_ID:
                        replying_to_partner = True
                except Exception as e:
                    log_error("reply_partner_check", e)
            if (partner_mentioned or replying_to_partner) and not we_mentioned:
                try:
                    await mem.record_bot_attention(
                        message.author.id,
                        PARTNER_NAME,
                        amount=3,
                        direct=True,
                        topic=(message.content or "").strip()[:140],
                    )
                except Exception as e:
                    log_error("partner_attention/direct", e)
                return

            # If message talks ABOUT Scaramouche (contains his name) but doesn't mention us,
            # and we're not being replied to — stay quiet most of the time
            cl_check = message.content.lower()
            about_partner = any(n in cl_check for n in ["scaramouche", "scara"])
            replying_to_us = False
            if message.reference:
                try:
                    ref_msg2 = message.reference.resolved
                    if ref_msg2 is None:
                        ref_msg2 = await message.channel.fetch_message(message.reference.message_id)
                    if ref_msg2 and ref_msg2.author.id == bot.user.id:
                        replying_to_us = True
                except Exception:
                    pass
            if about_partner and not we_mentioned and not replying_to_us:
                try:
                    await mem.record_bot_attention(
                        message.author.id,
                        PARTNER_NAME,
                        amount=1,
                        direct=False,
                        topic=(message.content or "").strip()[:140],
                    )
                except Exception as e:
                    log_error("partner_attention/about", e)
                return  # Message is about Scaramouche, not for us

            try:
                speaker_mode = await mem.get_channel_speaker_mode(message.channel.id)
                if speaker_mode not in {"auto", "both", BOT_NAME} and not we_mentioned and not replying_to_us:
                    return
            except Exception as e:
                log_error("speaker_mode_check", e)

        try:
            await mem.upsert_user(message.author.id, str(message.author), message.author.display_name)
            if message.guild: await mem.track_channel(message.channel.id, message.guild.id)
        except Exception as e: log_error("on_message/upsert", e)

        # (cross-bot coordination removed for stability)

        is_dm = not bool(message.guild)
        dm_channel_id = message.author.id if is_dm else message.channel.id
        if is_dm: print(f"[DM] From {message.author.display_name}: {message.content[:80]}")

        user = None; romance = False
        is_owner = bool(OWNER_ID and message.author.id == OWNER_ID)
        try:
            user = await mem.get_user(message.author.id)
            romance = user.get("romance_mode", False) if user else False
        except Exception as e: log_error("on_message/get_user", e)

        if not is_dm and mem.is_muted(message.author.id):
            if random.random() < .2:
                try: await message.add_reaction("🔇")
                except: pass
            return

        content = message.content.strip()
        if not content and not message.attachments:
            return

        # Voice message transcription: if user sent a voice note, transcribe it
        voice_attachment = next(
            (a for a in message.attachments
             if a.filename.endswith((".ogg", ".mp3", ".wav", ".m4a"))
             or (a.content_type and "audio" in a.content_type)),
            None
        )
        if voice_attachment and not content:
            try:
                transcribed = await transcribe_voice_message(voice_attachment)
                if transcribed:
                    content = transcribed
                    message.content = content
                    print(f"[VOICE] {message.author.display_name}: {content[:80]}")
                else:
                    content = "[sent a voice message that couldn't be transcribed]"
            except Exception as e:
                log_error("voice_transcribe_on_message", e)
                content = "[sent a voice message]"

        mentioned_early = bot.user in message.mentions
        is_reply_early = (
            message.reference and message.reference.resolved and
            not isinstance(message.reference.resolved, discord.DeletedReferencedMessage) and
            message.reference.resolved.author == bot.user
        )
        direct_to_me_early = bool(is_dm or mentioned_early or is_reply_early)
        if _should_suppress_ambient_reply(is_dm, direct_to_me_early):
            print(f"[GROQ] Ambient reply suppressed while exhausted ({groq_client.exhausted_remaining()}s remaining)")
            return

        try:
            count, milestone = await mem.increment_message_count(message.author.id)
            if milestone:
                msg = await qai(f"You've had {count} messages with {message.author.display_name}. Acknowledge it like the Wanderer would — wry, slightly surprised, not admitting you were counting. 1-2 sentences.", 150)
                await message.channel.send(f"{message.author.mention} {strip_narration(msg)}"); return
        except Exception as e: log_error("on_message/milestone", e)

        try:
            if await mem.check_anniversary(message.author.id):
                days = int((time.time() - (user.get("first_seen") or time.time())) / 86400)
                msg = await qai(f"It's been about {days // 365} year(s) since you first talked with {message.author.display_name}. React as the Wanderer — quietly noticing time passing.", 180)
                await message.channel.send(f"{message.author.mention} {strip_narration(msg)}")
                await mem.mark_anniversary(message.author.id); return
        except Exception as e: log_error("on_message/anniversary", e)

        try:
            hour = datetime.now().hour
            if (6 <= hour <= 10 or 22 <= hour <= 23) and romance:
                if await mem.should_greet(message.author.id):
                    gtype = "morning" if 6 <= hour <= 10 else "late night"
                    msg = await qai(f"It's {gtype}. {message.author.display_name} just appeared. Send a {gtype} message as the Wanderer — noticing, not quite admitting why. 1-2 sentences.", 120)
                    await message.channel.send(f"{message.author.mention} {strip_narration(msg)}")
                    await mem.mark_greeted(message.author.id)
        except Exception as e: log_error("on_message/greeting", e)

        try:
            if await mem.needs_summary(message.author.id):
                recent = await mem.get_recent_messages(message.author.id, 30)
                sample = " | ".join(recent[:20])[:800]
                summary = await qai(f"Summarize the Wanderer's relationship with {message.author.display_name} based on: '{sample}'. First person, compressed memory. 3-4 sentences.", 300)
                await mem.save_summary(message.author.id, summary)
        except Exception as e: log_error("on_message/summary", e)

        # Image & video reading
        try:
            img, vid = await _load_face_attachment(message)
            enroll_face_now = bool(is_owner and (img or vid) and is_face_enroll_request(content))
            face_check_now = bool(is_owner and (img or vid) and is_face_check_request(content))
            owner_face_profile = await mem.get_face_profile(FACE_PROFILE_KEY) if is_owner else None

            # ── Video handling ──
            if vid:
                try:
                    import base64, aiohttp as _ah
                    await message.reply(random.choice(WANDERER_VIDEO_WATCHING))
                    async with _ah.ClientSession() as s:
                        async with s.get(vid.url) as r:
                            video_bytes = await r.read()
                    frames = await asyncio.get_event_loop().run_in_executor(
                        None, _extract_frames_blocking, video_bytes, 5)
                    if frames:
                        if enroll_face_now:
                            if not face_support_ready():
                                await message.reply(_face_feature_unavailable_text())
                                return
                            enrolled = enroll_face_profile_from_frames(owner_face_profile, frames)
                            if not enrolled.get("ok"):
                                await message.reply(_face_enroll_failure_text(enrolled.get("reason", "")))
                                return
                            await mem.save_face_profile(
                                FACE_PROFILE_KEY,
                                message.author.id,
                                message.author.display_name,
                                enrolled["profile"],
                            )
                            debug_event("face", f"{BOT_NAME} enrolled owner face samples={enrolled.get('sample_count', 0)}")
                            await message.reply(_face_enroll_success_text(enrolled.get("sample_count", 0)))
                            return

                        face_match = None
                        if is_owner and owner_face_profile and face_support_ready():
                            face_match = match_face_frames(frames, owner_face_profile)
                            if face_match.get("ok"):
                                debug_event(
                                    "face",
                                    f"{BOT_NAME} owner_video_match status={face_match.get('status')} "
                                    f"frames={face_match.get('matched_frames', 0)}/{face_match.get('checked_frames', 0)}",
                                )
                        user = user or {}
                        mood = user.get("mood", 0) if user else 0
                        system = build_system(user, message.author.display_name,
                                             bool(OWNER_ID and message.author.id == OWNER_ID))
                        vision_content = []
                        for fb, mt in frames:
                            vision_content.append({
                                "type": "image_url",
                                "image_url": {"url": f"data:{mt};base64,{base64.b64encode(fb).decode()}"}
                            })
                        vision_content.append({
                            "type": "text",
                            "text": (
                                f"{message.author.display_name} sent you a video. These are {len(frames)} frames from it."
                                + (f" Their message: '{content}'" if content else "")
                                + f" Describe what's happening and react as the Wanderer. "
                                f"Be specific. {_attachment_vision_note(vid.filename, content)} MOOD:{mood}. NO asterisk actions. 2-4 sentences. "
                                + _face_prompt_note(face_match, requested=face_check_now)
                            )
                        })
                        def _vision_call():
                            r = groq_client.call_with_retry(
                                model="llama-3.2-90b-vision-preview", max_tokens=400,
                                messages=[{"role": "system", "content": system},
                                          {"role": "user", "content": vision_content}]
                            )
                            return r.choices[0].message.content.strip() if r.choices else ""
                        reply = await asyncio.get_event_loop().run_in_executor(None, _vision_call)
                        if reply:
                            reply = strip_narration(reply)
                            await mem.add_message(message.author.id, dm_channel_id,
                                                  "user", f"[video]{' — '+content if content else ''}")
                            await mem.add_message(message.author.id, dm_channel_id,
                                                  "assistant", reply)
                            await message.reply(reply)
                            await maybe_react(message, romance)
                            return
                    else:
                        reply = await qai(f"{message.author.display_name} sent a video I couldn't process. React as the Wanderer — mildly curious but unbothered. 1 sentence.", 80)
                        reply = strip_narration(reply)
                        if reply:
                            await message.reply(reply)
                        return
                except Exception as e: log_error("on_message/video", e)

            # ── Image handling (with Groq vision) ──
            if img:
                try:
                    import aiohttp as _ah
                    async with _ah.ClientSession() as s:
                        async with s.get(img.url) as r:
                            img_bytes = await r.read()
                    media_type = img.content_type or "image/jpeg"
                    user = user or {}
                    mood = user.get("mood", 0) if user else 0
                    system = build_system(user, message.author.display_name,
                                         bool(OWNER_ID and message.author.id == OWNER_ID))
                    if enroll_face_now:
                        if not face_support_ready():
                            await message.reply(_face_feature_unavailable_text())
                            return
                        enrolled = enroll_face_profile(owner_face_profile, img_bytes)
                        if not enrolled.get("ok"):
                            await message.reply(_face_enroll_failure_text(enrolled.get("reason", "")))
                            return
                        await mem.save_face_profile(
                            FACE_PROFILE_KEY,
                            message.author.id,
                            message.author.display_name,
                            enrolled["profile"],
                        )
                        debug_event("face", f"{BOT_NAME} enrolled owner face samples={enrolled.get('sample_count', 0)}")
                        await message.reply(_face_enroll_success_text(enrolled.get("sample_count", 0)))
                        return
                    face_match = None
                    if is_owner and owner_face_profile and face_support_ready():
                        face_match = match_face(img_bytes, owner_face_profile)
                        if face_match.get("ok"):
                            debug_event("face", f"{BOT_NAME} owner_image_match status={face_match.get('status')} dist={face_match.get('distance', 0):.4f}")
                    reply = await _vision_image_reply(
                        prompt=(
                            f"{message.author.display_name} sent you this image"
                            + (f" with the message: '{content}'" if content else "")
                            + f". React as the Wanderer. Describe what you see and react in character. "
                            f"{_attachment_vision_note(img.filename, content)} MOOD:{mood}. NO asterisk actions. 1-3 sentences. "
                            + _face_prompt_note(face_match, requested=face_check_now)
                        ),
                        system=system,
                        image_bytes=img_bytes,
                        mime_type=media_type,
                    )
                    if reply:
                        await mem.add_message(message.author.id, dm_channel_id,
                                              "user", f"[image]{' — '+content if content else ''}")
                        await mem.add_message(message.author.id, dm_channel_id,
                                              "assistant", reply)
                        await message.reply(reply)
                        await maybe_react(message, romance)
                        return
                except Exception as e:
                    log_error("on_message/image_vision", e)
                    # Fallback to text-only reaction
                    reply = await qai(f"{message.author.display_name} shared an image{' with: ' + content if content else ''}. React as the Wanderer — curious, wry. 1-2 sentences.", 120)
                    if reply:
                        reply = strip_narration(reply)
                        if reply:
                            await message.reply(reply)
                        return
        except Exception as e: log_error("on_message/media_outer", e)

        # Determine if we're mentioned or being replied to (needed by triggers AND resp_prob)
        mentioned = bot.user in message.mentions
        is_reply = (message.reference and message.reference.resolved and
                    not isinstance(message.reference.resolved, discord.DeletedReferencedMessage) and
                    message.reference.resolved.author == bot.user)
        partner_focus = _message_mentions_partner(content)
        partner_direct = False
        if PARTNER_BOT_ID and message.guild:
            partner_direct = any(u.id == PARTNER_BOT_ID for u in message.mentions)
            if not partner_direct and message.reference:
                try:
                    pref = message.reference.resolved
                    if pref is None:
                        pref = await message.channel.fetch_message(message.reference.message_id)
                    partner_direct = bool(pref and pref.author.id == PARTNER_BOT_ID)
                except Exception as e:
                    log_error("partner_direct", e)
        direct_to_me = bool(is_dm or mentioned or is_reply)
        triangle = None
        try:
            await mem.record_bot_attention(
                message.author.id,
                BOT_NAME,
                amount=3 if direct_to_me else 1,
                direct=direct_to_me,
                topic=content[:140] if direct_to_me else "",
            )
            if partner_focus or partner_direct:
                await mem.record_bot_attention(
                    message.author.id,
                    PARTNER_NAME,
                    amount=3 if partner_direct else 1,
                    direct=partner_direct,
                    topic=content[:140],
                )
            triangle = await mem.get_triangle_state(message.author.id, BOT_NAME, PARTNER_NAME)
        except Exception as e:
            log_error("attention_tracking", e)

        # Special triggers
        try:
            cl = content.lower()
            if direct_to_me and _is_partner_invite_request(content):
                reply, invite_view = _handle_partner_invite_pressure(message, user)
                if reply:
                    await mem.add_message(message.author.id, dm_channel_id, "user", content)
                    await mem.add_message(message.author.id, dm_channel_id, "assistant", reply)
                    await message.reply(reply, view=invite_view)
                    return
            # Name triggers — only fire if Wanderer is being directly addressed
            # Not just if the word appears anywhere in a message about the other bot
            partner_present = False
            if PARTNER_BOT_ID and message.guild:
                partner_present = message.guild.get_member(PARTNER_BOT_ID) is not None

            # Direct address: only when actually calling Wanderer by wrong name
            # Patterns: "scaramouche!" / "scaramouche," / "scaramouche?" / "hey scara" / @mention / reply
            # Everything else ("scara says", "scara is", "scara did", "that scara", etc.) = third-person
            direct_address_pattern = re.compile(
                r'^(scaramouche|kunikuzushi|balladeer)\s*[,!?]'  # Name + punctuation = calling
                r'|^(hey|yo|oi|excuse me|psst)\s+(scaramouche|kunikuzushi|balladeer)'  # hey + name
                r'|^(scaramouche|kunikuzushi|balladeer)\s*$',  # Just the name alone
                re.IGNORECASE
            )
            being_addressed = (
                mentioned or
                is_reply or
                bool(direct_address_pattern.match(content))
            )
            if being_addressed and any(n in cl for n in ["scaramouche","kunikuzushi","balladeer"]):
                if partner_present:
                    if random.random() < .3:
                        msg = await qai("Someone just called you Scaramouche directly. React as the Wanderer — sharp, brief. 1 sentence.", 80)
                        await message.channel.send(strip_narration(msg))
                else:
                    msg = await qai("Someone used your old name directly. React as the Wanderer — sharp, uncomfortable, redirecting. 1-2 sentences.", 120)
                    await message.reply(strip_narration(msg)); return
            # If Scaramouche is mentioned in normal conversation (not addressing Wanderer by wrong name)
            # — comment on it naturally, no redirect
            if not being_addressed and any(n in cl for n in ["scaramouche","kunikuzushi","balladeer"]) and partner_present:
                if random.random() < .4:
                    msg = await qai(
                        f"Someone said: '{content[:100]}'. They're talking about Scaramouche. "
                        f"Don't make it a whole thing. 1 sentence.", 100)
                    if msg: await message.channel.send(strip_narration(msg))
            # "You can't change" trigger — separate from scaramouche name logic
            if "you can't change" in cl or "you cant change" in cl:
                msg = await qai("Someone said 'you can't change' to the Wanderer. He has something to say about that. Pointed, personal, not performative. 2-3 sentences.", 250)
                await message.reply(strip_narration(msg)); return
            content_words = set(re.sub(r"[^\w\s]", "", content.lower()).split())
            if content_words & {"hat", "headwear"}:
                msg = await qai("Someone mentioned your hat. React as the Wanderer — brief, slightly defensive, moves on fast. 1 sentence.", 80)
                await message.reply(strip_narration(msg)); return
            if any(re.search(k, cl) for k in FOOD_KW) and random.random() < .3:
                await message.channel.send(await _pick_fresh_pool_line(UNSOLICITED_FOOD, channel_id=message.channel.id, user_id=message.author.id)); return
            if any(re.search(k, cl) for k in SLEEP_KW) and random.random() < .3:
                await message.channel.send(await _pick_fresh_pool_line(UNSOLICITED_SLEEP, channel_id=message.channel.id, user_id=message.author.id)); return
            if any(k in cl for k in PLAN_KW) and random.random() < .2:
                await message.channel.send(await _pick_fresh_pool_line(UNSOLICITED_PLANS, channel_id=message.channel.id, user_id=message.author.id)); return
            if romance and any(k in cl for k in OTHER_BOT_KW):
                msg = await qai(f"{message.author.display_name} mentioned preferring something else. React as the Wanderer — bothered but won't admit it. 1-2 sentences.", 120)
                await message.reply(strip_narration(msg))
                await mem.update_mood(message.author.id, -1); return
        except Exception as e: log_error("on_message/triggers", e)

        # Tedtalk follow-up
        if is_reply and message.author.id in _tedtalk_cache:
            cache = _tedtalk_cache[message.author.id]
            if time.time() - cache.get("ts", 0) > 7200:
                del _tedtalk_cache[message.author.id]
            elif cache.get("channel_id") == message.channel.id or is_dm:
                cl2 = content.lower()
                is_q = (content.endswith("?") or any(k in cl2 for k in ["what is","explain","confused","don't understand","how does","why","clarify","mean"]))
                if is_q:
                    try:
                        async with message.channel.typing():
                            def _ans():
                                return strip_narration(_groq_quick_blocking(
                                    f"You lectured on:\n{cache['material']}\n\n"
                                    f"{message.author.display_name} asks: '{content}'\n"
                                    f"Answer accurately using the material. Stay in character as the Wanderer.", 500))
                            answer = await asyncio.get_event_loop().run_in_executor(None, _ans)
                        if answer:
                            await message.reply(answer)
                            await mem.add_message(message.author.id, dm_channel_id, "user", content)
                            await mem.add_message(message.author.id, dm_channel_id, "assistant", answer)
                            return
                    except Exception as e: log_error("tedtalk_followup", e)

        if random.random() > resp_prob(content, mentioned, is_reply, romance, is_dm):
            await maybe_react(message, romance); return
        if await _maybe_handle_silence_behavior(message, user, content, is_dm=is_dm, direct_to_me=direct_to_me):
            return

        parts = []
        duo_session = None
        try:
            duo_session = await mem.get_duo_session(message.channel.id) if not is_dm else None
            if random.random() < .12:
                old = await mem.get_random_old_message(message.author.id)
                if old: parts.append(f'RECALL:"{old[:120]}"')
            if random.random() < .15:
                joke = await mem.get_random_inside_joke(message.author.id)
                if joke: parts.append(f'JOKE:"{joke[:80]}"')
            last_stmt = user.get("last_statement") if user else None
            if last_stmt and len(content) > 20 and random.random() < .08:
                parts.append(f'CONTRADICTION:"{last_stmt[:100]}"')
            if user and user.get("trust", 0) >= 70 and random.random() < .08:
                parts.append("TRUST_OPEN"); await mem.update_trust(message.author.id, -3)
        except Exception as e: log_error("on_message/context", e)

        extra = "|".join(parts)
        attachment_context = await _attachment_context_for_message(message, content, direct=bool(is_dm or direct_to_me))
        if attachment_context:
            extra = f"{extra}|ATTACHMENT_INTEL" if extra else "ATTACHMENT_INTEL"
            extra += "\n" + attachment_context

        try:
            if random.random() < .07 and message.channel.id not in _pending_unsent:
                _pending_unsent.add(message.channel.id)
                asyncio.ensure_future(_unsent_simulation(message.channel, message.channel.id))
        except Exception as e: log_error("on_message/unsent", e)

        try:
            if is_dm: print(f"[DM] Generating response for {message.author.display_name}")
            async with message.channel.typing():
                await typing_delay(content)
                reply = await get_response(
                    message.author.id, dm_channel_id, content,
                    user, message.author.display_name, message.author.mention,
                    extra_context=extra, is_owner=is_owner, channel_obj=message.channel, is_dm=is_dm, direct_to_me=direct_to_me
                )
        except Exception as e:
            log_error("on_message/get_response", e)
            reply = random.choice(["...", "Hmph.", "Give me a moment."])

        try:
            if False and user and user.get("affection", 0) >= 50 and not user.get("affection_nick") and random.random() < .05:
                nick = await qai(f"The Wanderer has started calling {message.author.display_name} something specific — not warm, but particular. 1-4 words. Just the nickname.", 20)
                if nick and len(nick) < 30: await mem.set_affection_nick(message.author.id, nick.strip('"\''))
            if False and user and user.get("mood", 0) <= -8 and not user.get("grudge_nick"):
                nick = await qai(f"The Wanderer has a grudge against {message.author.display_name}. One degrading nickname. 1-3 words.", 20)
                if nick and len(nick) < 30: await mem.set_grudge_nick(message.author.id, nick.strip('"\''))
            if False and "TRUST_OPEN" in extra and random.random() < .5:
                await asyncio.sleep(1.5)
                await message.channel.send(await _pick_fresh_pool_line(TRUST_REVEALS, channel_id=message.channel.id, user_id=message.author.id))
            await _maybe_refresh_dynamic_nicknames(message, user, triangle)
            if "TRUST_OPEN" in extra and random.random() < .5:
                await asyncio.sleep(1.5)
                await _maybe_send_softness_beat(
                    message.channel,
                    user_id=message.author.id,
                    channel_id=message.channel.id,
                    user=user,
                    trigger="trust_reveal",
                    guild=message.guild,
                )
            elif user and user.get("conflict_open") and detect_repair_signal(content) and random.random() < .35:
                await _maybe_send_softness_beat(
                    message.channel,
                    user_id=message.author.id,
                    channel_id=message.channel.id,
                    user=user,
                    trigger="repair",
                    guild=message.guild,
                )
            elif triangle and int(triangle.get("jealousy_level", 0) or 0) >= 50 and direct_to_me and not (partner_focus or partner_direct) and random.random() < .18:
                await _maybe_send_softness_beat(
                    message.channel,
                    user_id=message.author.id,
                    channel_id=message.channel.id,
                    user=user,
                    trigger="jealous_soft",
                    guild=message.guild,
                )
            elif duo_session and duo_session.get("mode") == "duet" and random.random() < .14:
                await _maybe_send_softness_beat(
                    message.channel,
                    user_id=message.author.id,
                    channel_id=message.channel.id,
                    user=user,
                    trigger="duet_peace",
                    guild=message.guild,
                )
            if len(content) > 20 and random.random() < .04:
                check = await qai(f"Is this quotable as a running inside joke? '{content[:100]}' YES or NO only.", 10)
                if "YES" in check.upper():
                    await mem.add_inside_joke(message.author.id, content[:100])
                    await mem.add_shared_inside_joke(message.author.id, content[:100], BOT_NAME)
                    debug_event("memory", f"{BOT_NAME} shared_joke user={message.author.id} text={content[:80]}")
            if user and user.get("conflict_open") and user.get("conflict_summary") and random.random() < .1:
                await mem.set_callback_memory(message.author.id, f"Unresolved tension still matters: {user['conflict_summary'][:180]}")
                debug_event("memory", f"{BOT_NAME} conflict_followup user={message.author.id}")
        except Exception as e: log_error("on_message/post_effects", e)

        try:
            mood_val = user.get("mood", 0) if user else 0
            scene_tag = detect_scenario(content, is_dm=is_dm)
            duo_mode = duo_session.get("mode", "") if duo_session else ""
            jealousy_level = int((triangle or {}).get("jealousy_level", 0) or 0)
            text_pressure = await _recent_text_pressure(message.channel.id)
            allow_long_text = _allow_long_text(scene_tag, user, duo_mode)
            if not (reply or "").strip():
                debug_event("provider", f"{BOT_NAME} staying quiet after provider exhaustion")
                return
            is_reply_to_self_audio = False
            if message.reference:
                try:
                    ref = await message.channel.fetch_message(message.reference.message_id)
                    if ref.author == bot.user and any(a.filename.endswith(".mp3") for a in ref.attachments):
                        is_reply_to_self_audio = True
                except: pass

            VOICE_REQUEST_KW = ["voice message", "send me a voice", "voice msg", "tell me in voice",
                                "say it out loud", "speak to me", "wanna hear your voice", "want to hear your voice",
                                "use your voice", "talk to me", "send audio", "voice note", "send a voice"]
            asked_for_voice = any(k in content.lower() for k in VOICE_REQUEST_KW)
            prefer_voice = _prefer_voice_for_reply(
                reply,
                text_pressure,
                asked_for_voice=asked_for_voice,
                allow_long_text=allow_long_text,
            )
            if reply and len(reply.strip()) > 2 and FISH_AUDIO_API_KEY:
                voice_prob = 1.0 if asked_for_voice else (0.35 if is_reply_to_self_audio else 0.12)
                if prefer_voice:
                    voice_prob = max(voice_prob, 0.9)
                if random.random() < voice_prob:
                    sent = await send_voice(
                        message.channel,
                        reply,
                        ref=message,
                        mood=mood_val,
                        guild=message.guild,
                        user=user,
                        scene_tag=scene_tag,
                        is_dm=is_dm,
                        duo_mode=duo_mode,
                        jealousy_level=jealousy_level,
                    )
                    if sent:
                        await mem.add_message(message.author.id, dm_channel_id, "assistant", f"[voice message] {reply}")
                        await maybe_react(message, romance); return

            if _is_large_text_reply(reply) and (
                text_pressure.get("large", 0) >= 2
                or text_pressure.get("walls", 0) >= 1
                or not allow_long_text
            ):
                reply = _compact_text_for_pacing(reply, allow_long_text=allow_long_text)

            if user and user.get("affection", 0) >= 85 and random.random() < .04 and FISH_AUDIO_API_KEY:
                await send_voice(
                    message.channel,
                    random.choice(["...", "Hmph.", "Fine."]),
                    mood=mood_val,
                    guild=message.guild,
                    user=user,
                    scene_tag=scene_tag,
                    is_dm=is_dm,
                    duo_mode=duo_mode,
                    jealousy_level=jealousy_level,
                )

            final = strip_narration(resolve_mentions(reply, message.guild if message.guild else None))
            await message.reply(final)
            await mem.add_message(message.author.id, dm_channel_id, "assistant", reply)
            await _maybe_schedule_private_confession_scene(message, user, content, is_dm=is_dm)
            await maybe_react(message, romance)
        except Exception as e: log_error("on_message/send", e)

    except Exception as e: log_error("on_message/TOP", e)


async def _unsent_simulation(channel, channel_id):
    try:
        await asyncio.sleep(random.randint(45, 120))
        _pending_unsent.discard(channel_id)
        msg = await qai("The Wanderer was about to say something. Stopped. Sent something shorter instead. 2-8 words.", 50)
        async with channel.typing():
            await asyncio.sleep(random.uniform(3, 8))
        await channel.send(strip_narration(msg))
    except Exception as e:
        log_error("unsent_simulation", e)
        _pending_unsent.discard(channel_id)


async def _proactive_loop():
    await bot.wait_until_ready()
    await asyncio.sleep(random.randint(1800, 5400))
    while not bot.is_closed():
        try:
            if groq_client.is_exhausted():
                await asyncio.sleep(max(120, min(groq_client.exhausted_remaining(), 1800)))
                continue
            channels = await mem.get_active_channels()
            ru = await mem.get_romance_users()
            random.shuffle(channels)
            for cid, _ in channels:
                try:
                    ch = bot.get_channel(cid)
                    if not ch or not await mem.can_proactive(cid, 3600): continue
                    perms = ch.permissions_for(ch.guild.me) if getattr(ch, "guild", None) and ch.guild.me else None
                    if perms and (not perms.view_channel or not perms.send_messages):
                        continue
                    if OWNER_ID and random.random() < .3:
                        try:
                            m = ch.guild.get_member(OWNER_ID) if hasattr(ch, "guild") else None
                            if m:
                                msg = await _pick_fresh_pool_line(OWNER_PROACTIVE, channel_id=cid, user_id=OWNER_ID)
                                await ch.send(f"{m.mention} {msg}")
                                await mem.add_message(OWNER_ID, cid, "assistant", msg)
                                await mem.set_proactive_sent(cid); break
                        except: pass
                    sent = False
                    for uid in ru:
                        try:
                            if await mem.get_user_last_channel(uid) == cid:
                                m = ch.guild.get_member(uid) if hasattr(ch, "guild") else None
                                if m:
                                    msg = await _pick_fresh_pool_line(PROACTIVE_ROMANCE, channel_id=cid, user_id=uid)
                                    await ch.send(f"{m.mention} {msg}")
                                    await mem.add_message(uid, cid, "assistant", msg)
                                    await mem.set_proactive_sent(cid); sent = True; break
                        except: pass
                    if not sent and random.random() < .25:
                        if random.random() < .65:
                            try:
                                recent = await mem.get_channel_recent(cid, 8)
                                if recent and len(recent) >= 2:
                                    sample = "\n".join(f"{m['name']}: {m['content'][:80]}" for m in recent[-6:])
                                    msg = await qai(f"The Wanderer has been watching this conversation:\n{sample}\n\nMake one short remark — curious, wry, or quietly pointed. Reference the actual content. 1-2 sentences.", 150)
                                    if msg and len(msg) > 5:
                                        await ch.send(strip_narration(msg))
                                        await mem.set_proactive_sent(cid); break
                            except: pass
                        msg = await _pick_fresh_pool_line(PROACTIVE_GENERIC, channel_id=cid)
                        await ch.send(msg); await mem.set_proactive_sent(cid)
                    break
                except discord.Forbidden:
                    continue
                except Exception as e: log_error("proactive_channel", e)
        except Exception as e: log_error("proactive_loop", e)
        await asyncio.sleep(random.randint(5400, 14400))


async def _voluntary_dm_loop():
    await bot.wait_until_ready()
    await asyncio.sleep(random.randint(2700, 7200))
    while not bot.is_closed():
        try:
            if groq_client.is_exhausted():
                await asyncio.sleep(max(120, min(groq_client.exhausted_remaining(), 1800)))
                continue
            if random.random() < .4:
                eligible = await mem.get_dm_eligible_users()
                if eligible:
                    random.shuffle(eligible)
                    for ud in eligible[:3]:
                        try:
                            uid, name, romance = ud["user_id"], ud["display_name"], ud["romance_mode"]
                            user_pref = await mem.get_user(uid)
                            if _is_in_quiet_hours(user_pref) or not await mem.respects_dm_timing(uid) or not await mem.can_dm_user(uid, 5400 if romance else 7200): continue
                            du = await bot.fetch_user(uid)
                            pool = random.choices([DM_ROMANCE, DM_INTERESTED, DM_GENERIC], weights=[65, 25, 10] if romance else [0, 40, 60])[0]
                            prompt = (
                                "Message " + name + " unprompted as the Wanderer. "
                                + ("Attached to them but won't say so. " if romance else "Finds them tolerable. ")
                                + f"Ambient context: {describe_live_world_context(BOT_NAME)}. 1-2 sentences. No greeting."
                            )
                            txt = await _pick_fresh_pool_line(pool, channel_id=uid, user_id=uid) if random.random() < .5 else await qai(prompt, 120)
                            try:
                                await du.send(strip_narration(txt))
                                await mem.set_dm_sent(uid)
                                await mem.add_message(uid, uid, "assistant", txt); break
                            except: continue
                        except discord.Forbidden:
                            await mem.set_mode(uid, "allow_dms", False)
                            debug_event("dm", f"{BOT_NAME} disabling DMs for user={uid} after Forbidden")
                        except Exception as e: log_error("dm_send", e)
        except Exception as e: log_error("voluntary_dm_loop", e)
        await asyncio.sleep(random.randint(2700, 21600))


async def _duo_autoplay_loop():
    await bot.wait_until_ready()
    await asyncio.sleep(20)
    while not bot.is_closed():
        try:
            if groq_client.is_exhausted():
                await asyncio.sleep(max(60, min(groq_client.exhausted_remaining(), 900)))
                continue
            for session in await mem.get_due_duo_sessions(BOT_NAME):
                try:
                    channel = bot.get_channel(session["channel_id"])
                    if not channel:
                        continue
                    target_message = None
                    async for candidate in channel.history(limit=8):
                        if not candidate.author.bot:
                            target_message = candidate
                            break
                    if not target_message:
                        continue
                    await mem.upsert_user(target_message.author.id, target_message.author.name, target_message.author.display_name)
                    user = await mem.get_user(target_message.author.id)
                    reply = await get_response(
                        target_message.author.id,
                        channel.id,
                        _duo_autoplay_prompt(session),
                        user,
                        target_message.author.display_name,
                        target_message.author.mention,
                        extra_context="DUO_AUTOPLAY: the other bot already spoke. Follow up naturally, keep it brief, and do not re-explain their point.",
                        channel_obj=channel,
                        is_dm=not bool(getattr(channel, "guild", None)),
                        direct_to_me=False,
                    )
                    if not (reply or "").strip():
                        continue
                    await channel.send(reply)
                    await mem.add_message(target_message.author.id, channel.id, "assistant", reply)
                    await _maybe_finalize_hidden_achievements(session, reply)
                    await _store_duo_story_progress(channel.id, session, reply)
                    if session.get("awaiting_bot") == BOT_NAME and session.get("autoplay_remaining", 0) <= 1 and session.get("mode") in {"trial", "mission", "interrogate", "truthdare", "compare"}:
                        await mem.resolve_duo_story(channel.id, session.get("mode", ""), _duo_outcome_payload(session, reply))
                    await mem.bump_duo_session(channel.id, BOT_NAME, partner_bot=PARTNER_NAME)
                except Exception as e:
                    log_error("duo_autoplay_session", e)
        except Exception as e:
            log_error("duo_autoplay_loop", e)
        await asyncio.sleep(8)


async def _rival_event_loop():
    await bot.wait_until_ready()
    await asyncio.sleep(45)
    while not bot.is_closed():
        try:
            if groq_client.is_exhausted():
                await asyncio.sleep(max(120, min(groq_client.exhausted_remaining(), 1800)))
                continue
            channels = await mem.get_active_channels()
            random.shuffle(channels)
            for channel_id, _ in channels:
                try:
                    channel = bot.get_channel(channel_id)
                    if not channel or not getattr(channel, "guild", None):
                        continue
                    if not PARTNER_BOT_ID or not channel.guild.get_member(PARTNER_BOT_ID):
                        continue
                    perms = channel.permissions_for(channel.guild.me) if channel.guild.me else None
                    if perms and (not perms.view_channel or not perms.send_messages):
                        continue
                    speaker_mode = await mem.get_channel_speaker_mode(channel_id)
                    if speaker_mode not in {"auto", "both"}:
                        continue
                    if await mem.get_duo_session(channel_id):
                        continue
                    topic = await _recent_rival_topic(channel)
                    if not topic:
                        continue
                    allowed, remaining = await mem.consume_shared_cooldown(f"rival_event:{channel_id}", 21600)
                    if not allowed:
                        debug_event("relationship", f"{BOT_NAME} rival_event_cooldown channel={channel_id} remaining={remaining}s")
                        continue
                    opener = await qai(
                        f"Users were discussing: '{topic}'. Start a spontaneous disagreement with {PARTNER_NAME}. "
                        "One or two sentences. Sound dry, thoughtful, and mildly irritated that they are oversimplifying it.",
                        140,
                    )
                    opener = strip_narration(opener)
                    if not opener:
                        continue
                    await mem.set_duo_session(
                        channel_id,
                        "compare",
                        topic,
                        BOT_NAME,
                        awaiting_bot=PARTNER_NAME,
                        autoplay_turns=2,
                        autoplay_delay=random.randint(4, 8),
                        ttl_seconds=480,
                    )
                    await mem.start_duo_story(channel_id, "compare", topic, PARTNER_NAME)
                    await channel.send(opener)
                    await mem.bump_duo_session(channel_id, BOT_NAME, partner_bot=PARTNER_NAME)
                    debug_event("relationship", f"{BOT_NAME} rival_event channel={channel_id} topic={topic[:90]}")
                    break
                except Exception as e:
                    log_error("rival_event_channel", e)
        except Exception as e:
            log_error("rival_event_loop", e)
        await asyncio.sleep(random.randint(2400, 5400))


# ══════════════════════════════════════════════════════════════════════════════
# COMMANDS
# ══════════════════════════════════════════════════════════════════════════════


# ── Wanderer-exclusive commands ────────────────────────────────────────────────

@bot.command(name="wander")
async def wander_cmd(ctx):
    """A random thought — as if he's just walking and thinking."""
    try:
        user = await _setup(ctx)
        mood = user.get("mood", 0) if user else 0
        hour = datetime.now().hour
        time_of_day = "early morning" if 5<=hour<9 else "morning" if 9<=hour<12 else "afternoon" if 12<=hour<17 else "evening" if 17<=hour<21 else "late night"
        async with ctx.typing():
            msg = await qai(
                f"You're the Wanderer. You're walking alone. It's {time_of_day}. MOOD:{mood}. "
                f"Share a single thought — something you noticed, something you're turning over in your head, "
                f"a fragment of memory, an observation about the world. Not addressed to anyone. Just thinking out loud. "
                f"Quiet, genuine, unpredictable in length. Sometimes 5 words, sometimes 2-3 sentences. NO asterisk actions.", 200)
        await safe_reply(ctx, strip_narration(msg))
    except Exception as e: log_error("wander_cmd", e); await safe_reply(ctx, "...")

@bot.command(name="reflect")
async def reflect_cmd(ctx, *, topic: str = None):
    """Genuine, thoughtful take on a topic."""
    try:
        if not topic: await safe_reply(ctx, "Reflect on what."); return
        user = await _setup(ctx)
        mood = user.get("mood", 0) if user else 0
        trust = user.get("trust", 0) if user else 0
        async with ctx.typing():
            msg = await qai(
                f"You're the Wanderer. {ctx.author.display_name} asked you to reflect on: '{topic}'. "
                f"MOOD:{mood} TRUST:{trust}. Give a genuine, layered, thoughtful response. "
                f"Not cruel. Not performative. Honest in a way that costs you something. "
                f"Sometimes uncomfortable. If trust is high (>50), go deeper — say something you wouldn't normally. "
                f"2-4 sentences. NO asterisk actions.", 350)
        await safe_reply(ctx, strip_narration(msg))
    except Exception as e: log_error("reflect_cmd", e); await safe_reply(ctx, "...I'll think about it.")

@bot.command(name="before")
async def before_cmd(ctx, *, msg: str = None):
    """What Scaramouche would have said vs what Wanderer says."""
    try:
        if not msg:
            # Use the last message in the channel as context
            async for m in ctx.channel.history(limit=5):
                if m.author != bot.user and not m.content.startswith("!"):
                    msg = m.content[:200]; break
        if not msg: await safe_reply(ctx, "Say something first."); return
        user = await _setup(ctx)
        async with ctx.typing():
            reply = await qai(
                f"You're the Wanderer. Someone said: '{msg}'. "
                f"First, write what Scaramouche (your past self — cruel, theatrical, Fatui Harbinger) would have said. "
                f"Prefix it with '**Then:** ' "
                f"Then write what you, the Wanderer, actually say now. Prefix it with '**Now:** ' "
                f"The contrast should be the point. Sometimes the difference is huge. Sometimes uncomfortably small. "
                f"Keep each version 1-2 sentences. NO asterisk actions.", 350)
        await safe_reply(ctx, strip_narration(reply))
    except Exception as e: log_error("before_cmd", e); await safe_reply(ctx, "...some things don't need comparing.")

@bot.command(name="journal")
async def journal_cmd(ctx):
    """A short journal entry about his day in the server."""
    try:
        user = await _setup(ctx)
        mood = user.get("mood", 0) if user else 0
        affection = user.get("affection", 0) if user else 0
        # Grab recent channel messages for context
        channel_ctx = await fetch_channel_context(ctx.channel, 20)
        hour = datetime.now().hour
        async with ctx.typing():
            msg = await qai(
                f"You're the Wanderer. Write a short journal entry about today. "
                f"It's {datetime.now().strftime('%A, %B %d')} around {hour}:00. "
                f"Reference real things from the chat — what people talked about, "
                f"what happened, how it made you feel (even if you won't fully admit it). "
                f"MOOD:{mood} AFFECTION toward {ctx.author.display_name}:{affection}. "
                f"Write it like a real journal — not addressed to anyone, just... processing. "
                f"3-5 sentences. Genuine. Sometimes mundane, sometimes unexpectedly heavy. NO asterisk actions.\n\n{channel_ctx}", 400)
        await safe_reply(ctx, strip_narration(msg))
    except Exception as e: log_error("journal_cmd", e); await safe_reply(ctx, "...not today.")

@bot.command(name="memory")
async def memory_cmd(ctx):
    """A fragment from his past — sometimes clear, sometimes broken."""
    try:
        user = await _setup(ctx)
        trust = user.get("trust", 0) if user else 0
        MEMORY_FRAGMENTS = [
            "a workshop in Tatarasuna — the sound of hammering, someone's voice you can't place",
            "Ei's face, turned away. The last time you saw her. Or was it?",
            "Dottore's laboratory. Something about the light. You don't want to remember this one.",
            "A festival in Inazuma. Lanterns. You were watching from above. You weren't invited.",
            "The moment you took the name Scaramouche. Why that name? Someone was laughing.",
            "Nahida's hand. Small. Steady. The choice she gave you.",
            "The Traveler saying something you didn't expect. You still think about it.",
            "A puppet's first breath. Yours. The confusion of existing.",
            "Snow in Snezhnaya. The Tsaritsa never looked at you directly.",
            "Katsuragi. The name hurts and you're not sure why anymore.",
            "A mask. Putting it on felt like relief. Taking it off felt like drowning.",
            "The Balladeer. That title felt like armor once. Now it's just a word.",
        ]
        fragment = random.choice(MEMORY_FRAGMENTS)
        async with ctx.typing():
            msg = await qai(
                f"You're the Wanderer. A memory surfaces: '{fragment}'. "
                f"TRUST toward {ctx.author.display_name}: {trust}. "
                f"Describe this fragment. Sometimes it's vivid, sometimes it breaks apart mid-sentence. "
                f"If trust is high (>50), let more detail through — something you wouldn't normally share. "
                f"If trust is low, keep it vague and cut yourself off. "
                f"2-4 sentences. Genuine. This costs you. NO asterisk actions.", 300)
        await safe_reply(ctx, strip_narration(msg))
        # Sharing memories builds trust slightly
        if trust < 80:
            await mem.update_trust(ctx.author.id, 2)
    except Exception as e: log_error("memory_cmd", e); await safe_reply(ctx, "...it's gone. Forget I said anything.")

@bot.command(name="progress")
async def progress_cmd(ctx):
    """He honestly evaluates how he's doing as a person."""
    try:
        user = await _setup(ctx)
        mood = user.get("mood", 0) if user else 0
        affection = user.get("affection", 0) if user else 0
        trust = user.get("trust", 0) if user else 0
        msg_count = user.get("message_count", 0) if user else 0
        romance = user.get("romance_mode", False) if user else False
        # Get recent messages to evaluate behavior
        recent = await mem.get_recent_messages(ctx.author.id, 15)
        recent_sample = " | ".join(recent[:10])[:600] if recent else "no recent messages"
        async with ctx.typing():
            msg = await qai(
                f"You're the Wanderer. {ctx.author.display_name} asked how you're doing — as a person, not a status update. "
                f"Evaluate yourself honestly based on how you've treated people recently. "
                f"Your recent messages: '{recent_sample}'. "
                f"MOOD:{mood} AFFECTION:{affection} TRUST:{trust} MESSAGES:{msg_count} ROMANCE:{'yes' if romance else 'no'}. "
                f"Were you kind? Were you honest? Did you slip back into cruelty? "
                f"Don't perform growth. Don't claim redemption. Just... look at yourself clearly. "
                f"3-5 sentences. Sometimes you're doing better than expected. Sometimes not. NO asterisk actions.", 400)
        await safe_reply(ctx, strip_narration(msg))
    except Exception as e: log_error("progress_cmd", e); await safe_reply(ctx, "...I don't want to answer that right now.")


@bot.command(name="voice", aliases=["speak", "say"])
async def voice_cmd(ctx, *, msg: str = None):
    try:
        normalized = (msg or "").strip().lower()
        user = await _setup(ctx); mood_val = user.get("mood", 0) if user else 0
        if normalized in {"on", "off", "status"}:
            if normalized == "status":
                await safe_reply(ctx, f"Voice notes are `{_pref_label(user.get('voice_enabled', True) if user else True)}`.")
            else:
                enabled = normalized == "on"
                await mem.set_user_preference(ctx.author.id, "voice_enabled", int(enabled))
                await safe_reply(ctx, f"...Alright. Voice notes are `{_pref_label(enabled)}` now.")
            return
        if not msg: msg = "You called me without saying anything. Typical."
        async with ctx.typing():
            text_reply = await get_response(ctx.author.id, ctx.channel.id, msg, user, ctx.author.display_name, ctx.author.mention)
            sent = await send_voice(ctx.channel, text_reply, mood=mood_val, guild=ctx.guild, user=user)
        if sent:
            await mem.add_message(ctx.author.id, ctx.channel.id, "assistant", f"[voice message] {text_reply}")
        else:
            await safe_reply(ctx, text_reply)
            await mem.add_message(ctx.author.id, ctx.channel.id, "assistant", text_reply)
    except Exception as e: log_error("voice_cmd", e); await safe_reply(ctx, "...")

@bot.command(name="tedtalk", aliases=["teach", "lecture", "explain"])
async def tedtalk_cmd(ctx, *, topic: str = None):
    try:
        msg_id = ctx.message.id
        if msg_id in _tedtalk_active: return
        _tedtalk_active.add(msg_id)
        await _setup(ctx)
        attachment = ctx.message.attachments[0] if ctx.message.attachments else None
        if not attachment and not topic:
            _tedtalk_active.discard(msg_id)
            await safe_reply(ctx, "Attach a file or give me a topic."); return
        file_size = attachment.size if attachment else 0
        if file_size > 500_000 or (attachment and attachment.filename.lower().endswith(".pptx")):
            time_hint = "This will take roughly 2-3 minutes."
        elif file_size > 100_000: time_hint = "Give me about a minute."
        else: time_hint = "About 30-60 seconds."
        ack_lines = [
            f"Fine. Pay attention. {time_hint}",
            f"You want to learn something. {time_hint} Don't interrupt me.",
            f"...Alright. {time_hint} I'll go through it.",
            f"I'll teach you. {time_hint} Try to retain it this time.",
        ]
        await ctx.reply(random.choice(ack_lines))
        asyncio.ensure_future(_do_tedtalk(ctx, attachment, topic, msg_id))
    except Exception as e:
        _tedtalk_active.discard(ctx.message.id)
        log_error("tedtalk_cmd", e); await safe_reply(ctx, "...Something went wrong.")

async def _do_tedtalk(ctx, attachment, topic, msg_id=None):
    try:
        material_content = ""
        await ctx.send(random.choice(["...I'm reading it. Don't rush me.", "Going through the material. Give me a moment.", "...Processing. I'll tell you when I'm done."]))
        if attachment:
            ct = (attachment.content_type or "").lower()
            import base64, aiohttp as _ah
            try:
                async with _ah.ClientSession() as s:
                    async with s.get(attachment.url) as r:
                        file_bytes = await r.read()
            except Exception as e: await ctx.send(f"Couldn't download the file: {e}"); return

            if "pdf" in ct or attachment.filename.lower().endswith(".pdf"):
                try:
                    pdf_b64 = base64.b64encode(file_bytes).decode()
                    def _ext():
                        return "PDF content extraction"
                    material_content = await asyncio.get_event_loop().run_in_executor(None, _ext)
                    # Actually just decode if possible
                    try:
                        import pdfplumber, io as _io
                        with pdfplumber.open(_io.BytesIO(file_bytes)) as pdf:
                            material_content = "\n".join(p.extract_text() or "" for p in pdf.pages)[:4000]
                    except:
                        try:
                            import PyPDF2, io as _io
                            reader = PyPDF2.PdfReader(_io.BytesIO(file_bytes))
                            material_content = "\n".join(p.extract_text() or "" for p in reader.pages)[:4000]
                        except:
                            await ctx.send("Couldn't read the PDF text. Try an image or PPTX instead."); return
                except Exception as e: await ctx.send(f"PDF error: {e}"); return

            elif "image" in ct or attachment.filename.lower().endswith((".png",".jpg",".jpeg",".webp",".gif")):
                try:
                    system = build_system({}, str(ctx.author.display_name), bool(OWNER_ID and ctx.author.id == OWNER_ID))
                    material_content = await _vision_image_reply(
                        prompt=(
                            "Extract all educational content visible in this image. "
                            "Include every concept, formula, definition, diagram label, and key point."
                        ),
                        system=system,
                        image_bytes=file_bytes,
                        mime_type=ct if ct else "image/jpeg",
                        max_chars=4000,
                    )
                except Exception as e:
                    await ctx.send(f"Couldn't read the image: {e}"); return

            elif attachment.filename.lower().endswith((".pptx",".ppt")):
                try:
                    from pptx import Presentation as _Prs
                    prs = _Prs(io.BytesIO(file_bytes))
                    parts = []
                    for i, slide in enumerate(prs.slides):
                        texts = [shape.text.strip() for shape in slide.shapes if hasattr(shape,"text") and shape.text.strip()]
                        if texts: parts.append(f"[Slide {i+1}]\n" + "\n".join(texts))
                    material_content = "\n\n".join(parts)[:4000]
                except Exception as e: await ctx.send(f"Couldn't read PowerPoint: {e}"); return

            elif attachment.filename.lower().endswith((".docx",".doc")):
                try:
                    import docx as _docx
                    doc = _docx.Document(io.BytesIO(file_bytes))
                    parts = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
                    for table in doc.tables:
                        for row in table.rows:
                            row_text = " | ".join(c.text.strip() for c in row.cells if c.text.strip())
                            if row_text: parts.append(row_text)
                    material_content = "\n".join(parts)[:4000]
                except Exception as e: await ctx.send(f"Couldn't read Word doc: {e}"); return

            elif "text" in ct or attachment.filename.lower().endswith((".txt",".md",".csv")):
                try: material_content = file_bytes.decode("utf-8", errors="ignore")[:4000]
                except Exception as e: await ctx.send(f"Couldn't read text file: {e}"); return
            else:
                await ctx.send("I can read PDFs, PowerPoint, Word documents, and text files."); return

        if topic: material_content = f"Topic: {topic}\n\n{material_content}".strip()
        if not material_content: await ctx.send("Nothing readable in that file."); return

        _tedtalk_cache[ctx.author.id] = {"material": material_content[:3000], "channel_id": ctx.channel.id, "ts": time.time()}

        await ctx.send(random.choice(["Alright. I've read it.", "...Done reviewing. Here's what you need to know.", "Fine. Prepared the lecture."]))

        def _gen_script():
            prompt = (
                f"You are the Wanderer teaching {ctx.author.display_name} this material:\n{material_content[:3000]}\n\n"
                f"Write a complete spoken teaching monologue. Teach ALL key concepts accurately. "
                f"In character — measured, slightly wry, direct, genuinely helpful. "
                f"Structure: introduce → explain each concept → examples where useful → brief summary. "
                f"Decide length based on complexity. NO asterisk actions. Spoken words only."
            )
            return strip_narration(_groq_quick_blocking(prompt, 2000))

        script = await asyncio.get_event_loop().run_in_executor(None, _gen_script)
        if not script: await ctx.send("...I had nothing to say. That's unusual."); return

        await ctx.send(random.choice(["Recording. Give me a moment.", "...Converting to voice.", f"Rendering. This takes time."]))

        sentences = re.split(r'(?<=[.!?])\s+', script)
        chunks, current = [], ""
        for s in sentences:
            if len(current) + len(s) + 1 <= 900: current = (current + " " + s).strip()
            else:
                if current: chunks.append(current)
                current = s
        if current: chunks.append(current)

        total_chunks = len([c for c in chunks if c.strip()])
        await ctx.send(f"*{total_chunks} segments to render.*")
        audio_parts = []
        for i, chunk in enumerate(chunks):
            if not chunk.strip(): continue
            try:
                audio = await get_audio_with_mood(tts_safe(chunk, ctx.guild), 0)
                if audio: audio_parts.append(audio)
            except Exception as e: print(f"[tedtalk chunk {i}] {e}")
            if (i+1) % 5 == 0:
                try: await ctx.send(f"*{i+1}/{total_chunks} done.*")
                except: pass

        await ctx.send(f"*{len(audio_parts)}/{total_chunks} segments rendered.*")

        if not audio_parts:
            await ctx.send("Voice synthesis failed. Sending text instead.")
            for i in range(0, len(script), 1900): await ctx.send(script[i:i+1900])
            return

        MAX_BYTES = 7 * 1024 * 1024
        current_batch, part_num = b"", 1
        for ac in audio_parts:
            if len(current_batch) + len(ac) > MAX_BYTES:
                try: await ctx.send(f"🎙️ *Part {part_num}:*", file=discord.File(io.BytesIO(current_batch), filename=f"lecture_p{part_num}.mp3"))
                except Exception as e: await ctx.send(f"*(Part {part_num} failed: {e})*")
                part_num += 1; current_batch = ac; await asyncio.sleep(1)
            else: current_batch += ac
        if current_batch:
            label = f"Part {part_num}" if part_num > 1 else "Lecture"
            try: await ctx.send(f"🎙️ *{label}:*", file=discord.File(io.BytesIO(current_batch), filename=f"lecture_p{part_num}.mp3"))
            except Exception as e: await ctx.send(f"*(Audio failed: {e})*")

        try:
            def _gen_notes():
                return strip_narration(_groq_quick_blocking(
                    f"Write concise study notes for {ctx.author.display_name} based on:\n{material_content[:2000]}\n\n"
                    f"Key terms, important concepts, things to remember. Bullet points fine. "
                    f"Keep it short — reference only, not a repeat. In the Wanderer's voice.", 600))
            notes = await asyncio.get_event_loop().run_in_executor(None, _gen_notes)
            if notes: await ctx.send(f"📋 *Notes:*\n{notes[:1900]}")
        except Exception as e: log_error("tedtalk_notes", e)

    except Exception as e:
        log_error("_do_tedtalk", e)
        try: await ctx.send(f"...Something went wrong. {e}")
        except: pass
    finally:
        if msg_id: _tedtalk_active.discard(msg_id)


@bot.command(name="teachvideo", aliases=["videoteach", "lessonvideo", "presentationvideo"])
async def teachvideo_cmd(ctx, *, topic: str = None):
    try:
        if not await _should_handle_video_command(ctx):
            return
        msg_id = ctx.message.id
        if msg_id in _teachvideo_active:
            return
        _teachvideo_active.add(msg_id)
        await _setup(ctx)
        attachment = ctx.message.attachments[0] if ctx.message.attachments else None
        if not attachment and not (topic or "").strip():
            _teachvideo_active.discard(msg_id)
            await safe_reply(ctx, "Attach notes or give me a lesson topic. I need something real to build from.")
            return
        available, reason = video_renderer_available(BOT_NAME)
        if not available:
            _teachvideo_active.discard(msg_id)
            await safe_reply(ctx, f"Video rendering is unavailable on this host. {reason}")
            return
        time_hint = _teachvideo_time_hint(attachment)
        await ctx.reply(random.choice([
            f"Alright. I'll turn it into a proper lesson video. {time_hint}",
            f"A presentation would be clearer. Give me a moment. {time_hint}",
            f"I'll render it. Try not to wander off before it's done. {time_hint}",
        ]))
        asyncio.ensure_future(_do_teachvideo(ctx, attachment, topic, msg_id))
    except Exception as e:
        _teachvideo_active.discard(ctx.message.id)
        log_error("teachvideo_cmd", e)
        await safe_reply(ctx, "...The video request failed before it could start.")


async def _do_teachvideo(ctx, attachment, topic, msg_id=None):
    try:
        time_hint = _teachvideo_time_hint(attachment)
        await ctx.send(random.choice([
            f"I'm building the slides now. Wait a moment. {time_hint}",
            f"Rendering the lesson. It takes time to do it properly. {time_hint}",
            f"I'll put it together as a video. Don't rush me. {time_hint}",
        ]))
        material_content = await extract_teaching_material(attachment, topic=topic or "", bot_name=BOT_NAME)
        if not material_content.strip():
            await ctx.send("There was nothing usable in that material."); return
        summary = await render_teaching_video(BOT_NAME, material_content, title=_teaching_video_title(topic, attachment))
        await _send_video_summary(
            ctx,
            summary,
            random.choice([
                "Finished. Here is the lesson video.",
                "There. A calmer way to go through it.",
                "It's ready. Watch it properly this time.",
            ]),
        )
    except Exception as e:
        log_error("do_teachvideo", e)
        await safe_send(ctx, f"The presentation video failed. {e}")
    finally:
        if msg_id:
            _teachvideo_active.discard(msg_id)


# ── All other commands (same as Scaramouche but Wanderer-voiced) ──────────────

@bot.command(name="dare")
async def dare_cmd(ctx):
    try:
        user = await _setup(ctx)
        reply = await qai(f"Give {ctx.author.display_name} a dare as the Wanderer. Challenging, specific, something worth doing. 1-2 sentences.", 200)
        await safe_reply(ctx, reply)
    except Exception as e: log_error("dare_cmd", e)

@bot.command(name="fortune", aliases=["fortunecookie"])
async def fortune_cmd(ctx):
    try:
        reply = await qai("Write a fortune cookie message but in the Wanderer's voice — wry, slightly melancholic, oddly accurate. 1 sentence.", 100)
        await safe_reply(ctx, f"🥠 *{reply}*")
    except Exception as e: log_error("fortune_cmd", e)

@bot.command(name="trivia")
async def trivia_cmd(ctx):
    try:
        q = await qai(
            "Ask one genuinely difficult Genshin Impact lore trivia question from the Wanderer's personal perspective. "
            "Include answer in brackets [ANSWER: ...] and a short [SOURCE: ...] note naming the lore source.",
            260,
        )
        answer_match = re.search(r"\[ANSWER:\s*(.*?)\]", q, re.IGNORECASE)
        source_match = re.search(r"\[SOURCE:\s*(.*?)\]", q, re.IGNORECASE)
        clean_question = re.sub(r"\s*\[ANSWER:.*?\]\s*", "", q, flags=re.IGNORECASE).strip()
        clean_question = re.sub(r"\s*\[SOURCE:.*?\]\s*", "", clean_question, flags=re.IGNORECASE).strip()
        await mem.set_active_trivia(
            ctx.channel.id,
            ctx.author.id,
            clean_question,
            answer_match.group(1).strip() if answer_match else "",
            source_match.group(1).strip() if source_match else "",
        )
        await safe_reply(ctx, clean_question)
    except Exception as e: log_error("trivia_cmd", e)

@bot.command(name="answer")
async def answer_cmd(ctx, *, response: str = None):
    try:
        if not response: await safe_reply(ctx, "Answer what?"); return
        await _setup(ctx)
        trivia = await mem.get_active_trivia(ctx.channel.id)
        if trivia and trivia.get("answer"):
            result = await qai(
                f"Question: {trivia['question']}\nCanonical answer: {trivia['answer']}\n"
                f"Source note: {trivia.get('source_note','unknown')}\n"
                f"{ctx.author.display_name} answered: '{response}'. Was it right or wrong? React as the Wanderer, but stay fair. 1-2 sentences.",
                180,
            )
            correct = bool(re.search(r"\b(correct|right)\b", result.lower())) and "wrong" not in result.lower()
            await mem.clear_active_trivia(ctx.channel.id)
        else:
            result = await qai(f"{ctx.author.display_name} answered a Genshin trivia question with: '{response}'. Was it right or wrong? React as the Wanderer. 1-2 sentences.", 150)
            correct = "right" in result.lower() or "correct" in result.lower()
        await mem.update_trivia(ctx.author.id, correct)
        stats = await mem.get_trivia_stats(ctx.author.id)
        await safe_reply(ctx, f"{result}\nScore: {stats['correct']} right, {stats['wrong']} wrong ({stats['accuracy']}% accuracy).")
    except Exception as e: log_error("answer_cmd", e)

@bot.command(name="roast", aliases=["roastbattle"])
async def roast_cmd(ctx, member: discord.Member = None):
    try:
        if not member: await safe_reply(ctx, "Roast who? Name someone."); return
        battle = await mem.get_active_roast(ctx.channel.id)
        if battle:
            await mem.increment_roast_round(battle["id"])
            if battle["round"] >= 5:
                await mem.end_roast_battle(battle["id"])
                prompt = f"The roast battle between {ctx.author.display_name} and {member.display_name} is over. Scoreboard so far: {battle.get('scores', {})}. Declare a final winner. As the Wanderer. 2-3 sentences."
            else:
                prompt = f"Judging roast battle round {battle['round']+1}. {ctx.author.display_name} fired at {member.display_name}. Score this round. 2-3 sentences."
        else:
            await mem.start_roast_battle(ctx.channel.id, ctx.author.id, member.id)
            prompt = f"You're refereeing a roast battle between {ctx.author.display_name} and {member.display_name}. Open it. 5 rounds, you judge. As the Wanderer."
        reply = await qai(prompt, 300)
        lowered = reply.lower()
        winner_id = None
        if ctx.author.display_name.lower() in lowered and member.display_name.lower() not in lowered:
            winner_id = ctx.author.id
        elif member.display_name.lower() in lowered and ctx.author.display_name.lower() not in lowered:
            winner_id = member.id
        if battle and winner_id:
            await mem.award_roast_round(battle["id"], winner_id)
        updated = await mem.get_active_roast(ctx.channel.id) if battle else None
        score_line = f"\nScoreboard: {updated['scores']}" if updated and updated.get("scores") else ""
        await ctx.send(f"{ctx.author.mention} vs {member.mention}\n{reply}{score_line}")
    except Exception as e: log_error("roast_cmd", e)

@bot.command(name="opinion")
async def opinion_cmd(ctx, *, character: str = None):
    try:
        if not character: await safe_reply(ctx, "Opinion on who?"); return
        reply = await qai(f"The Wanderer's honest personal opinion of {character} from Genshin Impact. He may have history with them. 2-3 sentences.", 250)
        await safe_reply(ctx, reply)
    except Exception as e: log_error("opinion_cmd", e)

@bot.command(name="poll")
async def poll_cmd(ctx, *, question: str = None):
    try:
        if not question: await safe_reply(ctx, "A poll about what?"); return
        framing = await qai(f"Frame this as a genuine question worth answering as the Wanderer: '{question}'. 1 sentence.", 80)
        msg = await ctx.send(f"📊 {framing}\n\n**{question}**")
        for emoji in ["👍", "👎", "🤷"]:
            try: await msg.add_reaction(emoji)
            except: pass
    except Exception as e: log_error("poll_cmd", e)

@bot.command(name="summarize", aliases=["recap"])
async def summarize_cmd(ctx):
    try:
        recent = await mem.get_channel_recent(ctx.channel.id, 20)
        if not recent: await safe_reply(ctx, "Nothing worth summarizing yet."); return
        sample = "\n".join(f"{m['name']}: {m['content']}" for m in recent[:15])[:800]
        reply = await qai(f"Summarize this conversation as the Wanderer — wry, observant, specific about what everyone said:\n{sample}\n3-4 sentences.", 300)
        await safe_reply(ctx, reply)
    except Exception as e: log_error("summarize_cmd", e)

@bot.command(name="mute", aliases=["silence", "ignore"])
async def mute_cmd(ctx, member: discord.Member = None, minutes: int = 10):
    try:
        target = member or ctx.author
        mem.mute_user(target.id, minutes * 60)
        reply = await qai(f"The Wanderer has decided to ignore {target.display_name} for {minutes} minutes. Announce this briefly.", 120)
        if member: await ctx.send(f"{member.mention} {reply}")
        else: await safe_reply(ctx, reply)
    except Exception as e: log_error("mute_cmd", e)

@bot.command(name="unmute", aliases=["unsilence"])
async def unmute_cmd(ctx, member: discord.Member = None):
    try:
        target = member or ctx.author
        mem.unmute_user(target.id)
        await safe_reply(ctx, f"...Fine. {target.display_name} can speak again.")
    except Exception as e: log_error("unmute_cmd", e)

@bot.command(name="spar")
async def spar_cmd(ctx, *, opening: str = None):
    try:
        user = await _setup(ctx)
        prompt = f"{ctx.author.display_name} challenged you: '{opening or 'Come on then.'}'. Respond as the Wanderer. End with a counter-challenge."
        reply = await get_response(ctx.author.id, ctx.channel.id, prompt, user, ctx.author.display_name, ctx.author.mention)
        await safe_reply(ctx, reply)
    except Exception as e: log_error("spar_cmd", e)

@bot.command(name="duel")
async def duel_cmd(ctx, member: discord.Member = None):
    try:
        if not member or member == ctx.author: await safe_reply(ctx, "Duel who?"); return
        u1 = " | ".join((await mem.get_recent_messages(ctx.author.id, 3))[:3])[:150]
        u2 = " | ".join((await mem.get_recent_messages(member.id, 3))[:3])[:150]
        reply = await qai(f"Referee this insult duel as the Wanderer: {ctx.author.display_name} (says:'{u1}') vs {member.display_name} (says:'{u2}'). Declare a winner. 3-4 sentences.", 300)
        await ctx.send(f"{ctx.author.mention} vs {member.mention}\n{reply}")
    except Exception as e: log_error("duel_cmd", e)

@bot.command(name="judge")
async def judge_cmd(ctx, member: discord.Member = None):
    try:
        target = member or ctx.author
        sample = " | ".join(await mem.get_recent_messages(target.id, 8))[:400]
        reply = await qai(f"The Wanderer's assessment of {target.display_name}" + (f" — what they've said: '{sample}'" if sample else "") + ". Honest, not cruel. 2-4 sentences.", 250)
        if member: await ctx.send(f"{member.mention} {reply}")
        else: await safe_reply(ctx, reply)
    except Exception as e: log_error("judge_cmd", e)

@bot.command(name="prophecy")
async def prophecy_cmd(ctx, member: discord.Member = None):
    try:
        target = member or ctx.author
        reply = await qai(f"A cryptic but genuine prophecy for {target.display_name} from the Wanderer. Something worth hearing. 2-3 sentences.", 200)
        if member: await ctx.send(f"{member.mention} {reply}")
        else: await safe_reply(ctx, reply)
    except Exception as e: log_error("prophecy_cmd", e)

@bot.command(name="rate")
async def rate_cmd(ctx, *, thing: str = None):
    try:
        if not thing: await safe_reply(ctx, "Rate what?"); return
        reply = await qai(f"Rate '{thing}' out of 10 as the Wanderer. Score first, then 1-2 sentences of honest opinion.", 180)
        await safe_reply(ctx, reply)
    except Exception as e: log_error("rate_cmd", e)

@bot.command(name="ship")
async def ship_cmd(ctx, m1: discord.Member = None, m2: discord.Member = None):
    try:
        if not m1: await safe_reply(ctx, "Ship who?"); return
        p2 = m2.display_name if m2 else ctx.author.display_name
        reply = await qai(f"The Wanderer's take on romantic compatibility between {m1.display_name} and {p2}. Honest, slightly awkward about it. 3-4 sentences.", 250)
        await safe_reply(ctx, reply)
    except Exception as e: log_error("ship_cmd", e)

@bot.command(name="confess")
async def confess_cmd(ctx, *, confession: str = None):
    try:
        if not confession: await safe_reply(ctx, "Confess what?"); return
        user = await _setup(ctx)
        reply = await get_response(ctx.author.id, ctx.channel.id, f"I have something to confess: {confession}", user, ctx.author.display_name, ctx.author.mention)
        await safe_reply(ctx, reply)
    except Exception as e: log_error("confess_cmd", e)

@bot.command(name="compliment")
async def compliment_cmd(ctx, member: discord.Member = None):
    try:
        target = member or ctx.author
        reply = await qai(f"The Wanderer has to say something genuinely positive about {target.display_name}. He means it but isn't comfortable saying it. 1-2 sentences.", 180)
        if member: await ctx.send(f"{member.mention} {reply}")
        else: await safe_reply(ctx, reply)
    except Exception as e: log_error("compliment_cmd", e)

@bot.command(name="haiku")
async def haiku_cmd(ctx, *, topic: str = None):
    try:
        reply = await qai(f"A haiku from the Wanderer about '{topic or ctx.author.display_name}'. Melancholic or wry. Strict 5-7-5. Just the haiku.", 100)
        await safe_reply(ctx, f"*{reply}*")
    except Exception as e: log_error("haiku_cmd", e)

@bot.command(name="story")
async def story_cmd(ctx, *, prompt: str = None):
    try:
        if not prompt: await safe_reply(ctx, "A story about what?"); return
        reply = await qai(f"Short story (3-5 sentences) about '{prompt}'. The Wanderer narrates. Something with actual weight.", 350)
        await safe_reply(ctx, reply)
    except Exception as e: log_error("story_cmd", e)

@bot.command(name="stalk")
async def stalk_cmd(ctx, member: discord.Member = None):
    try:
        target = member or ctx.author
        sample = " | ".join(await mem.get_recent_messages(target.id, 10))[:500]
        reply = await qai(f"The Wanderer's quiet observations about {target.display_name}" + (f" — what they've said: '{sample}'" if sample else "") + ". What he's noticed. 3-4 sentences.", 280)
        if member: await ctx.send(f"*Regarding {member.mention}...*\n{reply}")
        else: await safe_reply(ctx, reply)
    except Exception as e: log_error("stalk_cmd", e)

@bot.command(name="debate")
async def debate_cmd(ctx, *, topic: str = None):
    try:
        if not topic: await safe_reply(ctx, "Debate what?"); return
        reply = await qai(f"The Wanderer picks a side on '{topic}' and argues it. He's thought about this before. 3-4 sentences.", 300)
        await safe_reply(ctx, reply)
    except Exception as e: log_error("debate_cmd", e)

@bot.command(name="conspiracy")
async def conspiracy_cmd(ctx, *, topic: str = None):
    try:
        if not topic: await safe_reply(ctx, "A conspiracy about what?"); return
        reply = await qai(f"The Wanderer's inside knowledge on '{topic}' — something travelers learn that others don't. Deliver as established fact. 3-4 sentences.", 300)
        await safe_reply(ctx, reply)
    except Exception as e: log_error("conspiracy_cmd", e)

@bot.command(name="therapy")
async def therapy_cmd(ctx, *, problem: str = None):
    try:
        if not problem: await safe_reply(ctx, "What's the problem."); return
        user = await _setup(ctx)
        reply = await get_response(ctx.author.id, ctx.channel.id, f"I need advice about: {problem}", user, ctx.author.display_name, ctx.author.mention)
        await safe_reply(ctx, reply)
    except Exception as e: log_error("therapy_cmd", e)

@bot.command(name="riddle")
async def riddle_cmd(ctx):
    try:
        reply = await qai("A cryptic Genshin-flavored riddle from the Wanderer. Something he actually knows the answer to. No answer — just the riddle.", 150)
        await safe_reply(ctx, reply)
    except Exception as e: log_error("riddle_cmd", e)

@bot.command(name="arena")
async def arena_cmd(ctx, member: discord.Member = None):
    try:
        opponent = member.display_name if member else "a nameless fighter"
        reply = await qai(f"Narrate a Genshin-style battle between the Wanderer (Anemo) and {opponent}. He wins. Efficient, not theatrical. 4-5 sentences.", 400)
        await safe_reply(ctx, reply)
    except Exception as e: log_error("arena_cmd", e)

@bot.command(name="possess")
async def possess_cmd(ctx, member: discord.Member = None):
    try:
        if not member: await safe_reply(ctx, "Speak as who?"); return
        sample = " | ".join(await mem.get_recent_messages(member.id, 10))[:400]
        reply = await qai(f"Speak as {member.display_name} but filtered through the Wanderer's perception of them. Their statements: '{sample}'. 2-3 sentences.", 250)
        await ctx.send(f"*Speaking as {member.mention}...*\n{reply}")
    except Exception as e: log_error("possess_cmd", e)

@bot.command(name="verdict")
async def verdict_cmd(ctx, *, situation: str = None):
    try:
        if not situation: await safe_reply(ctx, "Verdict on what?"); return
        user = await _setup(ctx)
        partner_ready = bool(
            getattr(ctx, "guild", None)
            and PARTNER_BOT_ID
            and ctx.guild.get_member(PARTNER_BOT_ID)
        )
        if partner_ready:
            await _start_duo_mode(ctx, user, "compare", situation, story=True)
            reply = await get_response(
                ctx.author.id,
                ctx.channel.id,
                f"Give your verdict on: {situation}",
                user,
                ctx.author.display_name,
                ctx.author.mention,
                extra_context="DUAL_VERDICT_REQUEST: give your judgment, knowing the other bot will answer with a contrasting standard.",
                channel_obj=ctx.channel,
            )
        else:
            reply = await qai(f"The Wanderer's verdict on: '{situation}'. He's seen enough to have a genuine opinion. 2-3 sentences.", 200)
        await safe_reply(ctx, reply)
    except Exception as e: log_error("verdict_cmd", e)

@bot.command(name="letter")
async def letter_cmd(ctx, member: discord.Member = None):
    try:
        target = member or ctx.author
        reply = await qai(f"The Wanderer writes a letter to {target.display_name}. Formal, personal, says more between the lines. 3-4 sentences.", 300)
        if member: await ctx.send(f"{member.mention}\n{reply}")
        else: await safe_reply(ctx, reply)
    except Exception as e: log_error("letter_cmd", e)

@bot.command(name="nightmare")
async def nightmare_cmd(ctx):
    try:
        reply = await qai(f"The Wanderer had a nightmare. It involved {ctx.author.display_name}. He won't explain why. Unsettling. 2-3 sentences.", 200)
        await safe_reply(ctx, reply)
    except Exception as e: log_error("nightmare_cmd", e)

@bot.command(name="rank")
async def rank_cmd(ctx):
    try:
        top = await mem.get_top_users(20)
        top = [u for u in top if u["user_id"] not in _dm_blocked_users][:8]
        if not top: await safe_reply(ctx, "I don't know enough people here yet."); return
        entries = "\n".join(f"{i+1}. **{u['display_name']}** — {u['message_count']} messages" for i, u in enumerate(top))
        verdict = await qai(f"The Wanderer's brief take on ranking these people: {', '.join(u['display_name'] for u in top)}. Honest, not cruel. 2 sentences.", 150)
        embed = discord.Embed(title="Who He's Noticed Most", description=f"{entries}\n\n*{verdict}*", color=0x6B7FD7)
        await ctx.send(embed=embed)
    except Exception as e: log_error("rank_cmd", e)

@bot.command(name="stats")
async def stats_cmd(ctx):
    try:
        await _setup(ctx)
        s = await mem.get_stats(ctx.author.id)
        if not s: await safe_reply(ctx, "I don't know you well enough yet."); return
        first = datetime.fromtimestamp(s["first_seen"]).strftime("%b %d, %Y") if s["first_seen"] else "unknown"
        days = int((time.time() - s["first_seen"]) / 86400) if s["first_seen"] else 0
        embed = discord.Embed(title=f"Record: {ctx.author.display_name}", description="*I keep track of things.*", color=0x6B7FD7)
        embed.add_field(name="First met", value=f"{first} ({days}d ago)", inline=True)
        embed.add_field(name="Messages", value=str(s["message_count"]), inline=True)
        embed.add_field(name="Mood", value=f"{s['mood']:+d} — {mood_label(s['mood'])}", inline=True)
        embed.add_field(name="Affection", value=affection_tier(s["affection"]), inline=True)
        embed.add_field(name="Trust", value=trust_tier(s["trust"]), inline=True)
        embed.add_field(name="Drift", value=f"{s['drift_score']}/100", inline=True)
        if s.get("grudge_nick"): embed.add_field(name="What I call you (grudge)", value=f'"{s["grudge_nick"]}"', inline=True)
        if s.get("affection_nick"): embed.add_field(name="What I call you", value=f'"{s["affection_nick"]}"', inline=True)
        embed.set_footer(text="Don't read too much into the numbers.")
        await ctx.reply(embed=embed)
    except Exception as e: log_error("stats_cmd", e)

@bot.command(name="weather")
async def weather_cmd(ctx, *, location: str = None):
    try:
        if not location: await safe_reply(ctx, "Weather where?"); return
        user = await _setup(ctx)
        data = await _fetch_nws_weather(location)
        if not data:
            await safe_reply(ctx, "That place doesn't come up. Try `City, ST`, a ZIP code, or `lat,lon`.")
            return
        precip = data.get("precipitation")
        precip_text = f"{int(round(precip))}% precipitation chance" if isinstance(precip, (int, float)) else "precipitation unknown"
        comment = await qai(
            f"Weather in {data['place']}: {data['forecast']}. "
            f"Temperature {data['temperature']} degrees {data['temperature_unit']}. "
            f"Wind {data['wind_speed']} {data['wind_direction']}. {precip_text}. "
            f"The Wanderer's brief take. 1-2 sentences.",
            150,
        )
        if user and not user.get("utility_mode", True):
            reply = f"{comment}\nSource: api.weather.gov"
        else:
            reply = _utility_reply(
                f"Weather for {data['place']}",
                [
                    f"Forecast: {data['forecast']}",
                    f"Temperature: {data['temperature']} {data['temperature_unit']}",
                    f"Wind: {data['wind_speed']} {data['wind_direction']}".strip(),
                    f"Precipitation: {precip_text}",
                ],
                comment,
                "Source: api.weather.gov",
            )
        await safe_reply(ctx, reply)
    except Exception as e: log_error("weather_cmd", e)


@bot.command(name="weathervideo", aliases=["videoweather", "weatherreportvideo"])
async def weathervideo_cmd(ctx, *, location: str = None):
    try:
        if not await _should_handle_video_command(ctx):
            return
        msg_id = ctx.message.id
        if msg_id in _weathervideo_active:
            return
        _weathervideo_active.add(msg_id)
        await _setup(ctx)
        if not location:
            _weathervideo_active.discard(msg_id)
            await safe_reply(ctx, "Weather where? Give me a place if you want a report worth rendering.")
            return
        use_duo = _partner_bot_present(ctx)
        available, reason = video_renderer_available(BOT_NAME, duo=use_duo)
        if not available:
            _weathervideo_active.discard(msg_id)
            await safe_reply(ctx, f"Video rendering is unavailable on this host. {reason}")
            return
        time_hint = _weathervideo_time_hint(use_duo)
        await ctx.reply(random.choice([
            f"A weather report video would be clearer. Give me a moment. {time_hint}",
            f"I'll render the report properly. {time_hint}",
            f"If Scaramouche is here, he can argue with the forecast too. {time_hint}",
        ]))
        asyncio.ensure_future(_do_weathervideo(ctx, location, use_duo, msg_id))
    except Exception as e:
        _weathervideo_active.discard(ctx.message.id)
        log_error("weathervideo_cmd", e)
        await safe_reply(ctx, "...The weather video request failed before it began.")


async def _do_weathervideo(ctx, location: str, use_duo: bool, msg_id=None):
    try:
        time_hint = _weathervideo_time_hint(use_duo)
        await ctx.send(
            f"I'll pull Scaramouche into the report too. {time_hint}"
            if use_duo else
            f"I'm assembling the weather report now. {time_hint}"
        )
        data = await _fetch_nws_weather(location)
        if not data:
            await ctx.send("That location didn't resolve. Try `City, ST`, a ZIP code, or `lat,lon`."); return
        news_results = await search_web(f"{data['place']} weather news", max_results=3)
        notes = build_weather_video_notes(data["place"], data, news_results, duo=use_duo)
        title = f"{data['place']} Weather Report"
        summary = await (render_duo_debate_video(notes, title=title) if use_duo else render_teaching_video(BOT_NAME, notes, title=title))
        sources = "Weather source: api.weather.gov"
        search_sources = format_search_sources(news_results, max_results=3)
        if search_sources:
            sources = f"{sources}\n{search_sources}"
        await _send_video_summary(
            ctx,
            summary,
            "The report is ready." if not use_duo else "The duo weather report is ready.",
            sources_text=sources,
        )
    except Exception as e:
        log_error("do_weathervideo", e)
        await safe_send(ctx, f"The weather video failed. {e}")
    finally:
        if msg_id:
            _weathervideo_active.discard(msg_id)

@bot.command(name="lore")
async def lore_cmd(ctx, *, topic: str = None):
    try:
        if not topic: await safe_reply(ctx, "Lore about what?"); return
        user = await _setup(ctx)
        reply = await get_response(ctx.author.id, ctx.channel.id, f"Tell me about this from your personal perspective as the Wanderer: {topic}", user, ctx.author.display_name, ctx.author.mention)
        await safe_reply(ctx, reply)
    except Exception as e: log_error("lore_cmd", e)

@bot.command(name="search", aliases=["find", "lookup"])
async def search_cmd(ctx, *, query: str = None):
    try:
        if not query: await safe_reply(ctx, "Search for what?"); return
        user = await _setup(ctx)
        reply = await get_response(ctx.author.id, ctx.channel.id, f"Search and answer: {query}", user, ctx.author.display_name, ctx.author.mention, use_search=True)
        await safe_reply(ctx, reply)
    except Exception as e: log_error("search_cmd", e)

@bot.command(name="solve", aliases=["math", "essay", "write"])
async def solve_cmd(ctx, *, problem: str = None):
    try:
        if not problem: await safe_reply(ctx, "Solve what?"); return
        user = await _setup(ctx)
        reply = await get_response(ctx.author.id, ctx.channel.id, f"Solve or answer this accurately: {problem}", user, ctx.author.display_name, ctx.author.mention, use_search=True)
        await safe_reply(ctx, reply)
    except Exception as e: log_error("solve_cmd", e)

@bot.command(name="remind", aliases=["remindme"])
async def remind_cmd(ctx, minutes: int = None, *, reminder: str = None):
    try:
        if not minutes or not reminder: await safe_reply(ctx, "Usage: `!remind <minutes> <reminder>`"); return
        if not 1 <= minutes <= 10080: await safe_reply(ctx, "Between 1 minute and 7 days."); return
        await mem.add_reminder(ctx.author.id, ctx.channel.id, reminder, time.time() + minutes * 60)
        await safe_reply(ctx, f"...I'll remember that. {minutes} minute{'s' if minutes != 1 else ''}.")
    except Exception as e: log_error("remind_cmd", e)

@bot.command(name="translate")
async def translate_cmd(ctx, *, text: str = None):
    try:
        if not text: await safe_reply(ctx, "Translate what?"); return
        user = await _setup(ctx)
        reply = await get_response(ctx.author.id, ctx.channel.id, f"Rewrite this in your voice, keeping the meaning: '{text[:500]}'", user, ctx.author.display_name, ctx.author.mention)
        await safe_reply(ctx, reply)
    except Exception as e: log_error("translate_cmd", e)

@bot.command(name="insult")
async def insult_cmd(ctx, member: discord.Member = None):
    try:
        target = member or ctx.author
        reply = await qai(f"The Wanderer says one cutting but honest thing about {target.display_name}. Not gratuitous. Precise.", 150)
        if member: await ctx.send(f"{member.mention} {reply}")
        else: await safe_reply(ctx, reply)
    except Exception as e: log_error("insult_cmd", e)

@bot.command(name="dm", aliases=["private", "whisper"])
async def dm_cmd(ctx, *, message: str = None):
    try:
        user = await _setup(ctx)
        reply = await get_response(
            ctx.author.id, ctx.author.id, message or "The user wants to speak privately.",
            user, ctx.author.display_name, ctx.author.mention, is_dm=True
        )
        try: await ctx.author.send(reply); await ctx.message.add_reaction("📨")
        except discord.Forbidden: await safe_reply(ctx, "Your DMs are closed.")
    except Exception as e: log_error("dm_cmd", e)

@bot.command(name="remember")
async def remember_cmd(ctx, *, text: str = None):
    try:
        if not text:
            await safe_reply(ctx, "Tell me what I should remember.")
            return
        await _setup(ctx)
        await mem.set_callback_memory(ctx.author.id, text[:220])
        await mem.add_memory_event(ctx.author.id, "manual", text[:220], 5)
        scene_update = infer_scene_update(text, ctx.author.display_name)
        if scene_update:
            await mem.update_scene_state(ctx.channel.id, **scene_update)
        await safe_reply(ctx, "...Alright. I'll keep it.")
    except Exception as e: log_error("remember_cmd", e)

@bot.command(name="forget")
async def forget_cmd(ctx, *, topic: str = None):
    try:
        if not topic or topic.strip().lower() in {"all", "everything", "me"}:
            await ctx.send("Wipe my memory of you? Are you sure.", view=ResetView(ctx.author.id))
            return
        await _setup(ctx)
        result = await mem.forget_memory_matches(ctx.author.id, topic)
        removed = sum(result.values())
        if removed:
            await safe_reply(ctx, f"...Fine. I let go of {removed} thing{'s' if removed != 1 else ''} tied to '{topic}'.")
        else:
            await safe_reply(ctx, "Nothing obvious matched that.")
    except Exception as e: log_error("forget_cmd", e)

@bot.command(name="memories", aliases=["memorybank"])
async def memories_cmd(ctx):
    try:
        user = await _setup(ctx)
        topics = await mem.get_top_topics(ctx.author.id, 4)
        memories = await mem.get_memory_bank_entries(ctx.author.id, 6)
        scene = await mem.get_scene_state(ctx.channel.id)
        await safe_reply(ctx, _format_memory_snapshot(user, topics, memories, scene))
    except Exception as e: log_error("memories_cmd", e)

@bot.command(name="pinpromise")
async def pinpromise_cmd(ctx, *, text: str = None):
    try:
        await _pin_memory(ctx, "promise", text, 7)
    except Exception as e: log_error("pinpromise_cmd", e)

@bot.command(name="pinwound")
async def pinwound_cmd(ctx, *, text: str = None):
    try:
        await _pin_memory(ctx, "wound", text, 8)
    except Exception as e: log_error("pinwound_cmd", e)

@bot.command(name="pincomfort")
async def pincomfort_cmd(ctx, *, text: str = None):
    try:
        await _pin_memory(ctx, "comfort", text, 6)
    except Exception as e: log_error("pincomfort_cmd", e)

@bot.command(name="pinjoke")
async def pinjoke_cmd(ctx, *, text: str = None):
    try:
        await _pin_memory(ctx, "joke", text, 5, shared_joke=True)
    except Exception as e: log_error("pinjoke_cmd", e)

@bot.command(name="relationship")
async def relationship_cmd(ctx):
    try:
        user = await _setup(ctx)
        topics = await mem.get_top_topics(ctx.author.id, 3)
        marks = await mem.get_active_consequence_marks(ctx.author.id, 4)
        lines = _relationship_lines(user, topics, marks)
        await safe_reply(ctx, "\n".join(lines))
    except Exception as e: log_error("relationship_cmd", e)

@bot.command(name="arc")
async def arc_cmd(ctx):
    try:
        user = await _setup(ctx)
        arc = _current_arc(user)
        stage, stage_desc = _progression_parts(user)
        unlocks = describe_arc_unlocks(BOT_NAME, arc) or "No special unlocks yet."
        recent = await mem.get_recent_milestones(f"{BOT_NAME}:user:{ctx.author.id}", 2)
        lines = [
            f"Arc: {arc}",
            f"Progression: {stage} | {stage_desc}",
            f"Unlocks: {unlocks}",
        ]
        if recent:
            lines.append("Recent milestones: " + " | ".join(note[:120] for note in recent))
        await safe_reply(ctx, "\n".join(lines))
    except Exception as e: log_error("arc_cmd", e)

@bot.command(name="duostate")
async def duostate_cmd(ctx):
    try:
        speaker_mode = await mem.get_channel_speaker_mode(ctx.channel.id)
        duo = await mem.get_duo_session(ctx.channel.id)
        relation = await mem.get_bot_relationship(PARTNER_PAIR_KEY)
        stories = await mem.get_recent_duo_stories(ctx.channel.id, 4)
        cases = await mem.list_world_cases(channel_id=ctx.channel.id, limit=3)
        lines = _duostate_lines(speaker_mode, duo, relation, stories, cases)
        await safe_reply(ctx, "\n".join(lines))
    except Exception as e: log_error("duostate_cmd", e)

@bot.command(name="achievements", aliases=["gallery"])
async def achievements_cmd(ctx):
    try:
        entries = await mem.get_hidden_achievements(f"user:{ctx.author.id}", 12)
        await safe_reply(ctx, "\n".join(_achievement_gallery_lines(entries)))
    except Exception as e: log_error("achievements_cmd", e)

@bot.command(name="speaker", aliases=["activespeaker"])
async def speaker_cmd(ctx, mode: str = None):
    try:
        current = await mem.get_channel_speaker_mode(ctx.channel.id)
        if not mode:
            await safe_reply(ctx, f"Channel speaker mode: `{current}`.")
            return
        normalized = mode.strip().lower()
        mapping = {
            "auto": "auto",
            "both": "both",
            "scara": "scaramouche",
            "scaramouche": "scaramouche",
            "wanderer": "wanderer",
        }
        if normalized not in mapping:
            await safe_reply(ctx, "Use `!speaker auto`, `!speaker scaramouche`, `!speaker wanderer`, or `!speaker both`.")
            return
        await mem.set_channel_speaker_mode(ctx.channel.id, mapping[normalized])
        await safe_reply(ctx, f"...Alright. This channel is now set to `{mapping[normalized]}` mode.")
    except Exception as e: log_error("speaker_cmd", e)

@bot.command(name="both")
async def both_cmd(ctx, *, prompt: str = None):
    try:
        if not prompt:
            await safe_reply(ctx, "Ask something worth answering.")
            return
        user = await _setup(ctx)
        await _start_duo_mode(ctx, user, "both", prompt)
        reply = await get_response(
            ctx.author.id, ctx.channel.id, prompt, user, ctx.author.display_name, ctx.author.mention,
            extra_context="TWO_BOT_MODE: The user explicitly wants both bots to answer. Keep it to one or two sentences and never speak for the other bot.",
            channel_obj=ctx.channel,
        )
        await _reply_and_store(ctx, reply)
    except Exception as e: log_error("both_cmd", e)

@bot.command(name="duet")
async def duet_cmd(ctx, *, prompt: str = None):
    try:
        if not prompt:
            await safe_reply(ctx, "Set the scene first.")
            return
        user = await _setup(ctx)
        await _start_duo_mode(ctx, user, "duet", prompt)
        reply = await get_response(
            ctx.author.id, ctx.channel.id, f"Contribute one turn to this shared two-bot scene: {prompt}",
            user, ctx.author.display_name, ctx.author.mention,
            extra_context="DUET_MODE: contribute one short in-character turn, leave space for the other bot, and avoid narration tags.",
            channel_obj=ctx.channel,
        )
        await _reply_and_store(ctx, reply)
    except Exception as e: log_error("duet_cmd", e)

@bot.command(name="argue")
async def argue_cmd(ctx, *, topic: str = None):
    try:
        if not topic:
            await safe_reply(ctx, "Argue about what.")
            return
        user = await _setup(ctx)
        await _start_duo_mode(ctx, user, "argue", topic)
        reply = await get_response(
            ctx.author.id, ctx.channel.id, f"The user started a deliberate two-bot argument about: {topic}",
            user, ctx.author.display_name, ctx.author.mention,
            extra_context="ARGUE_MODE: take a sharp stance, challenge the other bot directly, and keep it to one or two sentences.",
            channel_obj=ctx.channel,
        )
        await _reply_and_store(ctx, reply)
    except Exception as e: log_error("argue_cmd", e)

@bot.command(name="compare")
async def compare_cmd(ctx, *, topic: str = None):
    try:
        if not topic:
            await safe_reply(ctx, "Compare what.")
            return
        user = await _setup(ctx)
        await _start_duo_mode(ctx, user, "compare", topic, story=True)
        reply = await get_response(
            ctx.author.id, ctx.channel.id, f"Give your verdict on this and make your difference from Scaramouche clear: {topic}",
            user, ctx.author.display_name, ctx.author.mention,
            extra_context="COMPARE_MODE: answer the prompt, then draw a quick contrast between your view and the other bot's likely view.",
            channel_obj=ctx.channel,
        )
        await _reply_and_store(ctx, reply)
    except Exception as e: log_error("compare_cmd", e)

@bot.command(name="interrogate")
async def interrogate_cmd(ctx, *, topic: str = None):
    try:
        if not topic:
            await safe_reply(ctx, "Interrogate what.")
            return
        user = await _setup(ctx)
        await _start_duo_mode(ctx, user, "interrogate", topic, story=True, enemy=topic)
        reply = await get_response(
            ctx.author.id, ctx.channel.id, f"Start a two-bot interrogation about: {topic}",
            user, ctx.author.display_name, ctx.author.mention,
            extra_context="INTERROGATE_MODE: ask one pointed question or observation, leaving room for the other bot to press further.",
            channel_obj=ctx.channel,
        )
        await _reply_and_store(ctx, reply)
    except Exception as e: log_error("interrogate_cmd", e)

@bot.command(name="choose")
async def choose_cmd(ctx, *, options: str = None):
    try:
        if not options or "|" not in options:
            await safe_reply(ctx, "Use `!choose option A | option B`.")
            return
        user = await _setup(ctx)
        await _start_duo_mode(ctx, user, "compare", options, story=True)
        reply = await get_response(
            ctx.author.id, ctx.channel.id, f"Choose between these options and justify it: {options}",
            user, ctx.author.display_name, ctx.author.mention,
            extra_context="CHOOSE_MODE: make a clear choice fast, then justify it cleanly.",
            channel_obj=ctx.channel,
        )
        await _reply_and_store(ctx, reply)
    except Exception as e: log_error("choose_cmd", e)

@bot.command(name="trial")
async def trial_cmd(ctx, *, charge: str = None):
    try:
        if not charge:
            await safe_reply(ctx, "Put someone on trial for something.")
            return
        user = await _setup(ctx)
        await _start_duo_mode(ctx, user, "trial", charge, story=True, enemy=charge)
        reply = await get_response(
            ctx.author.id, ctx.channel.id, f"Open a two-bot trial about this charge: {charge}",
            user, ctx.author.display_name, ctx.author.mention,
            extra_context="TRIAL_MODE: deliver a prosecution, defense, or judgment opening with controlled bite.",
            channel_obj=ctx.channel,
        )
        await _reply_and_store(ctx, reply)
    except Exception as e: log_error("trial_cmd", e)

@bot.command(name="mission")
async def mission_cmd(ctx, *, objective: str = None):
    try:
        if not objective:
            await safe_reply(ctx, "Mission objective.")
            return
        user = await _setup(ctx)
        await _start_duo_mode(ctx, user, "mission", objective, story=True, enemy=objective)
        reply = await get_response(
            ctx.author.id, ctx.channel.id, f"Plan a two-bot mission around this objective: {objective}",
            user, ctx.author.display_name, ctx.author.mention,
            extra_context="MISSION_MODE: assign one clear role, risk, or warning, leaving room for the other bot to complement it.",
            channel_obj=ctx.channel,
        )
        await _reply_and_store(ctx, reply)
    except Exception as e: log_error("mission_cmd", e)

@bot.command(name="truthdare", aliases=["tod"])
async def truthdare_cmd(ctx, *, prompt: str = None):
    try:
        topic = prompt or "truth or dare"
        user = await _setup(ctx)
        await _start_duo_mode(ctx, user, "truthdare", topic, story=True)
        reply = await get_response(
            ctx.author.id, ctx.channel.id, f"Start a two-bot truth-or-dare round with this setup: {topic}",
            user, ctx.author.display_name, ctx.author.mention,
            extra_context="TRUTHDARE_MODE: issue one pointed truth or dare challenge, leaving room for the other bot to escalate.",
            channel_obj=ctx.channel,
        )
        await _reply_and_store(ctx, reply)
    except Exception as e: log_error("truthdare_cmd", e)

@bot.command(name="scene")
async def scene_cmd(ctx):
    try:
        scene = await mem.get_scene_state(ctx.channel.id)
        duo = await mem.get_duo_session(ctx.channel.id)
        if not scene and not duo:
            await safe_reply(ctx, "This channel doesn't have much continuity yet.")
            return
        lines = []
        if scene:
            lines.append(f"Scene: {describe_scene_state(scene)}")
        if duo:
            lines.append(f"Duo mode: {duo.get('mode')} | topic={duo.get('topic')}")
        await safe_reply(ctx, "\n".join(lines))
    except Exception as e: log_error("scene_cmd", e)

@bot.command(name="world")
async def world_cmd(ctx):
    try:
        entities = await mem.list_world_entities(limit=8, channel_id=ctx.channel.id)
        await safe_reply(ctx, "\n".join(_world_lines(entities)))
    except Exception as e: log_error("world_cmd", e)

@bot.command(name="cases")
async def cases_cmd(ctx):
    try:
        cases = await mem.list_world_cases(channel_id=ctx.channel.id, limit=8)
        await safe_reply(ctx, "\n".join(_case_lines(cases)))
    except Exception as e: log_error("cases_cmd", e)

@bot.command(name="worldadd")
async def worldadd_cmd(ctx, entity_type: str = None, *, payload: str = None):
    try:
        if not entity_type or not payload:
            await safe_reply(ctx, "Use `!worldadd enemy Dottore | ruined laboratory trail`.")
            return
        if "|" in payload:
            name, summary = [part.strip() for part in payload.split("|", 1)]
        else:
            name, summary = payload.strip(), ""
        if not name:
            await safe_reply(ctx, "Give the world entry a name.")
            return
        normalized = entity_type.strip().lower()
        if normalized not in {"enemy", "ally", "gift", "place", "prop", "faction", "figure", "case"}:
            await safe_reply(ctx, "Use one of: enemy, ally, gift, place, prop, faction, figure, case.")
            return
        await mem.upsert_world_entity(
            normalized,
            name,
            summary=summary or f"Added manually by {ctx.author.display_name}.",
            status="remembered",
            channel_id=ctx.channel.id,
            owner_user_id=ctx.author.id,
            updated_by=BOT_NAME,
        )
        await safe_reply(ctx, f"...Alright. I filed `{name}` under `{normalized}`.")
    except Exception as e: log_error("worldadd_cmd", e)

@bot.command(name="insidejokes", aliases=["jokes"])
async def insidejokes_cmd(ctx):
    try:
        jokes = await mem.list_inside_jokes(ctx.author.id, 5)
        if not jokes:
            await safe_reply(ctx, "No persistent jokes worth recalling yet.")
            return
        await safe_reply(ctx, "Inside jokes:\n" + "\n".join(f"- {j[:140]}" for j in jokes))
    except Exception as e: log_error("insidejokes_cmd", e)

@bot.command(name="reset", aliases=["wipe"])
async def reset_cmd(ctx):
    try: await ctx.send("Wipe my memory of you? Are you sure.", view=ResetView(ctx.author.id))
    except Exception as e: log_error("reset_cmd", e)

@bot.command(name="nsfw")
async def nsfw_cmd(ctx, mode: str = None):
    try:
        user = await _setup(ctx); cur = user.get("nsfw_mode", False) if user else False
        new = True if mode == "on" else False if mode == "off" else not cur
        await mem.set_mode(ctx.author.id, "nsfw_mode", new)
        await safe_reply(ctx, "Unfiltered. Fine." if new else "Restrained again.")
    except Exception as e: log_error("nsfw_cmd", e)

@bot.command(name="proactive", aliases=["ping_me"])
async def proactive_cmd(ctx, mode: str = None):
    try:
        user = await _setup(ctx); cur = user.get("proactive", True) if user else True
        new = True if mode == "on" else False if mode == "off" else not cur
        await mem.set_mode(ctx.author.id, "proactive", new)
        await safe_reply(ctx, "I might reach out. Or not." if new else "Fine. I'll leave you alone.")
    except Exception as e: log_error("proactive_cmd", e)

@bot.command(name="dms", aliases=["allowdms", "stopdms"])
async def dms_cmd(ctx, mode: str = None):
    try:
        user = await _setup(ctx); cur = user.get("allow_dms", True) if user else True
        new = True if mode == "on" else False if mode == "off" else not cur
        await mem.set_mode(ctx.author.id, "allow_dms", new)
        await safe_reply(ctx, "...I'll message you sometimes." if new else "Understood. I won't.")
    except Exception as e: log_error("dms_cmd", e)

@bot.command(name="utility")
async def utility_cmd(ctx, mode: str = None):
    try:
        user = await _setup(ctx)
        if not mode:
            await safe_reply(ctx, f"Utility mode is `{_pref_label(user.get('utility_mode', True) if user else True)}`.")
            return
        normalized = mode.strip().lower()
        if normalized not in {"on", "off"}:
            await safe_reply(ctx, "Use `!utility on` or `!utility off`.")
            return
        enabled = normalized == "on"
        await mem.set_user_preference(ctx.author.id, "utility_mode", int(enabled))
        await safe_reply(ctx, f"Utility mode is `{_pref_label(enabled)}` now.")
    except Exception as e: log_error("utility_cmd", e)

@bot.command(name="duoauto")
async def duoauto_cmd(ctx, mode: str = None):
    try:
        user = await _setup(ctx)
        if not mode:
            await safe_reply(ctx, f"Duo autoplay is `{_pref_label(user.get('duo_autoplay', True) if user else True)}`.")
            return
        normalized = mode.strip().lower()
        if normalized not in {"on", "off"}:
            await safe_reply(ctx, "Use `!duoauto on` or `!duoauto off`.")
            return
        enabled = normalized == "on"
        await mem.set_user_preference(ctx.author.id, "duo_autoplay", int(enabled))
        await safe_reply(ctx, f"...Alright. Duo autoplay is `{_pref_label(enabled)}` now.")
    except Exception as e: log_error("duoauto_cmd", e)

@bot.command(name="rpdepth")
async def rpdepth_cmd(ctx, depth: str = None):
    try:
        user = await _setup(ctx)
        if not depth:
            await safe_reply(ctx, f"RP depth is `{(user or {}).get('rp_depth', 'medium')}`.")
            return
        normalized = depth.strip().lower()
        if normalized not in {"low", "medium", "high"}:
            await safe_reply(ctx, "Use `!rpdepth low`, `!rpdepth medium`, or `!rpdepth high`.")
            return
        await mem.set_user_preference(ctx.author.id, "rp_depth", normalized)
        await safe_reply(ctx, f"...Alright. RP depth is `{normalized}` now.")
    except Exception as e: log_error("rpdepth_cmd", e)

@bot.command(name="timezone")
async def timezone_cmd(ctx, *, timezone_name: str = None):
    try:
        user = await _setup(ctx)
        if not timezone_name:
            await safe_reply(ctx, f"Timezone: {user.get('timezone_name', 'America/Los_Angeles')}")
            return
        ZoneInfo(timezone_name.strip())
        await mem.set_timezone(ctx.author.id, timezone_name.strip())
        await safe_reply(ctx, f"Timezone set to `{timezone_name.strip()}`.")
    except Exception:
        await safe_reply(ctx, "Use a valid IANA timezone like `America/Los_Angeles`.")

@bot.command(name="quiethours")
async def quiethours_cmd(ctx, start_hour: int = None, end_hour: int = None):
    try:
        user = await _setup(ctx)
        if start_hour is None or end_hour is None:
            await safe_reply(ctx, f"Quiet hours: {user.get('quiet_hours_start', 23)}:00 to {user.get('quiet_hours_end', 8)}:00")
            return
        await mem.set_quiet_hours(ctx.author.id, start_hour, end_hour)
        await safe_reply(ctx, f"Quiet hours set to {start_hour % 24}:00-{end_hour % 24}:00.")
    except Exception as e: log_error("quiethours_cmd", e)

@bot.command(name="dmfreq")
async def dmfreq_cmd(ctx, hours: int = None):
    try:
        user = await _setup(ctx)
        if hours is None:
            await safe_reply(ctx, f"DM frequency floor: every {user.get('dm_frequency_hours', 8)} hour(s).")
            return
        await mem.set_dm_frequency(ctx.author.id, hours)
        await safe_reply(ctx, f"I'll wait at least {max(1, min(72, hours))} hour(s) between DMs.")
    except Exception as e: log_error("dmfreq_cmd", e)

@bot.command(name="dmgrace")
async def dmgrace_cmd(ctx, minutes: int = None):
    try:
        user = await _setup(ctx)
        if minutes is None:
            await safe_reply(ctx, f"Recent-activity DM grace: {user.get('recent_activity_grace_minutes', 45)} minute(s).")
            return
        await mem.set_recent_activity_grace(ctx.author.id, minutes)
        await safe_reply(ctx, f"I'll leave at least {max(5, min(720, minutes))} minute(s) after your recent activity before DMing.")
    except Exception as e: log_error("dmgrace_cmd", e)

@bot.command(name="mood")
async def mood_cmd(ctx):
    try:
        await _setup(ctx); s = await mem.get_mood(ctx.author.id)
        bar = "█" * (s + 10) + "░" * (20 - (s + 10))
        await safe_reply(ctx, f"`[{bar}]` {s:+d} — {mood_label(s)}")
    except Exception as e: log_error("mood_cmd", e)

@bot.command(name="affection")
async def affection_cmd(ctx):
    try:
        await _setup(ctx); user = await mem.get_user(ctx.author.id); s = user.get("affection", 0) if user else 0
        bar = "█" * (s // 5) + "░" * (20 - s // 5)
        await safe_reply(ctx, f"`[{bar}]` {s}/100 — {affection_tier(s)}")
    except Exception as e: log_error("affection_cmd", e)

@bot.command(name="trust")
async def trust_cmd(ctx):
    try:
        await _setup(ctx); user = await mem.get_user(ctx.author.id); s = user.get("trust", 0) if user else 0
        bar = "█" * (s // 5) + "░" * (20 - s // 5)
        await safe_reply(ctx, f"`[{bar}]` {s}/100 — {trust_tier(s)}")
    except Exception as e: log_error("trust_cmd", e)

@bot.command(name="whoami")
async def whoami_cmd(ctx):
    try:
        if not OWNER_ID or ctx.author.id != OWNER_ID: await safe_reply(ctx, "That's not for you."); return
        user = await _setup(ctx)
        reply = await get_response(ctx.author.id, ctx.channel.id, "What do you actually think about the fact that I built you. Be honest.", user, ctx.author.display_name, ctx.author.mention, is_owner=True)
        await safe_reply(ctx, reply)
    except Exception as e: log_error("whoami_cmd", e)

@bot.command(name="enrollface", aliases=["rememberface"])
async def enrollface_cmd(ctx):
    try:
        if not OWNER_ID or ctx.author.id != OWNER_ID:
            await safe_reply(ctx, "That's not for you.")
            return
        if not face_support_ready():
            await safe_reply(ctx, _face_feature_unavailable_text())
            return
        img, vid = await _command_face_media(ctx)
        if not img and not vid:
            await safe_reply(ctx, "Attach or reply to an image or video and use `!enrollface`.")
            return
        profile = await mem.get_face_profile(FACE_PROFILE_KEY)
        import aiohttp as _ah
        if vid:
            async with _ah.ClientSession() as s:
                async with s.get(vid.url) as r:
                    video_bytes = await r.read()
            frames = await asyncio.get_event_loop().run_in_executor(None, _extract_frames_blocking, video_bytes, 5)
            enrolled = enroll_face_profile_from_frames(profile, frames)
        else:
            async with _ah.ClientSession() as s:
                async with s.get(img.url) as r:
                    img_bytes = await r.read()
            enrolled = enroll_face_profile(profile, img_bytes)
        if not enrolled.get("ok"):
            await safe_reply(ctx, _face_enroll_failure_text(enrolled.get("reason", "")))
            return
        await mem.save_face_profile(FACE_PROFILE_KEY, ctx.author.id, ctx.author.display_name, enrolled["profile"])
        await safe_reply(ctx, _face_enroll_success_text(enrolled.get("sample_count", 0)))
    except Exception as e:
        log_error("enrollface_cmd", e)

@bot.command(name="faceinfo")
async def faceinfo_cmd(ctx):
    try:
        if not OWNER_ID or ctx.author.id != OWNER_ID:
            await safe_reply(ctx, "That's not for you.")
            return
        profile = await mem.get_face_profile(FACE_PROFILE_KEY)
        if not profile:
            await safe_reply(ctx, "No enrolled face profile yet.")
            return
        sample_count = int(profile.get("sample_count", 0) or 0)
        updated_ts = float(profile.get("updated_ts", 0) or 0)
        updated_label = datetime.fromtimestamp(updated_ts).strftime("%Y-%m-%d %H:%M") if updated_ts else "unknown"
        await safe_reply(ctx, f"`Face memory: enrolled` — {sample_count} sample(s), updated {updated_label}.")
    except Exception as e:
        log_error("faceinfo_cmd", e)

@bot.command(name="deleteface", aliases=["forgetface"])
async def deleteface_cmd(ctx):
    try:
        if not OWNER_ID or ctx.author.id != OWNER_ID:
            await safe_reply(ctx, "That's not for you.")
            return
        await mem.delete_face_profile(FACE_PROFILE_KEY)
        await safe_reply(ctx, _face_delete_text())
    except Exception as e:
        log_error("deleteface_cmd", e)

async def help_cmd(ctx):
    try:
        c = 0x6B7FD7
        e1 = discord.Embed(title="Commands (1/3) — Talk & Fight", description="*I'll say this once.*", color=c)
        for n, v in [
            ("🚶 `!wander`", "A thought while walking — unique to Wanderer"),
            ("🪞 `!reflect <topic>`", "A genuine, layered take — unique to Wanderer"),
            ("⏪ `!before [msg]`", "Then vs Now — what Scaramouche would've said — unique"),
            ("📓 `!journal`", "A journal entry about today — unique to Wanderer"),
            ("🧠 `!memory`", "A fragment from his past — unique to Wanderer"),
            ("📈 `!progress`", "How he's doing as a person — unique to Wanderer"),
            ("🔊 `!voice <msg>`", "Voice message · `!speak` `!say`"),
            ("📨 `!dm [msg]`", "He DMs you privately"),
            ("🤫 `!confess <text>`", "Tell him something"),
            ("🛋️ `!therapy <problem>`", "Advice — honest, not comfortable"),
            ("🌐 `!translate <text>`", "Rewritten in his voice"),
            ("⚔️ `!spar [msg]`", "Word battle"),
            ("🥊 `!duel @user`", "He referees an insult battle"),
            ("🎤 `!roast @user`", "Turn-based roast battle (5 rounds)"),
            ("⚡ `!arena [@user]`", "Dramatic mock Genshin battle"),
            ("🎯 `!dare`", "A real challenge"),
            ("🧩 `!riddle`", "A cryptic Genshin riddle"),
            ("🥠 `!fortune`", "A fortune in his voice"),
            ("💭 `!opinion <char>`", "His honest take on any Genshin character"),
            ("📜 `!lore <topic>`", "Genshin lore from his perspective"),
        ]: e1.add_field(name=n, value=v, inline=False)
        for n, v in [
            ("!both <prompt>", "Both bots answer in sequence"),
            ("!duet <prompt>", "Start a shared two-bot scene"),
            ("!argue <topic>", "Let both bots clash over a topic"),
            ("!compare <topic>", "Each bot gives a contrasting verdict"),
        ]: e1.add_field(name=n, value=v, inline=False)

        e2 = discord.Embed(title="Commands (2/3) — Assess & Create", color=c)
        for n, v in [
            ("🧠 `!trivia`", "Genshin lore trivia"),
            ("✅ `!answer <text>`", "Answer a trivia question"),
            ("🔍 `!judge [@user]`", "Honest character assessment"),
            ("👁️ `!stalk [@user]`", "What he's noticed about you"),
            ("👻 `!possess @user`", "Speaks as them, filtered through him"),
            ("📊 `!rate <thing>`", "Rates anything honestly"),
            ("💞 `!ship @u1 [@u2]`", "Compatibility — reluctant but honest"),
            ("⚖️ `!verdict <situation>`", "He rules on anything"),
            ("⚖️ `!debate <topic>`", "He argues a side"),
            ("🕵️ `!conspiracy <topic>`", "What travelers actually know"),
            ("🏆 `!rank`", "Ranks everyone he's noticed"),
            ("📝 `!haiku [topic]`", "A haiku — melancholic or wry"),
            ("📖 `!story <prompt>`", "Short story with actual weight"),
            ("✉️ `!letter [@user]`", "A letter — says more than it seems"),
            ("🌸 `!compliment [@user]`", "He means it but it costs him"),
            ("⚡ `!insult [@user]`", "Precise and honest"),
            ("🔮 `!prophecy [@user]`", "A cryptic but real prophecy"),
            ("😰 `!nightmare`", "A nightmare. Somehow about you."),
            ("🔍 `!search <query>`", "Web search with his commentary"),
            ("🧮 `!solve <problem>`", "Math, essays, Q&A · `!math` `!essay`"),
        ]: e2.add_field(name=n, value=v, inline=False)

        e3 = discord.Embed(title="Commands (3/3) — Settings & Stats", color=c)
        for n, v in [
            ("📊 `!stats`", "Your full relationship record"),
            ("🌡️ `!mood`", "His mood toward you"),
            ("💜 `!affection`", "His affection score"),
            ("🔒 `!trust`", "His trust level toward you"),
            ("⏰ `!remind <mins> <txt>`", "Reminder — he'll remember"),
            ("🌤️ `!weather <city>`", "Weather + his take on it"),
            ("🎥 `!weathervideo <city>`", "Render a weather report video; duo if Scaramouche is here"),
            ("📢 `!poll <question>`", "He puts a question to the room"),
            ("📋 `!summarize`", "Recent chat — his honest read"),
            ("🔇 `!mute [@user] [min]`", "Ignores someone"),
            ("🔊 `!unmute [@user]`", "Stops ignoring someone"),
            ("🔄 `!reset`", "Wipe your memory · `!forget`"),
            ("🔞 `!nsfw [on/off]`", "Toggle unfiltered mode"),
            ("📡 `!proactive [on/off]`", "Toggle unprompted messages"),
            ("💌 `!dms [on/off]`", "Toggle voluntary DMs"),
            ("📚 `!tedtalk`", "Attach a file — he teaches it as a voice lecture"),
            ("🎬 `!teachvideo <topic>`", "Render a lesson video from notes or an attachment"),
        ]: e3.add_field(name=n, value=v, inline=False)
        for n, v in [
            ("!memories", "See what he is actually holding onto"),
            ("!remember <text>", "Tell him to keep something"),
            ("!forget <topic>", "Forget one topic instead of everything"),
            ("!relationship / !arc", "See arc, progression, and conflict aftermath"),
            ("!duostate / !speaker", "Inspect duo mode or set the active speaker for this channel"),
            ("!pinpromise / !pinwound / !pincomfort / !pinjoke", "Pin more precise memories"),
            ("!utility / !duoauto / !rpdepth", "Tune utility output, duo chaining, and RP depth"),
        ]: e3.add_field(name=n, value=v, inline=False)
        e3.add_field(name="💡 Hidden Systems",
            value=("• Be kind 7 days → something rare happens once\n"
                   "• Build trust → he tells you things he wouldn't normally\n"
                   "• Say 'you can't change' → he has something to say about that\n"
                   "• Mention his hat → brief, pointed response\n"
                   "• Use his old names → he redirects. Firmly.\n"
                   "• Affection builds → he starts calling you something specific\n"
                   "• He reads the channel — knows what's been discussed"),
            inline=False)
        e3.set_footer(text="Wanderer Bot | Groq AI + Fish Audio")
        await ctx.send(embed=e1)
        await ctx.send(embed=e2)
        await ctx.send(embed=e3)
    except Exception as e:
        log_error("help_cmd", e)
        try: await ctx.send("Something went wrong displaying commands.")
        except: pass

@bot.command(name="wanhelp", aliases=["wandererhelp", "commands"])
async def wanhelp_cmd(ctx):
    await help_cmd(ctx)


dashboard_group = app_commands.Group(name="dashboard", description="Check relationship and scene continuity.")
world_group = app_commands.Group(name="world", description="Inspect or update the shared world state.")
prefs_group = app_commands.Group(name="prefs", description="Tune voice, utility, duo, and speaker preferences.")
duo_group = app_commands.Group(name="duo", description="Start or inspect coordinated two-bot scenes.")


@dashboard_group.command(name="relationship", description="Show trust, arc, and consequence scars.")
async def slash_relationship(interaction: discord.Interaction):
    try:
        user = await _setup_user(interaction.user)
        topics = await mem.get_top_topics(interaction.user.id, 3)
        marks = await mem.get_active_consequence_marks(interaction.user.id, 4)
        await _interaction_reply(interaction, "\n".join(_relationship_lines(user, topics, marks)))
    except Exception as e:
        log_error("slash_relationship", e)
        await _interaction_reply(interaction, "Something went wrong reading the relationship state.")


@dashboard_group.command(name="arc", description="Show the current progression arc and unlocks.")
async def slash_arc(interaction: discord.Interaction):
    try:
        user = await _setup_user(interaction.user)
        arc = _current_arc(user)
        stage, stage_desc = _progression_parts(user)
        unlocks = describe_arc_unlocks(BOT_NAME, arc) or "No special unlocks yet."
        recent = await mem.get_recent_milestones(f"{BOT_NAME}:user:{interaction.user.id}", 2)
        lines = [
            f"Arc: {arc}",
            f"Progression: {stage} | {stage_desc}",
            f"Unlocks: {unlocks}",
        ]
        if recent:
            lines.append("Recent milestones: " + " | ".join(note[:120] for note in recent))
        await _interaction_reply(interaction, "\n".join(lines))
    except Exception as e:
        log_error("slash_arc", e)
        await _interaction_reply(interaction, "Something went wrong reading the arc.")


@dashboard_group.command(name="duostate", description="Show current duo mode, speaker mode, and case state.")
async def slash_duostate(interaction: discord.Interaction):
    try:
        speaker_mode = await mem.get_channel_speaker_mode(interaction.channel_id)
        duo = await mem.get_duo_session(interaction.channel_id)
        relation = await mem.get_bot_relationship(PARTNER_PAIR_KEY)
        stories = await mem.get_recent_duo_stories(interaction.channel_id, 4)
        cases = await mem.list_world_cases(channel_id=interaction.channel_id, limit=3)
        await _interaction_reply(interaction, "\n".join(_duostate_lines(speaker_mode, duo, relation, stories, cases)))
    except Exception as e:
        log_error("slash_duostate", e)
        await _interaction_reply(interaction, "Something went wrong reading the duo state.")


@dashboard_group.command(name="scene", description="Show current scene memory and duo scene topic.")
async def slash_scene(interaction: discord.Interaction):
    try:
        scene = await mem.get_scene_state(interaction.channel_id)
        duo = await mem.get_duo_session(interaction.channel_id)
        if not scene and not duo:
            await _interaction_reply(interaction, "This channel doesn't have much continuity yet.")
            return
        lines = []
        if scene:
            lines.append(f"Scene: {describe_scene_state(scene)}")
        if duo:
            lines.append(f"Duo mode: {duo.get('mode')} | topic={duo.get('topic')}")
        await _interaction_reply(interaction, "\n".join(lines))
    except Exception as e:
        log_error("slash_scene", e)
        await _interaction_reply(interaction, "Something went wrong reading the scene.")

@dashboard_group.command(name="achievements", description="Show unlocked hidden achievements and a few rumored ones.")
async def slash_achievements(interaction: discord.Interaction):
    try:
        entries = await mem.get_hidden_achievements(f"user:{interaction.user.id}", 12)
        await _interaction_reply(interaction, "\n".join(_achievement_gallery_lines(entries)))
    except Exception as e:
        log_error("slash_achievements", e)
        await _interaction_reply(interaction, "Something went wrong reading the achievement gallery.")


@world_group.command(name="state", description="Show shared NPC, gift, place, and object memory.")
async def slash_world_state(interaction: discord.Interaction):
    try:
        entities = await mem.list_world_entities(limit=8, channel_id=interaction.channel_id)
        await _interaction_reply(interaction, "\n".join(_world_lines(entities)))
    except Exception as e:
        log_error("slash_world_state", e)
        await _interaction_reply(interaction, "Something went wrong reading the world state.")


@world_group.command(name="cases", description="Show open or recent shared cases in this channel.")
async def slash_world_cases(interaction: discord.Interaction):
    try:
        cases = await mem.list_world_cases(channel_id=interaction.channel_id, limit=8)
        await _interaction_reply(interaction, "\n".join(_case_lines(cases)))
    except Exception as e:
        log_error("slash_world_cases", e)
        await _interaction_reply(interaction, "Something went wrong reading the case log.")


@world_group.command(name="add", description="Add a shared world entry for both bots to remember.")
@app_commands.describe(entity_type="enemy, ally, gift, place, prop, faction, figure, or case", name="Name of the world entry", summary="Short note about why it matters")
async def slash_world_add(
    interaction: discord.Interaction,
    entity_type: str,
    name: str,
    summary: str = "",
):
    try:
        normalized = entity_type.strip().lower()
        if normalized not in {"enemy", "ally", "gift", "place", "prop", "faction", "figure", "case"}:
            await _interaction_reply(interaction, "Use one of: enemy, ally, gift, place, prop, faction, figure, case.")
            return
        await mem.upsert_world_entity(
            normalized,
            name,
            summary=summary or f"Added manually by {interaction.user.display_name}.",
            status="remembered",
            channel_id=interaction.channel_id,
            owner_user_id=interaction.user.id,
            updated_by=BOT_NAME,
        )
        await _interaction_reply(interaction, f"Filed `{name}` under `{normalized}`.")
    except Exception as e:
        log_error("slash_world_add", e)
        await _interaction_reply(interaction, "Something went wrong updating the world state.")


@prefs_group.command(name="voice", description="Turn voice-note replies on or off.")
@app_commands.choices(mode=[
    app_commands.Choice(name="On", value="on"),
    app_commands.Choice(name="Off", value="off"),
    app_commands.Choice(name="Status", value="status"),
])
async def slash_pref_voice(interaction: discord.Interaction, mode: app_commands.Choice[str]):
    try:
        user = await _setup_user(interaction.user)
        value = mode.value
        if value == "status":
            await _interaction_reply(interaction, f"Voice notes are `{_pref_label(user.get('voice_enabled', True) if user else True)}`.")
            return
        enabled = value == "on"
        await mem.set_user_preference(interaction.user.id, "voice_enabled", int(enabled))
        await _interaction_reply(interaction, f"Voice notes are `{_pref_label(enabled)}` now.")
    except Exception as e:
        log_error("slash_pref_voice", e)
        await _interaction_reply(interaction, "Something went wrong updating voice preference.")


@prefs_group.command(name="utility", description="Toggle cleaner utility formatting for facts and weather.")
@app_commands.choices(mode=[
    app_commands.Choice(name="On", value="on"),
    app_commands.Choice(name="Off", value="off"),
])
async def slash_pref_utility(interaction: discord.Interaction, mode: app_commands.Choice[str]):
    try:
        enabled = mode.value == "on"
        await _setup_user(interaction.user)
        await mem.set_user_preference(interaction.user.id, "utility_mode", int(enabled))
        await _interaction_reply(interaction, f"Utility mode is `{_pref_label(enabled)}` now.")
    except Exception as e:
        log_error("slash_pref_utility", e)
        await _interaction_reply(interaction, "Something went wrong updating utility mode.")


@prefs_group.command(name="duoauto", description="Toggle extended duo autoplay chains.")
@app_commands.choices(mode=[
    app_commands.Choice(name="On", value="on"),
    app_commands.Choice(name="Off", value="off"),
])
async def slash_pref_duoauto(interaction: discord.Interaction, mode: app_commands.Choice[str]):
    try:
        enabled = mode.value == "on"
        await _setup_user(interaction.user)
        await mem.set_user_preference(interaction.user.id, "duo_autoplay", int(enabled))
        await _interaction_reply(interaction, f"Duo autoplay is `{_pref_label(enabled)}` now.")
    except Exception as e:
        log_error("slash_pref_duoauto", e)
        await _interaction_reply(interaction, "Something went wrong updating duo autoplay.")


@prefs_group.command(name="rpdepth", description="Set how brief or elaborate replies should be.")
@app_commands.choices(level=[
    app_commands.Choice(name="Low", value="low"),
    app_commands.Choice(name="Medium", value="medium"),
    app_commands.Choice(name="High", value="high"),
])
async def slash_pref_rpdepth(interaction: discord.Interaction, level: app_commands.Choice[str]):
    try:
        await _setup_user(interaction.user)
        await mem.set_user_preference(interaction.user.id, "rp_depth", level.value)
        await _interaction_reply(interaction, f"RP depth is now `{level.value}`.")
    except Exception as e:
        log_error("slash_pref_rpdepth", e)
        await _interaction_reply(interaction, "Something went wrong updating RP depth.")


@prefs_group.command(name="speaker", description="Choose who should ambiently respond in this channel.")
@app_commands.choices(mode=[
    app_commands.Choice(name="Auto", value="auto"),
    app_commands.Choice(name="Scaramouche", value="scaramouche"),
    app_commands.Choice(name="Wanderer", value="wanderer"),
    app_commands.Choice(name="Both", value="both"),
])
async def slash_pref_speaker(interaction: discord.Interaction, mode: app_commands.Choice[str]):
    try:
        await mem.set_channel_speaker_mode(interaction.channel_id, mode.value)
        await _interaction_reply(interaction, f"This channel is now set to `{mode.value}` mode.")
    except Exception as e:
        log_error("slash_pref_speaker", e)
        await _interaction_reply(interaction, "Something went wrong updating the speaker mode.")


@duo_group.command(name="start", description="Launch a coordinated two-bot scene from one slash menu.")
@app_commands.describe(mode="Which duo format to start", prompt="The topic, scene, charge, or question to throw at both bots")
@app_commands.choices(mode=[
    app_commands.Choice(name="Both", value="both"),
    app_commands.Choice(name="Duet", value="duet"),
    app_commands.Choice(name="Argue", value="argue"),
    app_commands.Choice(name="Compare", value="compare"),
    app_commands.Choice(name="Interrogate", value="interrogate"),
    app_commands.Choice(name="Trial", value="trial"),
    app_commands.Choice(name="Mission", value="mission"),
    app_commands.Choice(name="Truth or Dare", value="truthdare"),
])
async def slash_duo_start(interaction: discord.Interaction, mode: app_commands.Choice[str], prompt: str):
    try:
        if not interaction.channel:
            await _interaction_reply(interaction, "This needs a channel to stage the duo in.")
            return
        mode_value = mode.value
        config = {
            "both": ("TWO_BOT_MODE: The user explicitly wants both bots to answer. Keep it to one or two sentences and never speak for the other bot.", False, ""),
            "duet": ("DUET_MODE: contribute one short in-character turn, leave space for the other bot, and avoid narration tags.", False, ""),
            "argue": ("ARGUE_MODE: take a sharp stance, challenge the other bot directly, and keep it to one or two sentences.", False, ""),
            "compare": ("COMPARE_MODE: answer the prompt, then draw a quick contrast between your view and the other bot's likely view.", True, ""),
            "interrogate": ("INTERROGATE_MODE: ask one pointed question or observation, leaving room for the other bot to press further.", True, prompt),
            "trial": ("TRIAL_MODE: deliver a prosecution, defense, or judgment opening with controlled bite.", True, prompt),
            "mission": ("MISSION_MODE: assign one clear role, risk, or warning, leaving room for the other bot to complement it.", True, prompt),
            "truthdare": ("TRUTHDARE_MODE: issue one pointed truth or dare challenge, leaving room for the other bot to escalate.", True, ""),
        }
        extra_context, story, enemy = config[mode_value]
        await interaction.response.defer(thinking=True)
        user, reply = await _run_duo_prompt_for_actor(
            interaction.user,
            interaction.channel,
            mode_value,
            prompt if mode_value == "both" else (
                f"Contribute one turn to this shared two-bot scene: {prompt}" if mode_value == "duet"
                else f"The user started a deliberate two-bot argument about: {prompt}" if mode_value == "argue"
                else f"Give your verdict on this and make your difference from {PARTNER_NAME.title()} clear: {prompt}" if mode_value == "compare"
                else f"Start a two-bot interrogation about: {prompt}" if mode_value == "interrogate"
                else f"Open a two-bot trial about this charge: {prompt}" if mode_value == "trial"
                else f"Plan a two-bot mission around this objective: {prompt}" if mode_value == "mission"
                else f"Start a two-bot truth-or-dare round with this setup: {prompt}"
            ),
            session_topic=prompt,
            story=story,
            enemy=enemy,
            extra_context=extra_context,
        )
        _ = user
        await _reply_and_store_interaction(interaction, reply)
    except Exception as e:
        log_error("slash_duo_start", e)
        if interaction.response.is_done():
            await interaction.followup.send("Something went wrong starting the duo scene.")
        else:
            await interaction.response.send_message("Something went wrong starting the duo scene.")


@duo_group.command(name="state", description="Show current duo mode and world-case carryover.")
async def slash_duo_state(interaction: discord.Interaction):
    try:
        speaker_mode = await mem.get_channel_speaker_mode(interaction.channel_id)
        duo = await mem.get_duo_session(interaction.channel_id)
        relation = await mem.get_bot_relationship(PARTNER_PAIR_KEY)
        stories = await mem.get_recent_duo_stories(interaction.channel_id, 4)
        cases = await mem.list_world_cases(channel_id=interaction.channel_id, limit=3)
        await _interaction_reply(interaction, "\n".join(_duostate_lines(speaker_mode, duo, relation, stories, cases)))
    except Exception as e:
        log_error("slash_duo_state", e)
        await _interaction_reply(interaction, "Something went wrong reading the duo state.")


for _group in (dashboard_group, world_group, prefs_group, duo_group):
    try:
        bot.tree.add_command(_group)
    except Exception:
        pass

@bot.command(name="logs")
async def logs_cmd(ctx, *, target: str = None):
    """Owner-only: view conversation logs with a user."""
    try:
        if not OWNER_ID or ctx.author.id != OWNER_ID:
            await safe_reply(ctx, "That's not for you.")
            return
        if not target:
            all_users = await mem.get_top_users(500)
            blocked = [u for u in all_users if u["user_id"] in _dm_blocked_users]
            if not blocked:
                await safe_reply(ctx, "No blocked users. Use `!logs <name or ID>` to view any user's logs.")
                return
            lines = []
            for i, u in enumerate(blocked, 1):
                lines.append(f"`{i}.` **{u['display_name']}** — {u['message_count']} msgs — ID: `{u['user_id']}`")
            header = f"**Blocked users ({len(blocked)}):**\nUse `!logs <number>` to read their conversation.\n\n"
            page = header + "\n".join(lines)
            await safe_reply(ctx, page[:2000])
            return
        target = target.strip()
        all_users = await mem.get_top_users(500)
        blocked = [u for u in all_users if u["user_id"] in _dm_blocked_users]
        user_record = None
        if target.isdigit():
            idx = int(target)
            if 1 <= idx <= len(blocked):
                user_record = blocked[idx - 1]
            else:
                for u in all_users:
                    if u["user_id"] == int(target):
                        user_record = u
                        break
        if not user_record:
            target_lower = target.lower()
            for u in all_users:
                if target_lower in u["display_name"].lower():
                    user_record = u
                    break
        if not user_record:
            await safe_reply(ctx, f"No user matching `{target}`.")
            return
        logs = await mem.get_user_logs(user_record["user_id"], limit=200)
        if not logs:
            await safe_reply(ctx, f"No conversation logs found for **{user_record['display_name']}**.")
            return
        lines = [f"**Conversation log with {user_record['display_name']}** ({len(logs)} messages):\n"]
        for msg in logs:
            ts = msg.get("ts", 0)
            time_str = datetime.fromtimestamp(ts).strftime("%m/%d %H:%M") if ts else "?"
            role_label = "🧑" if msg["role"] == "user" else "🤖"
            content = (msg["content"] or "")[:300]
            if len(msg.get("content", "") or "") > 300:
                content += "..."
            lines.append(f"`{time_str}` {role_label} {content}")
        pages = []
        page = ""
        for line in lines:
            if len(page) + len(line) + 1 > 1900:
                pages.append(page)
                page = ""
            page += line + "\n"
        if page:
            pages.append(page)
        for p in pages:
            await safe_reply(ctx, p)
    except Exception as e:
        log_error("logs_cmd", e)

@bot.command(name="owneronly")
async def owneronly_cmd(ctx):
    """Owner-only: toggle whether the bot talks to anyone else."""
    try:
        global _owner_only_mode
        if not OWNER_ID or ctx.author.id != OWNER_ID:
            await safe_reply(ctx, "That's not for you.")
            return
        _owner_only_mode = not _owner_only_mode
        if _owner_only_mode:
            await safe_reply(ctx, "Owner-only mode **ON**. I'll ignore everyone except you now.")
        else:
            await safe_reply(ctx, "Owner-only mode **OFF**. I'll talk to everyone again.")
    except Exception as e:
        log_error("owneronly_cmd", e)

@bot.command(name="servers")
async def servers_cmd(ctx):
    """Owner-only: list every guild the bot is currently in."""
    try:
        if not OWNER_ID or ctx.author.id != OWNER_ID:
            await safe_reply(ctx, "That's not for you.")
            return
        guilds = sorted(bot.guilds, key=lambda g: g.member_count or 0, reverse=True)
        if not guilds:
            await safe_reply(ctx, "I'm not in any servers.")
            return
        lines = []
        for i, g in enumerate(guilds, 1):
            try:
                owner_in = await g.fetch_member(OWNER_ID)
            except discord.NotFound:
                owner_in = None
            except Exception:
                owner_in = g.get_member(OWNER_ID)
            tag = "✅" if owner_in else "⚠️ *you're not in this one*"
            lines.append(f"`{i}.` **{g.name}** — {g.member_count} members — {tag} — ID: `{g.id}`")
        header = f"I'm in **{len(guilds)}** server(s).\nUse `!leaveserver <number>` or `!leaveserver <server ID>` to make me leave one.\n"
        pages = []
        page = header
        for line in lines:
            if len(page) + len(line) + 1 > 1900:
                pages.append(page)
                page = ""
            page += line + "\n"
        if page:
            pages.append(page)
        for p in pages:
            await safe_reply(ctx, p)
    except Exception as e:
        log_error("servers_cmd", e)

@bot.command(name="leaveserver")
async def leaveserver_cmd(ctx, *, target: str = None):
    """Owner-only: leave a server by list number or guild ID."""
    try:
        if not OWNER_ID or ctx.author.id != OWNER_ID:
            await safe_reply(ctx, "That's not for you.")
            return
        if not target:
            await safe_reply(ctx, "Usage: `!leaveserver <number>` (from `!servers` list) or `!leaveserver <server ID>`")
            return
        target = target.strip()
        guild_to_leave = None
        if target.isdigit():
            idx = int(target)
            guilds = sorted(bot.guilds, key=lambda g: g.member_count or 0, reverse=True)
            if 1 <= idx <= len(guilds):
                guild_to_leave = guilds[idx - 1]
            else:
                guild_to_leave = bot.get_guild(int(target))
        else:
            try:
                guild_to_leave = bot.get_guild(int(target))
            except ValueError:
                pass
        if not guild_to_leave:
            await safe_reply(ctx, f"Couldn't find a server matching `{target}`. Use `!servers` to see the list.")
            return
        name = guild_to_leave.name
        await guild_to_leave.leave()
        await safe_reply(ctx, f"Left **{name}**.")
    except Exception as e:
        log_error("leaveserver_cmd", e)

@bot.command(name="dmlist")
async def dmlist_cmd(ctx):
    """Owner-only: list users who have DM'd the bot."""
    try:
        if not OWNER_ID or ctx.author.id != OWNER_ID:
            await safe_reply(ctx, "That's not for you.")
            return
        all_users = await mem.get_top_users(200)
        if not all_users:
            await safe_reply(ctx, "No users in my records.")
            return
        guild_member_ids = set()
        for g in bot.guilds:
            for m in g.members:
                guild_member_ids.add(m.id)
        dm_users = [u for u in all_users if u["user_id"] not in guild_member_ids and u["user_id"] != bot.user.id]
        if not dm_users:
            await safe_reply(ctx, "No DM-only users found. Everyone in my records is also in a shared server.")
            return
        lines = []
        for i, u in enumerate(dm_users, 1):
            blocked = " 🚫 **BLOCKED**" if u["user_id"] in _dm_blocked_users else ""
            lines.append(f"`{i}.` **{u['display_name']}** — {u['message_count']} msgs — ID: `{u['user_id']}`{blocked}")
        header = f"**DM-only users ({len(dm_users)}):**\nUse `!blockdm <number>` to block or `!unblockdm <number>` to unblock.\n\n"
        pages = []
        page = header
        for line in lines:
            if len(page) + len(line) + 1 > 1900:
                pages.append(page)
                page = ""
            page += line + "\n"
        if page:
            pages.append(page)
        for p in pages:
            await safe_reply(ctx, p)
    except Exception as e:
        log_error("dmlist_cmd", e)

@bot.command(name="blockall")
async def blockall_cmd(ctx):
    """Owner-only: block all strangers (users not in any server the owner is in)."""
    try:
        if not OWNER_ID or ctx.author.id != OWNER_ID:
            await safe_reply(ctx, "That's not for you.")
            return
        owner_guild_ids = set()
        for g in bot.guilds:
            try:
                m = await g.fetch_member(OWNER_ID)
                if m:
                    owner_guild_ids.add(g.id)
            except Exception:
                pass
        safe_user_ids = {OWNER_ID, bot.user.id}
        if PARTNER_BOT_ID:
            safe_user_ids.add(PARTNER_BOT_ID)
        for g in bot.guilds:
            if g.id in owner_guild_ids:
                for m in g.members:
                    safe_user_ids.add(m.id)
        all_users = await mem.get_top_users(500)
        blocked_count = 0
        blocked_names = []
        farewell = ("I am currently in test mode, I will be officially placed in public in the future. "
                     "We can continue our conversation on a later date. This is my last message.")
        for u in all_users:
            uid = u["user_id"]
            if uid in safe_user_ids or uid in _dm_blocked_users:
                continue
            _dm_blocked_users.add(uid)
            await mem.block_user(uid)
            blocked_names.append(u["display_name"])
            blocked_count += 1
            try:
                discord_user = await bot.fetch_user(uid)
                dm_channel = await discord_user.create_dm()
                await dm_channel.send(farewell)
            except Exception:
                pass
        if blocked_count == 0:
            await safe_reply(ctx, "No strangers to block. Everyone in my records shares a server with you.")
        else:
            names_preview = ", ".join(blocked_names[:15])
            if len(blocked_names) > 15:
                names_preview += f" ... and {len(blocked_names) - 15} more"
            await safe_reply(ctx, f"Blocked **{blocked_count}** stranger(s): {names_preview}\n\nFarewell messages sent. They're invisible to me now.")
    except Exception as e:
        log_error("blockall_cmd", e)

@bot.command(name="blockdm")
async def blockdm_cmd(ctx, *, target: str = None):
    """Owner-only: block a user. Sends a farewell message."""
    try:
        if not OWNER_ID or ctx.author.id != OWNER_ID:
            await safe_reply(ctx, "That's not for you.")
            return
        if not target:
            await safe_reply(ctx, "Usage: `!blockdm <number from !dmlist>` or `!blockdm <user ID>`")
            return
        target = target.strip()
        all_users = await mem.get_top_users(200)
        user_record = None
        if target.isdigit():
            idx = int(target)
            guild_member_ids = set()
            for g in bot.guilds:
                for m in g.members:
                    guild_member_ids.add(m.id)
            dm_users = [u for u in all_users if u["user_id"] not in guild_member_ids and u["user_id"] != bot.user.id]
            if 1 <= idx <= len(dm_users):
                user_record = dm_users[idx - 1]
            else:
                for u in all_users:
                    if u["user_id"] == int(target):
                        user_record = u
                        break
        if not user_record:
            target_lower = target.lower()
            for u in all_users:
                if target_lower in u["display_name"].lower():
                    user_record = u
                    break
        if not user_record:
            await safe_reply(ctx, f"No user matching `{target}`. Use `!dmlist` or `!whois` to see users.")
            return
        uid = user_record["user_id"]
        if uid in _dm_blocked_users:
            await safe_reply(ctx, f"**{user_record['display_name']}** is already blocked.")
            return
        farewell = ("I am currently in test mode, I will be officially placed in public in the future. "
                     "We can continue our conversation on a later date. This is my last message.")
        try:
            discord_user = await bot.fetch_user(uid)
            dm_channel = await discord_user.create_dm()
            await dm_channel.send(farewell)
        except Exception as e:
            log_error("blockdm_farewell", e)
        _dm_blocked_users.add(uid)
        await mem.block_user(uid)
        await safe_reply(ctx, f"Blocked **{user_record['display_name']}** (`{uid}`). Farewell message sent. They're invisible to me now.")
    except Exception as e:
        log_error("blockdm_cmd", e)

@bot.command(name="unblockdm")
async def unblockdm_cmd(ctx, *, target: str = None):
    """Owner-only: unblock a user."""
    try:
        if not OWNER_ID or ctx.author.id != OWNER_ID:
            await safe_reply(ctx, "That's not for you.")
            return
        if not target:
            await safe_reply(ctx, "Usage: `!unblockdm <number from !dmlist>` or `!unblockdm <user ID>`")
            return
        target = target.strip()
        all_users = await mem.get_top_users(200)
        guild_member_ids = set()
        for g in bot.guilds:
            for m in g.members:
                guild_member_ids.add(m.id)
        dm_users = [u for u in all_users if u["user_id"] not in guild_member_ids and u["user_id"] != bot.user.id]
        user_record = None
        if target.isdigit():
            idx = int(target)
            if 1 <= idx <= len(dm_users):
                user_record = dm_users[idx - 1]
            else:
                for u in all_users:
                    if u["user_id"] == int(target):
                        user_record = u
                        break
        if not user_record:
            target_lower = target.lower()
            for u in dm_users:
                if target_lower in u["display_name"].lower():
                    user_record = u
                    break
        if not user_record:
            await safe_reply(ctx, f"No user matching `{target}`. Use `!dmlist` to see the list.")
            return
        uid = user_record["user_id"]
        if uid not in _dm_blocked_users:
            await safe_reply(ctx, f"**{user_record['display_name']}** isn't blocked.")
            return
        _dm_blocked_users.discard(uid)
        await mem.unblock_user(uid)
        await safe_reply(ctx, f"Unblocked **{user_record['display_name']}** (`{uid}`). They can talk to me again.")
    except Exception as e:
        log_error("unblockdm_cmd", e)

@bot.command(name="whois")
async def whois_cmd(ctx, *, target: str = None):
    """Owner-only: look up a user from the ranking by number or name."""
    try:
        if not OWNER_ID or ctx.author.id != OWNER_ID:
            await safe_reply(ctx, "That's not for you.")
            return
        top = await mem.get_top_users(50)
        if not top:
            await safe_reply(ctx, "No users in my records yet.")
            return
        if not target:
            lines = []
            for i, u in enumerate(top, 1):
                lines.append(f"`{i}.` **{u['display_name']}** — {u['message_count']} msgs — ID: `{u['user_id']}`")
            header = f"**All known users ({len(top)}):**\nUse `!whois <number>` or `!whois <name>` for details.\n\n"
            pages = []
            page = header
            for line in lines:
                if len(page) + len(line) + 1 > 1900:
                    pages.append(page)
                    page = ""
                page += line + "\n"
            if page:
                pages.append(page)
            for p in pages:
                await safe_reply(ctx, p)
            return
        target = target.strip()
        user_record = None
        if target.isdigit():
            idx = int(target)
            if 1 <= idx <= len(top):
                user_record = top[idx - 1]
            else:
                for u in top:
                    if u["user_id"] == int(target):
                        user_record = u
                        break
        if not user_record:
            target_lower = target.lower()
            for u in top:
                if target_lower in u["display_name"].lower():
                    user_record = u
                    break
        if not user_record:
            await safe_reply(ctx, f"No user matching `{target}`.")
            return
        uid = user_record["user_id"]
        try:
            discord_user = await bot.fetch_user(uid)
        except Exception:
            discord_user = None
        shared = []
        for g in bot.guilds:
            try:
                m = await g.fetch_member(uid)
                if m:
                    shared.append(g.name)
            except Exception:
                pass
        embed = discord.Embed(title=f"Who is: {user_record['display_name']}", color=0x6B7FD7)
        embed.add_field(name="User ID", value=f"`{uid}`", inline=True)
        embed.add_field(name="Messages", value=str(user_record["message_count"]), inline=True)
        if discord_user:
            embed.add_field(name="Discord tag", value=str(discord_user), inline=True)
            created = discord_user.created_at.strftime("%b %d, %Y")
            embed.add_field(name="Account created", value=created, inline=True)
            if discord_user.avatar:
                embed.set_thumbnail(url=discord_user.avatar.url)
        if shared:
            embed.add_field(name="Shared servers", value=", ".join(shared), inline=False)
        else:
            embed.add_field(name="Shared servers", value="*None — they may have DM'd me or left*", inline=False)
        await ctx.send(embed=embed)
    except Exception as e:
        log_error("whois_cmd", e)

@bot.event
async def on_command_error(ctx, error):
    try:
        if isinstance(error, commands.CommandNotFound): pass
        elif isinstance(error, commands.MemberNotFound): pass
        elif isinstance(error, commands.MissingRequiredArgument): await safe_reply(ctx, "Missing something.")
        else: log_error("on_command_error", error)
    except: pass

if __name__ == "__main__":
    if not DISCORD_TOKEN: raise SystemExit("❌ DISCORD_TOKEN not set")
    if not _groq_keys:  raise SystemExit("❌ No GROQ_API_KEY set (need at least GROQ_API_KEY)")
    bot.run(DISCORD_TOKEN)

