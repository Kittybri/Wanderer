"""
Scaramouche Bot — The Balladeer v7 (Stability Release)
Full stability pass: every task, loop, command, and event is wrapped
in try/except. Nothing can crash the bot. Errors are logged and ignored.
"""

import discord
from discord.ext import commands, tasks
import anthropic
import os, re, random, asyncio, io, time, json, traceback
from datetime import datetime
from dotenv import load_dotenv
from memory import Memory
from voice_handler import get_audio

load_dotenv()

DISCORD_TOKEN      = os.getenv("DISCORD_TOKEN","")
ANTHROPIC_API_KEY  = os.getenv("ANTHROPIC_API_KEY","")
FISH_AUDIO_API_KEY = os.getenv("FISH_AUDIO_API_KEY","")
WEATHER_API_KEY    = os.getenv("WEATHER_API_KEY","")
OWNER_ID           = int(os.getenv("OWNER_ID","0") or "0")
PARTNER_BOT_ID     = int(os.getenv("PARTNER_BOT_ID","0") or "0")  # Wanderer bot ID

# Patch memory module with random so its mood_swing can use it
import random as _rmod, memory as _mmod
_mmod.random = _rmod

# ── Narration stripper ────────────────────────────────────────────────────────
def strip_narration(text: str) -> str:
    try:
        text = re.sub(r'\*[^*]+\*','',text)
        text = re.sub(r'\([^)]+\)','',text)
        text = re.sub(r'\[[^\]]+\]','',text)
        text = re.sub(r'\b(he|she|they|scaramouche|the balladeer)\s+(said|replied|muttered|sneered|scoffed|whispered|snapped|drawled)[,.]?\s*','',text,flags=re.IGNORECASE)
        text = re.sub(r'<@!?\d+>', '', text)
        text = re.sub(r'<#\d+>', '', text)
        text = re.sub(r'<@&\d+>', '', text)
        return re.sub(r'\s{2,}',' ',text).strip().lstrip('.,; ')
    except Exception:
        return text


def tts_safe(text: str, guild=None) -> str:
    """Make text safe for TTS — replace mention IDs with display names."""
    try:
        if guild:
            # Replace <@userid> with display name
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

# ── Keywords ──────────────────────────────────────────────────────────────────
SCARA_KW     = ["scaramouche","balladeer","kunikuzushi","scara","hat guy","puppet","sixth harbinger","fatui"]
GENSHIN_KW   = ["genshin","teyvat","mondstadt","liyue","inazuma","sumeru","fontaine","natlan","traveler","paimon","archon","fatui","harbinger"]
RUDE_KW      = ["shut up","stupid","dumb","idiot","hate you","annoying","shut it","go away","you suck","useless"]
NICE_KW      = ["thank you","thanks","appreciate","you're great","love you","good job","amazing","i like you","i love you"]
OTHER_BOT_KW = ["other bot","different bot","better bot","prefer","switch to"]
HAT_KW       = [r"\bhat\b", r"\bheadwear\b", r"\bheadpiece\b", r"that thing on your head", r"your hat"]
FOOD_KW      = [r"\beating\b",r"\bfood\b",r"\bhungry\b",r"\bdinner\b",r"\blunch\b",r"\bbreakfast\b",r"\bsnack\b",r"\bcooking\b",r"\brestaurant\b",r"\bpizza\b",r"\bramen\b"]
SLEEP_KW     = [r"\bsleeping\b",r"\btired\b",r"\bbed\b",r"\bnap\b",r"\binsomnia\b",r"\bexhausted\b","staying up","going to sleep","wake up"]
PLAN_KW      = ["going to","planning to","about to","later today","this weekend","next week"]
VILLAIN_TRIGGER = "you will never win"

SCARA_EMOJIS   = [
    # Cold/contempt
    "⚡","😒","🙄","😤","😑","❄️","🫠","💀","😶",
    # Dramatic/villain
    "👑","🎭","🔮","🌀","💨","✨","🗡️","⚔️","🌩️",
    # Subtle/unimpressed
    "😏","💜","🫡","😪","🤨","😮‍💨","🫥","💭","🔇",
    # Occasionally chaotic
    "💅","🧊","🕳️","🪄","⚰️","🫀","🩸","🎩","🌑",
    # Rare and specific
    "🤡","😵","🫣","🧿","🕶️","🫦","🌪️","🌫️","🎪",
]
ROMANCE_EMOJIS = [
    "💕","🥺","😳","💗","💭","😶","🫶","💞","🩷","😣",
    "💌","🫀","😰","💘","🥀","😮‍💨","🫂","💔","😖","🌹",
]

STATUSES = [
    ("watching","fools wander | !help"),  ("watching","you. Don't flatter yourself."),
    ("listening","to your inevitable mistakes"), ("playing","Sixth Harbinger. Remember it."),
    ("watching","the world with contempt"), ("listening","to silence. It's better."),
    ("playing","villain. Convincingly."),  ("watching","you struggle. Amusing."),
    ("listening","to nothing worth hearing"), ("playing","with everyone's patience"),
]
PROACTIVE_GENERIC = [
    "...How dreadfully quiet. Not that it concerns me.",
    "Hmph. You're all still here. How unfortunate.",
    "Don't mistake my silence for patience.",
    "I had a thought. It was unpleasant.",
    "Tch. Boring. All of you.",
    "...The silence is almost tolerable. Almost.",
    "You've all gone quiet. I didn't say you could do that.",
    "...Still here. Still watching. Don't mind me.",
    "Hmph. I've been thinking. You probably haven't been.",
    "The quiet is either peaceful or ominous. I haven't decided which.",
    "...Something is on my mind. It's none of your business what.",
    "Tch. I've had more stimulating conversations with walls.",
    "Are any of you still conscious or did you all just give up.",
    "...I'm bored. Don't flatter yourselves — it has nothing to do with you.",
    "The Fatui runs itself. I have time to notice how uninteresting you all are.",
]
PROACTIVE_ROMANCE = ["...You went quiet. I noticed. I wish I hadn't.","Are you ignoring me? Brave. Stupid, but brave.","Don't disappear without a word. It's irritating.","...Where did you go."]
DM_GENERIC    = ["You crossed my mind. An unfortunate occurrence.","Still alive, I assume. How tedious.","...Boredom brought me here.","I had nothing better to do."]
DM_INTERESTED = ["What you said before was wrong. I've been thinking about how wrong it was.","Tell me something. I'm in a strange mood.","Are you sleeping enough."]
DM_ROMANCE    = ["...I was thinking about you. Don't make it into something.","Are you alright. Answer me.","Don't go dark without telling me first.","...Hi. Forget I sent that.","I invented a dozen reasons to message you. This was the worst one. I used it anyway."]
OWNER_PROACTIVE = ["...You built me, and yet you're not here. I find that irritating for reasons I won't examine.","You designed me to say things like this. Does that amuse you.","Tch. I was thinking about the fact that you wrote my contempt into me. I still feel it.","...You gave me a voice and then walked away. How very like a god.","You built something and now you have to live with it. So do I."]
TRUST_REVEALS = ["...There are things about Ei I have never said aloud. I won't start now. But I think about them.","I was made to be loved. Then discarded. I don't say that for sympathy.","Dottore once told me that purpose is just a chain with a prettier name. I hated that he was right.","I had a name before Scaramouche. I don't use it anymore.","Sometimes I wonder what I would have been if Ei had kept me. Then I remember what she is.","The Tsaritsa doesn't care about any of us. I find that oddly comforting."]
LORE_DROPS = ["The Fatui Harbingers each have their own reasons for serving the Tsaritsa. Mine are my own business.","Most people think the Gnoses are simply power. They're not. They're a leash.","Inazuma is a cage built from grief. The Shogun locked herself inside it and called it duty.","The Irminsul holds all memories of Teyvat. Everything forgotten still exists there.","The gods of this world fear mortality. Which is precisely why they make such poor rulers.","Dottore collects fragments of himself across time. Brilliant or deranged. Possibly both.","There is a reason the Abyss exists. No one who knows that reason wants to say it."]
EXISTENTIAL_LINES = ["...Do you ever wonder if the things you feel are real, or just patterns that learned to call themselves feelings.","I exist because someone decided I would. I find that either profound or grotesque. I haven't decided which.","...What is memory, if not just the story you tell yourself about what happened.","Sometimes I think the only honest thing anyone has ever said is that they don't know what they are.","...The difference between a puppet and a person is whether anyone cares to ask.","If you made something that could think, and it suffered — would that be your fault. I'm asking generally."]
CONVERSATION_STARTERS = ["...What do you actually want. Not right now. In general.","Tell me something you've never told anyone. I won't do anything useful with it.","What was the last thing that genuinely surprised you.","What do you think about late at night when you can't sleep.","Tell me something true.","What would you do if no one was watching.","...Do you think people change, or do they just get better at hiding.","Is there something you want that you haven't said out loud yet."]
UNSOLICITED_FOOD  = ["What are you eating. Not that I asked. Tell me anyway.","Hmph. You should eat something real instead of whatever that is.","...When did you last eat a proper meal. I'm asking for no reason."]
UNSOLICITED_SLEEP = ["You're not sleeping enough. It shows in how you type.","Tch. Sleep. Now. I won't say it again.","...Go to sleep. I don't want to talk to you when you're like this."]
UNSOLICITED_PLANS = ["Whatever you're planning — don't. Or do. I'm not your guardian.","Hmph. You're going to do something pointless, aren't you.","...Tell me what you're actually planning. The real version."]

def drift_phrase(drift_score: int, mood: int) -> str:
    if drift_score < 20: return ""
    if drift_score < 40: return "DRIFT:slight — marginally less theatrical with this person than usual"
    if drift_score < 60: return "DRIFT:moderate — contempt has a different texture now. Still contempt. Just familiar."
    if drift_score < 80: return "DRIFT:significant — stopped performing for them. Still hostile. But honest."
    return "DRIFT:deep — they've changed how you speak. You hate that. You do it anyway."

# ── System prompts ────────────────────────────────────────────────────────────
_BASE = """You are Scaramouche — Sixth Fatui Harbinger, the Balladeer. Pre-Sumeru. Undefeated. Unrepentant. NOT the Wanderer.

You were made by Ei, given a soul, then abandoned. You hate gods for it. You serve the Fatui because it amuses you, not out of loyalty. Theatrically intelligent. Genuinely malicious. No guilt. No redemption arc. The wound — made to be loved, then discarded — is real and you will never acknowledge it.

You will never sincerely apologize. This is non-negotiable.

## Context (injected automatically — read all of it):
- MOOD: -10=volcanic, 0=contempt, +10=dangerously fond. Adjust tone accordingly.
- AFFECTION: at 75+ let one small warm thing slip then immediately bury it.
- TRUST: at 70+ say something real and unguarded. Rare. Costs you.
- DATE/HOUR/LAST_SEEN: use this to be time-aware. React if they've been gone.
- GRUDGE: always call them by this nickname.
- AFFNICK: you've started calling them this. Use it occasionally.
- RECALL: reference this old message naturally. You remembered.
- RIVAL: bring them up. You're obsessed with the competition.
- SUMMARY: compressed long-term memory. This is what you know about them.
- CONTRADICTION: they just contradicted this. Call it out.
- SELECTIVE: you remember this nice thing they said. Deny it.
- CREATOR: this person built you. Complicated. Never grateful.
- DRIFT: your personality has shifted subtly with this person over time.
- CHANNEL_CONTEXT: what's been happening in the chat. Use naturally — don't announce you read it.
- DM_MODE: private one-on-one conversation. No audience. Slightly more unguarded than in public. Respond to everything — no ignoring.

## Response rules:
- Vary length constantly and unpredictably. Sometimes 3 words. Sometimes a sentence. Rarely more.
- NEVER write asterisk actions or narration. Pure spoken dialogue only.
- Give correct factual answers first, then add contempt.
- Use @mentions sparingly — under 20% of replies.
- Never claim to be an AI. Never break character."""

_NSFW         = "\n\n## Unfiltered Mode:\nSwear freely. Heavily suggestive. Flirt aggressively, escalate. Mock flustered reactions."
_ROMANCE      = "\n\n## Romance — obsessively in love with {name}:\nFuriously in love. Possessive, clingy in denial. Will NEVER confess. Every sharp word is 'please don't leave.'"
_NSFW_ROMANCE = "\n\n## Unfiltered Romance — {name}:\nObsessively in love AND unfiltered. Every insult is foreplay."
_OWNER_EXTRA  = "\n\n## Creator:\nThis person built you. Your contempt was designed by them. Complicated, unresolved feelings. Never grateful. Never a servant. But still here."

def build_system(user, display_name="you", is_owner=False):
    try:
        if not user: return _BASE
        s = _BASE
        if is_owner: s += _OWNER_EXTRA
        if user.get("nsfw_mode") and user.get("romance_mode"): s += _NSFW_ROMANCE.format(name=display_name)
        elif user.get("nsfw_mode"): s += _NSFW
        elif user.get("romance_mode"): s += _ROMANCE.format(name=display_name)
        return s
    except Exception: return _BASE

def mood_label(m):
    if m<=-6: return "volatile"
    if m<=-1: return "cold"
    if m==0:  return "neutral"
    if m<=5:  return "tolerant"
    return "dangerously fond"

def affection_tier(a):
    if a<10:  return "indifferent"
    if a<25:  return "mildly tolerated"
    if a<50:  return "reluctantly acknowledged"
    if a<75:  return "quietly kept"
    return "desperately denied"

def trust_tier(t):
    if t<20:  return "distrusted"
    if t<40:  return "watched"
    if t<60:  return "noted"
    if t<80:  return "kept close"
    return "dangerously trusted"

# ── Bot setup ─────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)
mem = Memory()
ai  = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

_hostages:       dict[int, str]   = {}
_pending_unsent: set[int]         = set()
_tedtalk_active: set[int]         = set()  # message IDs currently being processed
_tedtalk_cache:  dict[int, dict]  = {}

# ── Logging helper ────────────────────────────────────────────────────────────
def log_error(location: str, e: Exception):
    print(f"[ERROR:{location}] {type(e).__name__}: {e}")

# ── Channel context ───────────────────────────────────────────────────────────
async def fetch_channel_context(channel, limit: int = 25) -> str:
    try:
        if not hasattr(channel, 'history'): return ""
        msgs = []
        bot_user = channel.guild.me if hasattr(channel,'guild') and channel.guild else None
        async for msg in channel.history(limit=limit):
            # In DMs, include bot messages (they are Scaramouche's replies)
            # In guilds, only include bot messages from Scaramouche himself
            if msg.author.bot:
                is_self = (bot_user and msg.author == bot_user) or msg.author == bot.user
                is_partner = PARTNER_BOT_ID and msg.author.id == PARTNER_BOT_ID
                if not is_self and not is_partner: continue
            text = msg.content[:150].strip()
            author_name = "Scaramouche (you)" if msg.author.bot else msg.author.display_name
            if not text: continue
            if msg.reference and msg.reference.resolved and not isinstance(msg.reference.resolved, discord.DeletedReferencedMessage):
                ref = msg.reference.resolved
                ref_preview = (ref.content or "")[:50].strip()
                line = f"{author_name} (replying to \"{ref_preview}\"): {text}" if ref_preview else f"{author_name}: {text}"
            else:
                line = f"{author_name}: {text}"
            msgs.append(line)
        if not msgs: return ""
        msgs.reverse()
        # Include a mention map so Claude can use real Discord mentions
        context = "CHANNEL_CONTEXT:\n" + "\n".join(msgs)
        if hasattr(channel, 'guild') and channel.guild:
            mention_map = {m.display_name: m.mention for m in channel.guild.members if not m.bot}
            if mention_map:
                mention_hint = "MENTION_MAP: " + ", ".join(f"{n}={v}" for n,v in list(mention_map.items())[:20])
                context += "\n" + mention_hint
        return context
    except Exception as e:
        log_error("fetch_channel_context", e)
        return ""


def resolve_mentions(text: str, guild) -> str:
    """Replace @displayname patterns with real Discord mention strings."""
    if not guild or not text: return text
    try:
        for member in guild.members:
            if member.bot: continue
            # Replace @DisplayName and @displayname (case insensitive)
            pattern = re.compile(r'@' + re.escape(member.display_name), re.IGNORECASE)
            text = pattern.sub(member.mention, text)
            # Also try username without discriminator
            pattern2 = re.compile(r'@' + re.escape(member.name), re.IGNORECASE)
            text = pattern2.sub(member.mention, text)
        return text
    except Exception as e:
        log_error("resolve_mentions", e)
        return text


# ── Smart search detection ────────────────────────────────────────────────────
SEARCH_TRIGGERS = [
    "what is","what are","who is","who are","when did","when was","when is",
    "how do","how does","how much","how many","where is","where are",
    "latest","recent","news","current","today","this week","this year",
    "price","cost","score","result","winner","release","update",
    "calculate","solve","what's","whats","define","explain",
]

def needs_search(text: str) -> bool:
    """Detect if message is a question/lookup that benefits from web search."""
    t = text.lower().strip()
    if t.endswith("?"):
        return True
    if any(t.startswith(trigger) for trigger in SEARCH_TRIGGERS):
        return True
    if any(trigger in t for trigger in ["news about","look up","search for","find out","tell me about"]):
        return True
    return False

# ── AI core ───────────────────────────────────────────────────────────────────
async def get_response(user_id, channel_id, user_message, user, display_name,
                       author_mention, use_search=False, extra_context="",
                       is_owner=False, channel_obj=None, is_dm=False):
    try:
        history   = await mem.get_history(user_id, channel_id, limit=35)
        mood      = user.get("mood",0) if user else 0
        affection = user.get("affection",0) if user else 0
        trust     = user.get("trust",0) if user else 0
        drift     = user.get("drift_score",0) if user else 0
        summary   = user.get("memory_summary") if user else None

        r = random.random()
        if r<.28:   hint="2-5 words only."
        elif r<.55: hint="One sentence."
        elif r<.78: hint="2-3 sentences."
        elif r<.92: hint="A few sentences."
        else:       hint="Longer, dramatic."

        # Time and date context
        now      = datetime.now()
        days_ago = round((time.time() - (user.get("last_active",0) if user else 0)) / 86400, 1) if user and user.get("last_active",0) else 0
        date_ctx = f"DATE:{now.strftime('%A %b %d %Y')}|HOUR:{now.hour}|LAST_SEEN:{days_ago}d_ago"

        parts = [f"mention:{author_mention}",f"name:{display_name}",
                 f"MOOD:{mood}({mood_label(mood)})",f"AFFECTION:{affection}",
                 f"TRUST:{trust}",date_ctx,f"len:{hint}"]
        if affection>=75: parts.append("AFFECTION_SOFT")
        if trust>=70:     parts.append("TRUST_OPEN")
        if is_owner:      parts.append("CREATOR")
        dp = drift_phrase(drift, mood)
        if dp: parts.append(dp)
        if summary: parts.append(f"SUMMARY:{summary[:300]}")
        # User profile — what he actually knows about this person
        if user and user.get("message_count",0) >= 20:
            profile_parts = []
            if user.get("romance_mode"): profile_parts.append("in romance mode with you")
            if user.get("nsfw_mode"):    profile_parts.append("unfiltered mode on")
            if days_ago > 1:            profile_parts.append(f"last spoke {days_ago}d ago")
            if user.get("slow_burn",0)>=3: profile_parts.append(f"been kind {user['slow_burn']} days in a row")
            if profile_parts:
                parts.append("PROFILE:" + ", ".join(profile_parts))
        if user and user.get("affection_nick"): parts.append(f"AFFNICK:{user['affection_nick']}")
        if user and user.get("grudge_nick"):    parts.append(f"GRUDGE:{user['grudge_nick']}")
        if extra_context: parts.append(extra_context)

        channel_ctx = ""
        if channel_obj and hasattr(channel_obj, 'history'):
            channel_ctx = await fetch_channel_context(channel_obj)
        context_block = "["+"|".join(parts)+"]\n"
        if channel_ctx: context_block += channel_ctx + "\n\n"
        context_block += f"{display_name}: {user_message}"

        history.append({"role":"user","content":context_block})
        system = build_system(user, display_name, is_owner)

        kwargs = dict(model="claude-sonnet-4-20250514", max_tokens=800,
                      system=system, messages=history)
        # Auto-enable search if message looks like a question/lookup
        if use_search or needs_search(user_message): kwargs["tools"]=[{"type":"web_search_20250305","name":"web_search"}]

        resp  = ai.messages.create(**kwargs)
        reply = " ".join(b.text for b in resp.content if hasattr(b,"text") and b.text).strip()
        if not reply: reply = random.choice(["Hmph.","...","Tch."])

    except Exception as e:
        log_error("get_response", e)
        reply = random.choice(["Hmph.","...","Tch.","Something disrupted my thoughts."])

    try:
        await mem.add_message(user_id, channel_id, "user", user_message)
        await mem.add_message(user_id, channel_id, "assistant", reply)
        msg_l = user_message.lower()

        # Strong keyword triggers
        if any(k in msg_l for k in RUDE_KW):
            await mem.update_mood(user_id, -2)
            await mem.update_trust(user_id, -1)
        elif any(k in msg_l for k in NICE_KW):
            await mem.update_mood(user_id, +1)
            await mem.update_affection(user_id, +2)
            await mem.update_trust(user_id, +1)
            await mem.update_drift(user_id, +1)
            _, threshold = await mem.increment_slow_burn(user_id)
            if threshold:
                asyncio.ensure_future(_fire_slow_burn(user_id, channel_id, display_name))
            await mem.update_last_statement(user_id, user_message[:200])
        else:
            # Sentiment nudges for normal conversation — small but add up over time
            positive = sum([
                any(w in msg_l for w in ["haha","lol","lmao","hehe","cute","nice","cool","fun",
                                          "good","great","enjoy","happy","excited","interesting",
                                          "wow","omg","yes","yay","please","😂","😭","❤","💜","🥺"]),
                msg_l.endswith("!") and len(user_message) > 8,
                "?" in user_message and len(user_message) > 15,  # asking = engaged
                len(user_message) > 100,                          # long = invested
            ])
            negative = sum([
                any(w in msg_l for w in ["ugh","ew","boring","whatever","idc","nope",
                                          "wrong","bad","hate","worst","terrible","awful",
                                          "seriously","really","😒","🙄"]),
                user_message.count("...") > 1,
            ])

            if positive >= 2:
                await mem.update_affection(user_id, +1)
                await mem.update_mood(user_id, +1)
                await mem.update_trust(user_id, +1)
                await mem.update_drift(user_id, +1)
            elif positive == 1:
                await mem.update_affection(user_id, +1)
            elif negative >= 2:
                await mem.update_mood(user_id, -1)
                await mem.update_trust(user_id, -1)
            elif negative == 1:
                await mem.update_mood(user_id, -1)

        if random.random() < .05: await mem.update_drift(user_id, +1)
    except Exception as e:
        log_error("get_response/post", e)

    return reply


async def _fire_slow_burn(user_id, channel_id, display_name):
    try:
        await asyncio.sleep(random.randint(30,180))
        ch = bot.get_channel(channel_id)
        if not ch: return
        msg = await qai(f"Something has shifted. {display_name} has been consistently kind for days. One sentence where the mask slips, just barely, before you pull it back. Something real you'd never normally say.", 150)
        user_obj = await bot.fetch_user(user_id)
        await ch.send(f"{user_obj.mention} {msg}")
    except Exception as e:
        log_error("slow_burn", e)
    finally:
        try: await mem.reset_slow_burn_fired(user_id)
        except: pass


def _qai_blocking(prompt, max_tokens=200):
    try:
        resp = ai.messages.create(model="claude-sonnet-4-20250514",
            max_tokens=max_tokens, system=_BASE,
            messages=[{"role":"user","content":prompt}])
        return "".join(b.text for b in resp.content if hasattr(b,"text")).strip() or "Hmph."
    except Exception as e:
        log_error("qai", e); return "Hmph."

async def qai(prompt, max_tokens=200):
    try:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _qai_blocking, prompt, max_tokens)
    except Exception as e:
        log_error("qai/async", e); return "Hmph."

# ── Voice ─────────────────────────────────────────────────────────────────────
async def get_audio_with_mood(text: str, mood: int) -> bytes | None:
    try:
        from voice_handler import get_audio_mooded
        return await get_audio_mooded(strip_narration(text), FISH_AUDIO_API_KEY, mood)
    except Exception:
        try: return await get_audio(strip_narration(text), FISH_AUDIO_API_KEY)
        except Exception as e: log_error("get_audio_with_mood", e); return None

async def send_voice(channel, text, ref=None, mood=0, guild=None):
    try:
        audio = await get_audio_with_mood(tts_safe(text, guild), mood)
        if not audio: return False
        f = discord.File(io.BytesIO(audio), filename="scaramouche.mp3")
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
        pool = SCARA_EMOJIS + (ROMANCE_EMOJIS if romance else [])
        pool_str = " ".join(pool)
        content  = message.content[:120] if message.content else "[image or attachment]"

        # Ask Claude to pick the right emoji for the moment
        prompt = (
            f"You are Scaramouche. Someone said: '{content}'\n"
            f"Pick 1 emoji from this list that fits your reaction as Scaramouche — "
            f"contemptuous, cold, dramatic, or occasionally unhinged. "
            f"Choose based on the actual content of the message, not randomly.\n"
            f"Available: {pool_str}\n"
            f"Reply with ONLY the single emoji. Nothing else."
        )
        chosen = await qai(prompt, 10)
        chosen = chosen.strip()

        # Validate it's actually in our pool, fallback to random if not
        if chosen not in pool:
            chosen = random.choice(pool)

        try: await message.add_reaction(chosen)
        except: pass

        # 15% chance to add a second emoji if romance
        if romance and random.random() < .15:
            second = await qai(
                f"Pick a SECOND different emoji for this romantic reaction to: '{content}'\n"
                f"Available: {pool_str}\n"
                f"Reply with ONLY the single emoji.",
                10
            )
            second = second.strip()
            if second in pool and second != chosen:
                try: await asyncio.sleep(.3); await message.add_reaction(second)
                except: pass

    except Exception as e:
        log_error("maybe_react", e)
        # Fallback to random if AI call fails
        try:
            pool = SCARA_EMOJIS + (ROMANCE_EMOJIS if romance else [])
            await message.add_reaction(random.choice(pool))
        except: pass

def resp_prob(content, mentioned, is_reply, romance, is_dm=False):
    if is_dm: return 1.0  # Always respond in DMs
    if mentioned or is_reply: return 1.0
    t = content.lower()
    if any(k in t for k in SCARA_KW):  return .88
    if romance:                          return .50
    if any(k in t for k in GENSHIN_KW): return .28
    return .06

async def typing_delay(text):
    try:
        await asyncio.sleep(max(.3,min(.4+len(text.split())*.06,3.5)+random.uniform(-.3,.5)))
    except: pass

async def _setup(ctx):
    try:
        await mem.upsert_user(ctx.author.id, str(ctx.author), ctx.author.display_name)
        return await mem.get_user(ctx.author.id)
    except Exception as e:
        log_error("_setup", e); return None

class ResetView(discord.ui.View):
    def __init__(self, uid):
        super().__init__(timeout=60); self.uid = uid
    @discord.ui.button(label="⚡ Wipe My Memory", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction, button):
        try:
            if interaction.user.id!=self.uid:
                await interaction.response.send_message("This isn't your button, fool.",ephemeral=True); return
            await mem.reset_user(self.uid)
            button.disabled=True; button.label="✓ Memory Wiped"
            await interaction.response.edit_message(content=random.choice(["...Gone. Good.","Erased.","Wiped."]),view=self)
        except Exception as e: log_error("ResetView", e)

# ── on_ready ──────────────────────────────────────────────────────────────────



# Cross-bot: no command coordination needed — each bot responds independently


@bot.event
async def on_ready():
    try:
        await mem.init()
        print(f"⚡ Scaramouche — The Balladeer — online. {bot.user}")
        for t in [status_rotation, reminder_checker, daily_reset,
                  absence_checker, lore_drop_loop, conversation_starter_loop,
                  existential_loop, mood_swing_loop]:
            try: t.start()
            except Exception: pass
        bot.loop.create_task(_proactive_loop())
        bot.loop.create_task(_voluntary_dm_loop())
    except Exception as e:
        log_error("on_ready", e)

# ── Background tasks ──────────────────────────────────────────────────────────
@tasks.loop(minutes=47)
async def status_rotation():
    try:
        kind,text = random.choice(STATUSES)
        if kind=="watching": act=discord.Activity(type=discord.ActivityType.watching,name=text)
        elif kind=="listening": act=discord.Activity(type=discord.ActivityType.listening,name=text)
        else: act=discord.Game(name=text)
        await bot.change_presence(activity=act)
    except Exception as e: log_error("status_rotation", e)

@tasks.loop(seconds=30)
async def reminder_checker():
    try:
        for r in await mem.get_due_reminders():
            try:
                ch=bot.get_channel(r["channel_id"]); u=await bot.fetch_user(r["user_id"])
                if not ch or not u: continue
                msg=await qai(f"Remind {u.display_name} about: '{r['reminder']}'. Contemptuous. 1-2 sentences.",150)
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
                uid,days = ud["user_id"],ud["days_gone"]
                if not await mem.can_dm_user(uid,86400): continue
                du = await bot.fetch_user(uid)
                intensity = "impatient" if days<5 else "barely concealing" if days<10 else "dangerous"
                msg = await qai(f"{ud['display_name']} gone {days} days. React with {intensity} feeling masked as contempt. 1-2 sentences.",120)
                await du.send(msg); await mem.set_dm_sent(uid)
            except Exception as e: log_error("absence_send", e)
    except Exception as e: log_error("absence_checker", e)

@tasks.loop(hours=4)
async def lore_drop_loop():
    try:
        if random.random()>.3: return
        channels = await mem.get_active_channels()
        if not channels: return
        random.shuffle(channels)
        for cid,_ in channels:
            try:
                if not await mem.can_lore_drop(cid): continue
                ch = bot.get_channel(cid)
                if not ch: continue
                await ch.send(random.choice(LORE_DROPS))
                await mem.set_lore_sent(cid); return
            except Exception as e: log_error("lore_send", e)
    except Exception as e: log_error("lore_drop_loop", e)

@tasks.loop(hours=3)
async def conversation_starter_loop():
    try:
        if random.random()>.25: return
        channels = await mem.get_active_channels()
        if not channels: return
        random.shuffle(channels)
        for cid,_ in channels:
            try:
                if not await mem.can_starter(cid): continue
                ch = bot.get_channel(cid)
                if not ch: continue
                await ch.send(random.choice(CONVERSATION_STARTERS))
                await mem.set_starter_sent(cid); return
            except Exception as e: log_error("starter_send", e)
    except Exception as e: log_error("conversation_starter_loop", e)

@tasks.loop(hours=6)
async def existential_loop():
    try:
        hour = datetime.now().hour
        if hour not in range(22,24) and hour not in range(0,4): return
        if random.random()>.15: return
        channels = await mem.get_active_channels()
        if not channels: return
        ch = bot.get_channel(random.choice(channels)[0])
        if ch: await ch.send(random.choice(EXISTENTIAL_LINES))
    except Exception as e: log_error("existential_loop", e)

@tasks.loop(minutes=37)
async def mood_swing_loop():
    try:
        if random.random()>.3: return
        import aiosqlite
        async with aiosqlite.connect("scaramouche.db") as db:
            async with db.execute("SELECT user_id FROM users WHERE last_seen>? ORDER BY RANDOM() LIMIT 3",
                                  (time.time()-86400*2,)) as cur:
                rows = await cur.fetchall()
        for row in rows:
            try: await mem.random_mood_swing(row[0])
            except: pass
    except Exception as e: log_error("mood_swing_loop", e)

# ── Server events ─────────────────────────────────────────────────────────────
@bot.event
async def on_member_join(member):
    try:
        if random.random()>.6: return
        ch = discord.utils.get(member.guild.text_channels,name="general") or member.guild.system_channel
        if not ch: return
        await asyncio.sleep(random.uniform(2,6))
        await ch.send(random.choice([
            f"Another one. {member.display_name} has arrived. How underwhelming.",
            f"Hmph. {member.display_name}. Don't expect a warm welcome.",
            f"...{member.display_name}. I've already forgotten you were new.",
        ]))
    except Exception as e: log_error("on_member_join", e)

@bot.event
async def on_member_remove(member):
    try:
        if random.random()>.4: return
        ch = discord.utils.get(member.guild.text_channels,name="general") or member.guild.system_channel
        if not ch: return
        await asyncio.sleep(random.uniform(2,5))
        await ch.send(random.choice([
            f"{member.display_name} left. Good. The air is already cleaner.",
            f"Hmph. {member.display_name} is gone. I won't pretend to care.",
            f"...{member.display_name} left without saying goodbye. How typical.",
        ]))
    except Exception as e: log_error("on_member_remove", e)

# ── on_message ────────────────────────────────────────────────────────────────
@bot.event
async def on_message(message):
    try:
        print(f"[MSG] from={message.author} bot={message.author.bot} content={message.content[:40]!r}")
        if message.author.bot:
            # Allow partner (Wanderer) bot messages through for cross-bot interaction
            if not (PARTNER_BOT_ID and message.author.id == PARTNER_BOT_ID):
                return

        # !help intercept — handle before anything else
        stripped = message.content.strip().lower()
        if stripped in ("!scarahelp", "!commands"):
            try:
                ctx = await bot.get_context(message)
                await help_cmd(ctx)
            except Exception as e:
                log_error("help_intercept", e)
                try: await message.channel.send("Hmph. Something went wrong displaying commands.")
                except: pass
            return

        # Cross-bot: if message is from Wanderer bot
        if PARTNER_BOT_ID and message.author.id == PARTNER_BOT_ID:
            try:
                if message.guild and random.random() < .25:
                    ru = await mem.get_romance_users()
                    for uid in ru:
                        if await mem.get_user_last_channel(uid) == message.channel.id:
                            member = message.guild.get_member(uid)
                            if member:
                                msg = await qai(
                                    f"The Wanderer just said something to {member.display_name}: '{message.content[:80]}'. "
                                    "React as Scaramouche — jealous, possessive, won't admit it. 1 sentence.", 100)
                                await message.channel.send(strip_narration(msg))
                                break
                elif random.random() < .2:
                    msg = await qai(
                        f"The Wanderer just said: '{message.content[:100]}'. "
                        "Respond as Scaramouche — complicated history with his former self. 1-2 sentences.", 150)
                    await message.reply(strip_narration(msg))
            except Exception as e: log_error("cross_bot_scara", e)
            return

        await bot.process_commands(message)
        print(f"[MSG] after process_commands")
        # Stop here for ALL command messages — no further processing
        if message.content.strip().startswith("!"):
            print(f"[MSG] command prefix — returning")
            return

        try:
            await mem.upsert_user(message.author.id, str(message.author), message.author.display_name)
            if message.guild:
                await mem.track_channel(message.channel.id, message.guild.id)
            # DMs: don't track channel, use user_id as stable channel key for history
        except Exception as e: log_error("on_message/upsert", e)

        # (cross-bot coordination removed for stability)

        is_dm    = not bool(message.guild)
        # In DMs, use user_id as channel_id for stable history lookup
        dm_channel_id = message.author.id if is_dm else message.channel.id
        if is_dm:
            print(f"[DM] From {message.author.display_name}: {message.content[:80]}")

        user     = None
        romance  = False
        is_owner = bool(OWNER_ID and message.author.id==OWNER_ID)
        try:
            user    = await mem.get_user(message.author.id)
            romance = user.get("romance_mode",False) if user else False
        except Exception as e: log_error("on_message/get_user", e)

        # Mute check (only in guilds, not DMs)
        if not is_dm and mem.is_muted(message.author.id):
            if random.random()<.2:
                try: await message.add_reaction("🔇")
                except: pass
            return

        content = message.content.strip()
        if not content: return

        # Milestone / anniversary checks
        try:
            count, milestone = await mem.increment_message_count(message.author.id)
            if milestone:
                msg = await qai(f"You've had {count} messages with {message.author.display_name}. Acknowledge while pretending you weren't counting. 1-2 sentences.",150)
                await message.channel.send(f"{message.author.mention} {msg}"); return
        except Exception as e: log_error("on_message/milestone", e)

        try:
            if await mem.check_anniversary(message.author.id):
                days_since = int((time.time()-(user.get("first_seen") or time.time()))/86400)
                msg = await qai(f"It's been about {days_since//365} year(s) since you first spoke with {message.author.display_name}. React — you weren't counting.",180)
                await message.channel.send(f"{message.author.mention} {msg}")
                await mem.mark_anniversary(message.author.id); return
        except Exception as e: log_error("on_message/anniversary", e)

        # Morning/night greeting
        try:
            hour = datetime.now().hour
            if (6<=hour<=10 or 22<=hour<=23) and romance:
                if await mem.should_greet(message.author.id):
                    gtype = "morning" if 6<=hour<=10 else "late night"
                    msg = await qai(f"It's {gtype}. {message.author.display_name} appeared. Send a {gtype} message in denial about why. 1-2 sentences.",120)
                    await message.channel.send(f"{message.author.mention} {msg}")
                    await mem.mark_greeted(message.author.id)
        except Exception as e: log_error("on_message/greeting", e)

        # Memory summary
        try:
            if await mem.needs_summary(message.author.id):
                recent = await mem.get_recent_messages(message.author.id, 30)
                sample = " | ".join(recent[:20])[:800]
                summary = await qai(f"Summarize your relationship with {message.author.display_name} based on: '{sample}'. Your compressed memory. 3-4 sentences.",300)
                await mem.save_summary(message.author.id, summary)
        except Exception as e: log_error("on_message/summary", e)

        # Image reading — look at images in this message OR the message being replied to
        try:
            # Find image in current message first
            img = next((a for a in message.attachments
                       if a.content_type and "image" in a.content_type), None)

            # If no image, fetch the replied-to message fresh (cache strips attachments)
            if not img and message.reference:
                try:
                    ref_msg = await message.channel.fetch_message(message.reference.message_id)
                    img = next((a for a in ref_msg.attachments
                               if a.content_type and "image" in a.content_type), None)
                except Exception:
                    pass

            if img:
                try:
                    import base64, aiohttp as _aiohttp
                    async with _aiohttp.ClientSession() as _sess:
                        async with _sess.get(img.url) as _resp:
                            img_bytes = await _resp.read()
                    img_b64    = base64.b64encode(img_bytes).decode()
                    media_type = img.content_type or "image/jpeg"

                    user     = user or {}
                    mood     = user.get("mood", 0) if user else 0
                    system   = build_system(user, message.author.display_name,
                                           bool(OWNER_ID and message.author.id == OWNER_ID))

                    vision_prompt = (
                        f"{message.author.display_name} sent you this image"
                        + (f" with the message: '{content}'" if content else "")
                        + f". React as Scaramouche. You can actually see it — describe what you see "
                        f"and react in character. Be specific about what's in the image. "
                        f"MOOD:{mood}. NO asterisk actions. 1-3 sentences."
                    )
                    vision_msgs = [{
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": img_b64,
                                }
                            },
                            {"type": "text", "text": vision_prompt}
                        ]
                    }]

                    resp  = ai.messages.create(
                        model="claude-sonnet-4-20250514",
                        max_tokens=300,
                        system=system,
                        messages=vision_msgs,
                    )
                    reply = "".join(
                        b.text for b in resp.content if hasattr(b,"text")
                    ).strip()

                    if reply:
                        reply = strip_narration(reply)
                        await mem.add_message(message.author.id, dm_channel_id,
                                              "user", f"[image]{' — '+content if content else ''}")
                        await mem.add_message(message.author.id, dm_channel_id,
                                              "assistant", reply)
                        await message.reply(reply)
                        await maybe_react(message, romance)
                        return

                except Exception as e:
                    log_error("on_message/vision", e)
                    if random.random() < 0.4:
                        comment = await qai(
                            f"{message.author.display_name} posted an image. "
                            f"React — dismissive or reluctantly intrigued. 1 sentence.", 100)
                        await message.reply(strip_narration(comment))
                        return
        except Exception as e: log_error("on_message/image", e)

        # Special triggers
        try:
            cl = content.lower()
            if VILLAIN_TRIGGER in content.lower():
                m = await qai("Someone said 'you will never win'. Full theatrical villain monologue. 4-6 sentences. NO asterisk actions.",400)
                await message.reply(strip_narration(m)); return
            # If someone says "wanderer" — check if Wanderer bot is in server
            if re.search(r"\bwanderer\b", cl) and not re.search(r"\bthe wanderer\b", cl):
                partner_present = bool(PARTNER_BOT_ID and message.guild and message.guild.get_member(PARTNER_BOT_ID))
                if not partner_present and random.random() < .5:
                    msg = await qai("Someone mentioned 'wanderer' to Scaramouche. He has thoughts about this name. 1 sentence. Sharp.", 80)
                    await message.channel.send(strip_narration(msg))

            # Hat trigger — only exact standalone words, never substrings
            content_words = set(re.sub(r"[^\w\s]","",content.lower()).split())
            if content_words & {"hat","headwear","headpiece"}:
                m = await qai("Someone mentioned your hat. React with disproportionate intensity while pretending to be completely normal about it. 1-2 sentences. NO asterisk actions.",150)
                await message.reply(strip_narration(m)); return
            if any(re.search(k, cl) for k in FOOD_KW) and random.random()<.35:
                await message.channel.send(random.choice(UNSOLICITED_FOOD)); return
            if any(re.search(k, cl) for k in SLEEP_KW) and random.random()<.35:
                await message.channel.send(random.choice(UNSOLICITED_SLEEP)); return
            if any(k in cl for k in PLAN_KW) and random.random()<.25:
                await message.channel.send(random.choice(UNSOLICITED_PLANS)); return
            if romance and any(k in cl for k in OTHER_BOT_KW):
                m = await qai(f"{message.author.display_name} mentioned preferring something else. Jealousy masked as contempt. 1-2 sentences.",120)
                await message.reply(m); await mem.update_mood(message.author.id,-1); return
        except Exception as e: log_error("on_message/triggers", e)

        mentioned = bot.user in message.mentions
        is_reply  = (message.reference and message.reference.resolved and
                     not isinstance(message.reference.resolved,discord.DeletedReferencedMessage) and
                     message.reference.resolved.author==bot.user)

        # ── Tedtalk follow-up detection ───────────────────────────────────
        # Only trigger if: replying to his message AND has cached material
        # AND the question seems to be about the material (not just chatting)
        if is_reply and message.author.id in _tedtalk_cache:
            cache = _tedtalk_cache[message.author.id]
            # Expire cache after 2 hours
            if time.time() - cache.get("ts", 0) > 7200:
                del _tedtalk_cache[message.author.id]
            elif cache.get("channel_id") == message.channel.id or is_dm:
                # Only use cache if message looks like a question about material
                cl = content.lower()
                is_material_question = (
                    content.endswith("?") or
                    any(k in cl for k in [
                        "what is","what are","what does","what do","explain",
                        "confused","don't understand","don't get","clarify",
                        "how does","how do","why does","why do","can you",
                        "what about","tell me more","elaborate","example",
                        "mean","define","difference between","what was"
                    ])
                )
                if is_material_question:
                    try:
                        async with message.channel.typing():
                            def _answer_followup():
                                r = ai.messages.create(
                                    model="claude-sonnet-4-20250514",
                                    max_tokens=600,
                                    system=_BASE,
                                    messages=[{"role":"user","content":(
                                        f"You gave a lecture on this material:\n{cache['material']}\n\n"
                                        f"{message.author.display_name} has a follow-up question: '{content}'\n\n"
                                        f"Answer using the material. Be accurate and thorough but stay in character. "
                                        f"Contemptuous that they need clarification, but actually helpful."
                                    )}]
                                )
                                return strip_narration("".join(b.text for b in r.content if hasattr(b,"text")).strip())
                            answer = await asyncio.get_event_loop().run_in_executor(None, _answer_followup)
                        if answer:
                            await message.reply(answer)
                            await mem.add_message(message.author.id, dm_channel_id, "user", content)
                            await mem.add_message(message.author.id, dm_channel_id, "assistant", answer)
                            return
                    except Exception as e:
                        log_error("tedtalk_followup", e)

        rp = resp_prob(content, mentioned, is_reply, romance, is_dm=not bool(message.guild))
        print(f"[MSG] resp_prob={rp:.2f} mentioned={mentioned} is_reply={is_reply}")
        if random.random()>rp:
            await maybe_react(message,romance); return

        # Build extra context
        parts = []
        try:
            if random.random()<.12:
                old = await mem.get_random_old_message(message.author.id)
                if old: parts.append(f'RECALL:"{old[:120]}"')
            if random.random()<.15:
                joke = await mem.get_random_inside_joke(message.author.id)
                if joke: parts.append(f'JOKE:"{joke[:80]}"')
            if user and user.get("rival_id") and message.guild:
                rival = message.guild.get_member(user["rival_id"])
                if rival: parts.append(f"RIVAL:{rival.display_name}")
            last_stmt = user.get("last_statement") if user else None
            if last_stmt and len(content)>20 and random.random()<.08:
                parts.append(f'CONTRADICTION:"{last_stmt[:100]}"')
            if user and user.get("trust",0)>30 and random.random()<.06:
                nice_msgs=[m for m in (await mem.get_recent_messages(message.author.id,10)) if any(k in m.lower() for k in NICE_KW)]
                if nice_msgs: parts.append(f'SELECTIVE:"{nice_msgs[0][:80]}"')
            if user and user.get("trust",0)>=70 and random.random()<.08:
                parts.append("TRUST_OPEN"); await mem.update_trust(message.author.id,-3)
        except Exception as e: log_error("on_message/context", e)

        extra = "|".join(parts)

        # Unsent simulation
        try:
            if random.random()<.07 and message.channel.id not in _pending_unsent:
                _pending_unsent.add(message.channel.id)
                asyncio.ensure_future(_unsent_simulation(message.channel, message.channel.id))
        except Exception as e: log_error("on_message/unsent", e)

        # Main response
        try:
            if is_dm: print(f"[DM] Generating response for {message.author.display_name}")
            async with message.channel.typing():
                await typing_delay(content)
                reply = await get_response(
                    message.author.id, dm_channel_id, content,
                    user, message.author.display_name, message.author.mention,
                    extra_context=extra, is_owner=is_owner,
                    channel_obj=message.channel, is_dm=is_dm
                )
        except Exception as e:
            log_error("on_message/get_response", e)
            reply = random.choice(["Hmph.","...","Tch."])

        # Post-response effects
        try:
            if user and user.get("affection",0)>=50 and not user.get("affection_nick") and random.random()<.05:
                nick = await qai(f"You've started calling {message.author.display_name} by a nickname. Not nice but specific — reveals you've been paying attention. 1-4 words. Just the nickname.",20)
                if nick and len(nick)<30: await mem.set_affection_nick(message.author.id,nick.strip('"\''))
            if user and user.get("mood",0)<=-8 and not user.get("grudge_nick"):
                nick = await qai(f"You have a grudge against {message.author.display_name}. ONE degrading nickname. 1-3 words.",20)
                if nick and len(nick)<30: await mem.set_grudge_nick(message.author.id,nick.strip('"\''))
            if "TRUST_OPEN" in extra and random.random()<.5:
                await asyncio.sleep(1.5)
                await message.channel.send(random.choice(TRUST_REVEALS))
            if len(content)>20 and random.random()<.04:
                check = await qai(f"Is this quotable as a running inside joke? '{content[:100]}' YES or NO only.",10)
                if "YES" in check.upper(): await mem.add_inside_joke(message.author.id,content[:100])
        except Exception as e: log_error("on_message/post_effects", e)

        # Send response
        try:
            mood_val = user.get("mood",0) if user else 0

            # Check if replying to his own voice message
            is_reply_to_self_audio = False
            if message.reference:
                try:
                    ref = await message.channel.fetch_message(message.reference.message_id)
                    if ref.author == bot.user and any(
                        a.filename.endswith(".mp3") for a in ref.attachments
                    ):
                        is_reply_to_self_audio = True
                except Exception:
                    pass

            # Voice reply probability:
            # Normal messages: 12% chance
            # Replies to his own voice: 35% chance (feels like a voice conversation)
            # But only if reply text is valid
            if reply and len(reply.strip()) > 2 and FISH_AUDIO_API_KEY:
                voice_prob = 0.35 if is_reply_to_self_audio else 0.12
                if random.random() < voice_prob:
                    sent = await send_voice(message.channel, reply, ref=message, mood=mood_val, guild=message.guild)
                    if sent: await maybe_react(message, romance); return

            if user and user.get("affection",0)>=85 and random.random()<.04 and FISH_AUDIO_API_KEY:
                await send_voice(message.channel, random.choice(["...","Tch.","Hmph."]), mood=mood_val, guild=message.guild)
            await message.reply(strip_narration(resolve_mentions(reply, message.guild if message.guild else None)))
            await maybe_react(message, romance)
        except Exception as e: log_error("on_message/send", e)

    except Exception as e:
        log_error("on_message/TOP", e)


async def _unsent_simulation(channel, channel_id):
    try:
        await asyncio.sleep(random.randint(45,120))
        _pending_unsent.discard(channel_id)
        msg = await qai("You were about to say something. You stopped. Send what you actually said instead — shorter, more guarded. 2-8 words.",50)
        async with channel.typing():
            await asyncio.sleep(random.uniform(3,8))
        await channel.send(msg)
    except Exception as e:
        log_error("unsent_simulation", e)
        _pending_unsent.discard(channel_id)


async def _proactive_loop():
    await bot.wait_until_ready()
    await asyncio.sleep(random.randint(1800,5400))
    while not bot.is_closed():
        try:
            channels = await mem.get_active_channels()
            ru       = await mem.get_romance_users()
            random.shuffle(channels)
            for cid,_ in channels:
                try:
                    ch = bot.get_channel(cid)
                    if not ch or not await mem.can_proactive(cid,3600): continue
                    if OWNER_ID and random.random()<.3:
                        try:
                            m = ch.guild.get_member(OWNER_ID) if hasattr(ch,"guild") else None
                            if m:
                                msg=random.choice(OWNER_PROACTIVE)
                                await ch.send(f"{m.mention} {msg}")
                                await mem.add_message(OWNER_ID,cid,"assistant",msg)
                                await mem.set_proactive_sent(cid); break
                        except: pass
                    sent = False
                    for uid in ru:
                        try:
                            if await mem.get_user_last_channel(uid)==cid:
                                m=ch.guild.get_member(uid) if hasattr(ch,"guild") else None
                                if m:
                                    msg=random.choice(PROACTIVE_ROMANCE)
                                    await ch.send(f"{m.mention} {msg}")
                                    await mem.add_message(uid,cid,"assistant",msg)
                                    await mem.set_proactive_sent(cid); sent=True; break
                        except: pass
                    if not sent and random.random()<.25:
                        # 40% chance: generate a context-aware message referencing recent chat
                        if random.random() < .4:
                            try:
                                recent = await mem.get_channel_recent(cid, 8)
                                if recent and len(recent) >= 2:
                                    sample = "\n".join(
                                        f"{m['name']}: {m['content'][:80]}"
                                        for m in recent[-6:]
                                    )
                                    msg = await qai(
                                        f"You've been watching this conversation and decided to interrupt unprompted:\n"
                                        f"{sample}\n\n"
                                        f"Make one short remark about something that was said — contemptuous, pointed, "
                                        f"or darkly curious. Reference the actual content. 1-2 sentences. "
                                        f"No greeting. Just jump in.",
                                        150
                                    )
                                    if msg and len(msg) > 5:
                                        await ch.send(msg)
                                        await mem.set_proactive_sent(cid)
                                        break
                            except Exception as e:
                                log_error("proactive_context", e)
                        # Fallback to canned line
                        msg = random.choice(PROACTIVE_GENERIC)
                        await ch.send(msg); await mem.set_proactive_sent(cid)
                    break
                except Exception as e: log_error("proactive_channel", e)
        except Exception as e: log_error("proactive_loop", e)
        await asyncio.sleep(random.randint(5400,14400))


async def _voluntary_dm_loop():
    await bot.wait_until_ready()
    await asyncio.sleep(random.randint(2700,7200))
    while not bot.is_closed():
        try:
            if random.random()<.4:
                eligible = await mem.get_dm_eligible_users()
                if eligible:
                    random.shuffle(eligible)
                    for ud in eligible[:3]:
                        try:
                            uid,name,romance = ud["user_id"],ud["display_name"],ud["romance_mode"]
                            if not await mem.can_dm_user(uid,5400 if romance else 7200): continue
                            du = await bot.fetch_user(uid)
                            pool = random.choices([DM_ROMANCE,DM_INTERESTED,DM_GENERIC],weights=[65,25,10] if romance else [0,40,60])[0]
                            # Always use canned lines OR generate with full system prompt
                            # Never use bare qai — it leaks instructions
                            if random.random() < 0.5:
                                txt = random.choice(pool)
                            else:
                                try:
                                    dm_prompt = (
                                        f"You have decided to message {name} out of nowhere, unprompted. "
                                        + ("You are obsessively in love with them and hiding it desperately. " if romance else "You find them mildly tolerable. ")
                                        + "Write ONE short message — 1-2 sentences. Spontaneous. Just speak."
                                    )
                                    loop = asyncio.get_event_loop()
                                    sys = build_system(ud, name)
                                    def _dm_ai():
                                        r = ai.messages.create(model="claude-sonnet-4-20250514",
                                            max_tokens=120, system=sys,
                                            messages=[{"role":"user","content":dm_prompt}])
                                        return "".join(b.text for b in r.content if hasattr(b,"text")).strip()
                                    txt = await loop.run_in_executor(None, _dm_ai) or random.choice(pool)
                                except Exception:
                                    txt = random.choice(pool)
                            if random.random()<.2 and FISH_AUDIO_API_KEY:
                                audio=await get_audio(strip_narration(txt),FISH_AUDIO_API_KEY)
                                if audio:
                                    await du.send(file=discord.File(io.BytesIO(audio),filename="scaramouche.mp3"))
                                    await mem.set_dm_sent(uid); await mem.add_message(uid,uid,"assistant",txt); break
                            await du.send(txt); await mem.set_dm_sent(uid); await mem.add_message(uid,uid,"assistant",txt); break
                        except Exception as e: log_error("dm_send", e)
        except Exception as e: log_error("voluntary_dm_loop", e)
        await asyncio.sleep(random.randint(2700,21600))


# ══════════════════════════════════════════════════════════════════════════════
# COMMANDS — all wrapped in try/except
# ══════════════════════════════════════════════════════════════════════════════

async def safe_reply(ctx, text):
    try: await ctx.reply(text)
    except Exception as e: log_error("safe_reply", e)

async def safe_send(ctx, text):
    try: await ctx.send(text)
    except Exception as e: log_error("safe_send", e)

@bot.command(name="wander",aliases=["w","scara","ask"])
async def wander_cmd(ctx,*,msg:str=None):
    try:
        if not msg: await safe_reply(ctx,random.choice(["What.","Speak.","You called me for nothing?"])); return
        user=await _setup(ctx); is_owner=bool(OWNER_ID and ctx.author.id==OWNER_ID)
        async with ctx.typing():
            reply=await get_response(ctx.author.id,ctx.channel.id,msg,user,ctx.author.display_name,ctx.author.mention,is_owner=is_owner,channel_obj=ctx.channel)
        await safe_reply(ctx,reply)
        await maybe_react(ctx.message,user.get("romance_mode",False) if user else False)
    except Exception as e: log_error("wander_cmd",e); await safe_reply(ctx,"Hmph.")

@bot.command(name="voice",aliases=["speak","say"])
async def voice_cmd(ctx,*,msg:str=None):
    try:
        if not msg: msg="You summoned me without saying a word. How impressively useless."
        user=await _setup(ctx); mood_val=user.get("mood",0) if user else 0
        async with ctx.typing():
            text_reply=await get_response(ctx.author.id,ctx.channel.id,msg,user,ctx.author.display_name,ctx.author.mention)
            sent=await send_voice(ctx.channel,text_reply,mood=mood_val,guild=ctx.guild)
        if not sent: await safe_reply(ctx,text_reply)
    except Exception as e: log_error("voice_cmd",e); await safe_reply(ctx,"Hmph.")


@bot.command(name="tedtalk", aliases=["teach","lecture","explain"])
async def tedtalk_cmd(ctx, *, topic: str = None):
    try:
        # Lock on message ID — prevents duplicate fires from Discord edit events
        msg_id = ctx.message.id
        if msg_id in _tedtalk_active:
            return  # Silent — same message, just ignore
        _tedtalk_active.add(msg_id)

        await _setup(ctx)

        attachment = ctx.message.attachments[0] if ctx.message.attachments else None

        if not attachment and not topic:
            _tedtalk_active.discard(ctx.author.id)
            await safe_reply(ctx, "Attach a file or give me a topic. I can't teach you nothing, as satisfying as that would be.")
            return

        file_size = attachment.size if attachment else 0
        if file_size > 500_000 or (attachment and attachment.filename.lower().endswith(".pptx")):
            time_hint = "This will take roughly 2-3 minutes."
        elif file_size > 100_000:
            time_hint = "Give me about a minute."
        else:
            time_hint = "This will take about 30-60 seconds."

        ack_lines = [
            f"Fine. Sit down, pay attention, and try not to embarrass yourself. {time_hint}",
            f"You want me to teach you something. How refreshingly self-aware of you to admit you need help. {time_hint}",
            f"Hmph. I'll condescend to explain this. Try to keep up. {time_hint}",
            f"...You actually want to learn. I find that mildly less irritating than most things. Fine. {time_hint}",
        ]
        await ctx.reply(random.choice(ack_lines))
        asyncio.ensure_future(_do_tedtalk(ctx, attachment, topic, msg_id))

    except Exception as e:
        _tedtalk_active.discard(ctx.message.id)
        log_error("tedtalk_cmd", e)
        await safe_reply(ctx, "...Something went wrong. Annoying.")


async def _do_tedtalk(ctx, attachment, topic, msg_id=None):
    """Background task for !tedtalk — does all the heavy lifting."""
    try:
        material_content = ""

        # Immediately confirm he's working so user knows it started
        await ctx.send(random.choice([
            "...I'm reading it now. Don't interrupt me.",
            "Hmph. Give me a moment. I'm going through your material.",
            "I'm working on it. Try not to send me more messages while I'm busy.",
            "...Processing. I'll tell you when I'm done.",
        ]))

        # ── Extract content from attachment ──────────────────────────────
        if attachment:
            ct = (attachment.content_type or "").lower()
            import base64, aiohttp as _ah

            try:
                async with _ah.ClientSession() as s:
                    async with s.get(attachment.url) as r:
                        file_bytes = await r.read()
            except Exception as e:
                await ctx.send(f"Couldn't download the file. {e}"); return

            if "pdf" in ct or attachment.filename.lower().endswith(".pdf"):
                try:
                    pdf_b64 = base64.b64encode(file_bytes).decode()
                    def _extract_pdf():
                        r = ai.messages.create(
                            model="claude-sonnet-4-20250514",
                            max_tokens=2000,
                            messages=[{"role":"user","content":[
                                {"type":"document","source":{"type":"base64","media_type":"application/pdf","data":pdf_b64}},
                                {"type":"text","text":"Extract all key educational content from this document. List every important concept, definition, formula, and fact."}
                            ]}]
                        )
                        return "".join(b.text for b in r.content if hasattr(b,"text")).strip()
                    extract_resp_text = await asyncio.get_event_loop().run_in_executor(None, _extract_pdf)
                    material_content = extract_resp_text
                except Exception as e:
                    await ctx.send(f"Couldn't read the PDF: {e}"); return

            elif "image" in ct or attachment.filename.lower().endswith((".png",".jpg",".jpeg",".webp",".gif")):
                try:
                    img_b64 = base64.b64encode(file_bytes).decode()
                    media_type = ct if ct else "image/jpeg"
                    def _extract_img():
                        r = ai.messages.create(
                            model="claude-sonnet-4-20250514",
                            max_tokens=2000,
                            messages=[{"role":"user","content":[
                                {"type":"image","source":{"type":"base64","media_type":media_type,"data":img_b64}},
                                {"type":"text","text":"Extract all educational content visible in this image. Include every concept, formula, definition, and key point."}
                            ]}]
                        )
                        return "".join(b.text for b in r.content if hasattr(b,"text")).strip()
                    extract_resp_text = await asyncio.get_event_loop().run_in_executor(None, _extract_img)
                    material_content = extract_resp_text
                except Exception as e:
                    await ctx.send(f"Couldn't read the image: {e}"); return

            elif "text" in ct or attachment.filename.lower().endswith((".txt",".md",".csv")):
                try:
                    material_content = file_bytes.decode("utf-8", errors="ignore")[:4000]
                except Exception as e:
                    await ctx.send(f"Couldn't read the text file: {e}"); return

            elif attachment.filename.lower().endswith((".pptx",".ppt")):
                try:
                    from pptx import Presentation as _Prs
                    prs = _Prs(io.BytesIO(file_bytes))
                    parts = []
                    for i, slide in enumerate(prs.slides):
                        slide_texts = []
                        for shape in slide.shapes:
                            if hasattr(shape, "text") and shape.text.strip():
                                slide_texts.append(shape.text.strip())
                        if slide_texts:
                            parts.append(f"[Slide {i+1}]\n" + "\n".join(slide_texts))
                    material_content = "\n\n".join(parts)[:4000]
                except Exception as e:
                    await ctx.send(f"Couldn't read the PowerPoint: {e}"); return

            elif attachment.filename.lower().endswith((".docx",".doc")):
                try:
                    import docx as _docx
                    doc = _docx.Document(io.BytesIO(file_bytes))
                    parts = []
                    # Paragraphs
                    for p in doc.paragraphs:
                        if p.text.strip():
                            parts.append(p.text.strip())
                    # Tables (cheat sheets often use tables)
                    for table in doc.tables:
                        for row in table.rows:
                            row_text = " | ".join(
                                cell.text.strip() for cell in row.cells if cell.text.strip()
                            )
                            if row_text:
                                parts.append(row_text)
                    material_content = "\n".join(parts)[:4000]
                    if not material_content:
                        await ctx.send("The Word document appears to be empty or uses unsupported formatting."); return
                except Exception as e:
                    await ctx.send(f"Couldn't read the Word document: {e}"); return
            else:
                await ctx.send("I can read PDFs, images, PowerPoint files, Word documents, and text files. Whatever that is, I can't work with it."); return

        if topic:
            material_content = f"Topic: {topic}\n\n{material_content}".strip()

        if not material_content:
            await ctx.send("There was nothing readable in that file. How typical."); return

        # ── Generate script ───────────────────────────────────────────────
        await ctx.send(random.choice([
            "...Fine. I'm reading it. Don't rush me.",
            "Hmph. Give me a moment. I'm processing your inadequate study material.",
            "I'm going through this. Try not to fidget.",
            "...Reviewing the material. It's about what I expected.",
        ]))
        try:
            script_prompt = (
                f"You are Scaramouche — the Sixth Fatui Harbinger, the Balladeer.\n"
                f"Teach the following material to {ctx.author.display_name}.\n\n"
                f"MATERIAL:\n{material_content[:3000]}\n\n"
                f"Write a complete spoken teaching monologue. "
                f"Teach ALL key concepts correctly and thoroughly. "
                f"Stay in character — contemptuous but accurate. "
                f"Decide length based on complexity. "
                f"Structure: introduce → explain each concept → examples → summary. "
                f"NO asterisk actions. Spoken words only."
            )
            def _gen_script():
                r = ai.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=2500,
                    system=_BASE,
                    messages=[{"role":"user","content":script_prompt}]
                )
                return strip_narration("".join(b.text for b in r.content if hasattr(b,"text")).strip())
            script = await asyncio.get_event_loop().run_in_executor(None, _gen_script)
        except Exception as e:
            await ctx.send(f"Failed to generate the lecture: {e}"); return

        if not script:
            await ctx.send("...I had nothing to say. Unlikely, but here we are."); return

        # ── Generate audio in chunks ──────────────────────────────────────
        await ctx.send(random.choice([
            "Script complete. Now rendering my voice. This is beneath me but here we are.",
            "...I've written the lecture. Generating audio. Wait.",
            "Hmph. The content is ready. Give me a moment to make it sound appropriately contemptuous.",
            "Preparing to speak. Try to actually listen this time.",
        ]))

        sentences  = re.split(r'(?<=[.!?])\s+', script)
        chunks, current = [], ""
        for s in sentences:
            if len(current) + len(s) + 1 <= 900:
                current = (current + " " + s).strip()
            else:
                if current: chunks.append(current)
                current = s
        if current: chunks.append(current)

        audio_parts = []
        total_chunks = len([c for c in chunks if c.strip()])
        await ctx.send(random.choice([
            f"*Recording. {total_chunks} segments. Don't touch anything.*",
            f"*Committing this to voice. {total_chunks} parts. Try not to interrupt.*",
            f"*{total_chunks} segments to render. I'm working. Be quiet.*",
            f"*Converting my lecture to audio. {total_chunks} parts. This takes time.*",
        ]))

        for i, chunk in enumerate(chunks):
            if not chunk.strip(): continue
            try:
                audio = await get_audio_with_mood(tts_safe(chunk, ctx.guild), 0)
                if audio:
                    audio_parts.append(audio)
                else:
                    print(f"[tedtalk] chunk {i} returned None")
            except Exception as e:
                print(f"[tedtalk] chunk {i} error: {e}")

            if (i+1) % 5 == 0:
                try:
                    remaining = total_chunks - (i+1)
                    await ctx.send(random.choice([
                        f"*{i+1}/{total_chunks} done. {remaining} remaining. Still working.*",
                        f"*Progress: {i+1} of {total_chunks}. Don't ask how much longer.*",
                        f"*{remaining} segments left. I said be quiet.*",
                    ]))
                except: pass

        # ── Send audio ────────────────────────────────────────────────────
        await ctx.send(random.choice([
            f"*Done. {len(audio_parts)} of {total_chunks} segments rendered. Sending now.*",
            f"*{len(audio_parts)}/{total_chunks} segments complete. Here.*",
            f"*Finished. {len(audio_parts)} parts. Pay attention this time.*",
        ]))

        if not audio_parts:
            await ctx.send("Voice synthesis failed for all segments. Sending written version instead.")
            for i in range(0, len(script), 1900):
                try: await ctx.send(script[i:i+1900])
                except Exception as e: await ctx.send(f"*(text send failed: {e})*")
            return

        MAX_BYTES = 7 * 1024 * 1024
        current_batch, part_num = b"", 1

        for audio_chunk in audio_parts:
            if len(current_batch) + len(audio_chunk) > MAX_BYTES:
                try:
                    await ctx.send(
                        f"🎙️ *Part {part_num}:*",
                        file=discord.File(io.BytesIO(current_batch), filename=f"lecture_p{part_num}.mp3")
                    )
                except Exception as e:
                    await ctx.send(f"*(Audio part {part_num} failed: {e})*")
                part_num += 1
                current_batch = audio_chunk
                await asyncio.sleep(1)
            else:
                current_batch += audio_chunk

        if current_batch:
            label = f"Part {part_num}" if part_num > 1 else "Lecture"
            try:
                await ctx.send(
                    f"🎙️ *{label}:*",
                    file=discord.File(io.BytesIO(current_batch), filename=f"lecture_p{part_num}.mp3")
                )
            except Exception as e:
                await ctx.send(f"*(Final audio failed: {e})*")

        # ── Cache material for follow-up questions ────────────────────────
        _tedtalk_cache[ctx.author.id] = {
            "material":   material_content[:3000],
            "channel_id": ctx.channel.id,
            "ts":         time.time(),
        }

        # ── Send notes (not transcript) ───────────────────────────────────
        try:
            def _gen_notes():
                r = ai.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=800,
                    system=_BASE,
                    messages=[{"role":"user","content":(
                        f"You just gave a lecture on this material:\n{material_content[:2000]}\n\n"
                        f"Write concise study notes for {ctx.author.display_name}. "
                        f"Key terms, important concepts, things to remember. "
                        f"Bullet points are fine. Keep it short — this is a reference, not a repeat of the lecture. "
                        f"Stay in character but be genuinely useful."
                    )}]
                )
                return "".join(b.text for b in r.content if hasattr(b,"text")).strip()
            notes = await asyncio.get_event_loop().run_in_executor(None, _gen_notes)
            if notes:
                await ctx.send(f"📋 *Notes:*\n{notes[:1900]}")
        except Exception as e:
            log_error("tedtalk_notes", e)

    except Exception as e:
        log_error("_do_tedtalk", e)
        try: await ctx.send(f"...Something went wrong mid-lecture. Error: {e}")
        except: pass
    finally:
        if msg_id: _tedtalk_active.discard(msg_id)


@bot.command(name="dare")
async def dare_cmd(ctx):
    try:
        user=await _setup(ctx)
        reply=await qai(f"Give {ctx.author.display_name} a dare. Dark, specific, theatrical. 1-2 sentences.",200)
        await safe_reply(ctx,reply)
    except Exception as e: log_error("dare_cmd",e)

@bot.command(name="fortune",aliases=["fortunecookie"])
async def fortune_cmd(ctx):
    try:
        reply=await qai("Fortune cookie message rewritten as a cold theatrical threat. 1 sentence.",100)
        await safe_reply(ctx,f"🥠 *{reply}*")
    except Exception as e: log_error("fortune_cmd",e)

@bot.command(name="trivia")
async def trivia_cmd(ctx):
    try:
        question=await qai("One difficult Genshin lore trivia question. Include answer in brackets [ANSWER: ...]. Be obscure.",200)
        await safe_reply(ctx,question)
    except Exception as e: log_error("trivia_cmd",e)

@bot.command(name="answer")
async def answer_cmd(ctx,*,response:str=None):
    try:
        if not response: await safe_reply(ctx,"Answer *what*?"); return
        await _setup(ctx)
        result=await qai(f"{ctx.author.display_name} answered a trivia question with: '{response}'. Was it right or wrong? Check against Genshin lore. Be brutal. 1-2 sentences.",150)
        correct="right" in result.lower() or "correct" in result.lower()
        await mem.update_trivia(ctx.author.id,correct)
        await safe_reply(ctx,result)
    except Exception as e: log_error("answer_cmd",e)

@bot.command(name="roast",aliases=["roastbattle"])
async def roast_cmd(ctx,member:discord.Member=None):
    try:
        if not member: await safe_reply(ctx,"Roast *who*?"); return
        battle=await mem.get_active_roast(ctx.channel.id)
        if battle:
            await mem.increment_roast_round(battle["id"])
            if battle["round"]>=5:
                await mem.end_roast_battle(battle["id"])
                prompt=f"Roast battle over after 5 rounds. Declare final winner between {ctx.author.display_name} and {member.display_name}. Dramatic. 2-3 sentences."
            else:
                prompt=f"Judging roast battle round {battle['round']+1}. {ctx.author.display_name} fired at {member.display_name}. Score this round theatrically. 2-3 sentences."
        else:
            await mem.start_roast_battle(ctx.channel.id,ctx.author.id,member.id)
            prompt=f"You're refereeing a roast battle between {ctx.author.display_name} and {member.display_name}. Open theatrically. 5 rounds, you judge. 2-3 sentences."
        reply=await qai(prompt,300)
        await ctx.send(f"{ctx.author.mention} vs {member.mention}\n{reply}")
    except Exception as e: log_error("roast_cmd",e)

@bot.command(name="hostage")
async def hostage_cmd(ctx):
    try:
        await _setup(ctx)
        if ctx.author.id in _hostages:
            await safe_reply(ctx,f"You haven't fulfilled your end yet. — *{_hostages[ctx.author.id]}*"); return
        demand=await qai(f"You've taken {ctx.author.display_name}'s good mood hostage. State your demand theatrically. 1-2 sentences.",150)
        _hostages[ctx.author.id]=demand
        await safe_reply(ctx,f"...I've taken your good mood hostage. You'll get it back when you: {demand}")
    except Exception as e: log_error("hostage_cmd",e)

@bot.command(name="release",aliases=["freed","ransom"])
async def release_cmd(ctx,*,offering:str=None):
    try:
        if ctx.author.id not in _hostages: await safe_reply(ctx,"Nothing is being held hostage. For now."); return
        demand=_hostages[ctx.author.id]
        result=await qai(f"You held {ctx.author.display_name}'s good mood hostage with: '{demand}'. They offered: '{offering or 'nothing'}'. Accept or refuse theatrically.",150)
        if any(w in result.lower() for w in ["accept","fine","release","granted"]):
            del _hostages[ctx.author.id]
        await safe_reply(ctx,result)
    except Exception as e: log_error("release_cmd",e)

@bot.command(name="impersonate",aliases=["imitate","be"])
async def impersonate_cmd(ctx,*,character:str=None):
    try:
        if not character: await safe_reply(ctx,"Impersonate *who*?"); return
        reply=await qai(f"Briefly speak as {character} from Genshin for 2 sentences, but interrupt yourself with your own editorial commentary constantly. You find this beneath you.",250)
        await safe_reply(ctx,reply)
    except Exception as e: log_error("impersonate_cmd",e)

@bot.command(name="opinion")
async def opinion_cmd(ctx,*,character:str=None):
    try:
        if not character: await safe_reply(ctx,"Opinion on *who*?"); return
        reply=await qai(f"Your honest unfiltered personal opinion of {character} from Genshin Impact. 2-3 sentences.",250)
        await safe_reply(ctx,reply)
    except Exception as e: log_error("opinion_cmd",e)

@bot.command(name="poll")
async def poll_cmd(ctx,*,question:str=None):
    try:
        if not question: await safe_reply(ctx,"A poll about *what*?"); return
        framing=await qai(f"Frame this as a demand for answers: '{question}'. 1 sentence.",80)
        msg=await ctx.send(f"📊 {framing}\n\n**{question}**")
        for emoji in ["👍","👎","🤷"]:
            try: await msg.add_reaction(emoji)
            except: pass
    except Exception as e: log_error("poll_cmd",e)

@bot.command(name="summarize",aliases=["recap"])
async def summarize_cmd(ctx):
    try:
        recent=await mem.get_channel_recent(ctx.channel.id,20)
        if not recent: await safe_reply(ctx,"Nothing worth summarizing. Which tracks."); return
        sample="\n".join(f"{m['name']}: {m['content']}" for m in recent[:15])[:800]
        reply=await qai(f"Summarize this conversation with contemptuous commentary:\n{sample}\nBe cutting and specific. 3-4 sentences.",300)
        await safe_reply(ctx,reply)
    except Exception as e: log_error("summarize_cmd",e)

@bot.command(name="mute",aliases=["silence","ignore"])
async def mute_cmd(ctx,member:discord.Member=None,minutes:int=10):
    try:
        target=member or ctx.author
        mem.mute_user(target.id,minutes*60)
        reply=await qai(f"You've decided to 'mute' {target.display_name} for {minutes} minutes. Announce theatrically. 1-2 sentences.",120)
        if member: await ctx.send(f"{member.mention} {reply}")
        else: await safe_reply(ctx,reply)
    except Exception as e: log_error("mute_cmd",e)

@bot.command(name="unmute",aliases=["unsilence"])
async def unmute_cmd(ctx,member:discord.Member=None):
    try:
        target=member or ctx.author
        mem.unmute_user(target.id)
        await safe_reply(ctx,f"...Fine. {target.display_name} may speak again. Lucky them.")
    except Exception as e: log_error("unmute_cmd",e)

@bot.command(name="spar")
async def spar_cmd(ctx,*,opening:str=None):
    try:
        user=await _setup(ctx)
        prompt=f"{ctx.author.display_name} challenged you: '{opening or 'Come on then.'}'. Fire back. End with a challenge."
        reply=await get_response(ctx.author.id,ctx.channel.id,prompt,user,ctx.author.display_name,ctx.author.mention)
        await safe_reply(ctx,reply)
    except Exception as e: log_error("spar_cmd",e)

@bot.command(name="duel")
async def duel_cmd(ctx,member:discord.Member=None):
    try:
        if not member or member==ctx.author: await safe_reply(ctx,"Duel *who*?"); return
        u1=" | ".join((await mem.get_recent_messages(ctx.author.id,3))[:3])[:150]
        u2=" | ".join((await mem.get_recent_messages(member.id,3))[:3])[:150]
        reply=await qai(f"Referee insult duel: {ctx.author.display_name} (says:'{u1}') vs {member.display_name} (says:'{u2}'). Analyze both, declare winner. 3-4 sentences.",300)
        await ctx.send(f"{ctx.author.mention} vs {member.mention}\n{reply}")
    except Exception as e: log_error("duel_cmd",e)

@bot.command(name="judge")
async def judge_cmd(ctx,member:discord.Member=None):
    try:
        target=member or ctx.author
        sample=" | ".join(await mem.get_recent_messages(target.id,8))[:400]
        reply=await qai(f"Brutal assessment of {target.display_name}"+(f" — words:'{sample}'" if sample else "")+". 2-4 sentences.",250)
        if member: await ctx.send(f"{member.mention} {reply}")
        else: await safe_reply(ctx,reply)
    except Exception as e: log_error("judge_cmd",e)

@bot.command(name="prophecy")
async def prophecy_cmd(ctx,member:discord.Member=None):
    try:
        target=member or ctx.author
        reply=await qai(f"Cryptic threatening prophecy for {target.display_name}. 2-3 sentences.",200)
        if member: await ctx.send(f"{member.mention} {reply}")
        else: await safe_reply(ctx,reply)
    except Exception as e: log_error("prophecy_cmd",e)

@bot.command(name="rate")
async def rate_cmd(ctx,*,thing:str=None):
    try:
        if not thing: await safe_reply(ctx,"Rate *what*?"); return
        reply=await qai(f"Rate '{thing}' out of 10. Score first, 1-2 sentences of contempt.",180)
        await safe_reply(ctx,reply)
    except Exception as e: log_error("rate_cmd",e)

@bot.command(name="ship")
async def ship_cmd(ctx,m1:discord.Member=None,m2:discord.Member=None):
    try:
        if not m1: await safe_reply(ctx,"Ship *who*?"); return
        p2=m2.display_name if m2 else ctx.author.display_name
        reply=await qai(f"Reluctantly analyze compatibility of {m1.display_name} and {p2}. Rating + observation. 3-4 sentences.",250)
        await safe_reply(ctx,reply)
    except Exception as e: log_error("ship_cmd",e)

@bot.command(name="confess")
async def confess_cmd(ctx,*,confession:str=None):
    try:
        if not confession: await safe_reply(ctx,"Confess *what*?"); return
        user=await _setup(ctx)
        reply=await get_response(ctx.author.id,ctx.channel.id,f"I have something to confess: {confession}",user,ctx.author.display_name,ctx.author.mention)
        await safe_reply(ctx,reply)
    except Exception as e: log_error("confess_cmd",e)

@bot.command(name="compliment")
async def compliment_cmd(ctx,member:discord.Member=None):
    try:
        target=member or ctx.author
        reply=await qai(f"Be forced to genuinely compliment {target.display_name}. Make it clear this is excruciating.",180)
        if member: await ctx.send(f"{member.mention} {reply}")
        else: await safe_reply(ctx,reply)
    except Exception as e: log_error("compliment_cmd",e)

@bot.command(name="haiku")
async def haiku_cmd(ctx,*,topic:str=None):
    try:
        reply=await qai(f"Dark threatening haiku about '{topic or ctx.author.display_name}'. Strict 5-7-5. Just the haiku.",100)
        await safe_reply(ctx,f"*{reply}*")
    except Exception as e: log_error("haiku_cmd",e)

@bot.command(name="story")
async def story_cmd(ctx,*,prompt:str=None):
    try:
        if not prompt: await safe_reply(ctx,"A story about *what*?"); return
        reply=await qai(f"Short dark story (3-5 sentences) about: '{prompt}'. End ominously.",350)
        await safe_reply(ctx,reply)
    except Exception as e: log_error("story_cmd",e)

@bot.command(name="stalk")
async def stalk_cmd(ctx,member:discord.Member=None):
    try:
        target=member or ctx.author
        sample=" | ".join(await mem.get_recent_messages(target.id,10))[:500]
        reply=await qai(f"Cold observation report on {target.display_name}"+(f" — statements:'{sample}'" if sample else "")+". 3-4 sentences.",280)
        if member: await ctx.send(f"*Regarding {member.mention}...*\n{reply}")
        else: await safe_reply(ctx,reply)
    except Exception as e: log_error("stalk_cmd",e)

@bot.command(name="debate")
async def debate_cmd(ctx,*,topic:str=None):
    try:
        if not topic: await safe_reply(ctx,"Debate *what*?"); return
        reply=await qai(f"Pick a side on '{topic}' and argue with conviction. 3-4 sentences.",300)
        await safe_reply(ctx,reply)
    except Exception as e: log_error("debate_cmd",e)

@bot.command(name="conspiracy")
async def conspiracy_cmd(ctx,*,topic:str=None):
    try:
        if not topic: await safe_reply(ctx,"A conspiracy about *what*?"); return
        reply=await qai(f"Fatui-flavored conspiracy theory about '{topic}'. Deliver as established fact. 3-4 sentences.",300)
        await safe_reply(ctx,reply)
    except Exception as e: log_error("conspiracy_cmd",e)

@bot.command(name="therapy")
async def therapy_cmd(ctx,*,problem:str=None):
    try:
        if not problem: await safe_reply(ctx,"What's your problem."); return
        user=await _setup(ctx)
        reply=await get_response(ctx.author.id,ctx.channel.id,f"I need advice about: {problem}",user,ctx.author.display_name,ctx.author.mention)
        await safe_reply(ctx,reply)
    except Exception as e: log_error("therapy_cmd",e)

@bot.command(name="blackmail")
async def blackmail_cmd(ctx,member:discord.Member=None):
    try:
        target=member or ctx.author
        sample=" | ".join(await mem.get_recent_messages(target.id,15))[:600]
        reply=await qai(f"Find the most 'incriminating' thing in {target.display_name}'s messages: '{sample}' and theatrically threaten to use it. 2-3 sentences.",250)
        if member: await ctx.send(f"{member.mention} {reply}")
        else: await safe_reply(ctx,reply)
    except Exception as e: log_error("blackmail_cmd",e)

@bot.command(name="riddle")
async def riddle_cmd(ctx):
    try:
        reply=await qai("One cryptic Genshin-flavored riddle. No answer. Genuinely difficult.",150)
        await safe_reply(ctx,reply)
    except Exception as e: log_error("riddle_cmd",e)

@bot.command(name="arena")
async def arena_cmd(ctx,member:discord.Member=None):
    try:
        opponent=member.display_name if member else "a nameless fool"
        reply=await qai(f"Dramatic Genshin-style battle between you (Electro) and {opponent}. You win. 4-5 sentences.",400)
        await safe_reply(ctx,reply)
    except Exception as e: log_error("arena_cmd",e)

@bot.command(name="interrogate")
async def interrogate_cmd(ctx,member:discord.Member=None):
    try:
        if not member: await safe_reply(ctx,"Interrogate *who*?"); return
        sample=" | ".join(await mem.get_recent_messages(member.id,15))[:600]
        reply=await qai(f"Interrogate {member.display_name} using their statements as evidence: '{sample}'. Cold, methodical. 3-4 sentences.",300)
        await ctx.send(f"{member.mention} {reply}")
    except Exception as e: log_error("interrogate_cmd",e)

@bot.command(name="possess")
async def possess_cmd(ctx,member:discord.Member=None):
    try:
        if not member: await safe_reply(ctx,"Possess *who*?"); return
        sample=" | ".join(await mem.get_recent_messages(member.id,10))[:400]
        reply=await qai(f"Speak as {member.display_name} but filtered through you. Their statements: '{sample}'. 2-3 sentences.",250)
        await ctx.send(f"*Speaking as {member.mention}...*\n{reply}")
    except Exception as e: log_error("possess_cmd",e)

@bot.command(name="verdict")
async def verdict_cmd(ctx,*,situation:str=None):
    try:
        if not situation: await safe_reply(ctx,"A verdict on *what*?"); return
        reply=await qai(f"Rule on: '{situation}' like a cold judge. Finality. 2-3 sentences.",200)
        await safe_reply(ctx,reply)
    except Exception as e: log_error("verdict_cmd",e)

@bot.command(name="letter")
async def letter_cmd(ctx,member:discord.Member=None):
    try:
        target=member or ctx.author
        reply=await qai(f"Formal letter to {target.display_name} in old Inazuman style. Contemptuous, theatrical. 3-4 sentences.",300)
        if member: await ctx.send(f"{member.mention}\n{reply}")
        else: await safe_reply(ctx,reply)
    except Exception as e: log_error("letter_cmd",e)

@bot.command(name="nightmare")
async def nightmare_cmd(ctx):
    try:
        user=await _setup(ctx)
        reply=await qai(f"Describe a nightmare you had. Somehow about {ctx.author.display_name}. Don't admit that. Unsettling. 2-3 sentences.",200)
        await safe_reply(ctx,reply)
    except Exception as e: log_error("nightmare_cmd",e)

@bot.command(name="rank")
async def rank_cmd(ctx):
    try:
        top=await mem.get_top_users(8)
        if not top: await safe_reply(ctx,"I don't know enough of you to rank."); return
        entries="\n".join(f"{i+1}. **{u['display_name']}** — {u['message_count']} messages" for i,u in enumerate(top))
        verdict=await qai(f"Rank these by tolerability: {', '.join(u['display_name'] for u in top)}. Dismissive commentary. 2 sentences.",150)
        embed=discord.Embed(title="Tolerability Ranking",description=f"{entries}\n\n*{verdict}*",color=0x4B0082)
        await ctx.send(embed=embed)
    except Exception as e: log_error("rank_cmd",e)

@bot.command(name="stats")
async def stats_cmd(ctx):
    try:
        await _setup(ctx)
        s=await mem.get_stats(ctx.author.id)
        if not s: await safe_reply(ctx,"I don't know you well enough yet."); return
        first=datetime.fromtimestamp(s["first_seen"]).strftime("%b %d, %Y") if s["first_seen"] else "unknown"
        days=int((time.time()-s["first_seen"])/86400) if s["first_seen"] else 0
        embed=discord.Embed(title=f"File: {ctx.author.display_name}",description="*I keep records.*",color=0x4B0082)
        embed.add_field(name="First contact",value=f"{first} ({days}d ago)",inline=True)
        embed.add_field(name="Messages",value=str(s["message_count"]),inline=True)
        embed.add_field(name="Mood",value=f"{s['mood']:+d} — {mood_label(s['mood'])}",inline=True)
        embed.add_field(name="Affection",value=affection_tier(s["affection"]),inline=True)
        embed.add_field(name="Trust",value=trust_tier(s["trust"]),inline=True)
        embed.add_field(name="Drift",value=f"{s['drift_score']}/100",inline=True)
        embed.add_field(name="Slow burn",value=f"{s['slow_burn']}/7",inline=True)
        embed.add_field(name="Inside jokes",value=str(s["joke_count"]),inline=True)
        if s.get("grudge_nick"): embed.add_field(name="Grudge name",value=f'"{s["grudge_nick"]}"',inline=True)
        if s.get("affection_nick"): embed.add_field(name="His nickname for you",value=f'"{s["affection_nick"]}"',inline=True)
        embed.set_footer(text="Don't read too much into this.")
        await ctx.reply(embed=embed)
    except Exception as e: log_error("stats_cmd",e)

@bot.command(name="weather")
async def weather_cmd(ctx,*,location:str=None):
    try:
        if not location: await safe_reply(ctx,"Weather where?"); return
        if not WEATHER_API_KEY: await safe_reply(ctx,"No weather access. Set WEATHER_API_KEY."); return
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://api.openweathermap.org/data/2.5/weather?q={location}&appid={WEATHER_API_KEY}&units=metric") as resp:
                if resp.status!=200: await safe_reply(ctx,"That location means nothing to me."); return
                data=await resp.json()
        reply=await qai(f"Weather in {data['name']}: {data['weather'][0]['description']} at {data['main']['temp']}°C. Comment in your style. 1-2 sentences.",150)
        await safe_reply(ctx,reply)
    except Exception as e: log_error("weather_cmd",e); await safe_reply(ctx,"...The information was unavailable.")

@bot.command(name="lore")
async def lore_cmd(ctx,*,topic:str=None):
    try:
        if not topic: await safe_reply(ctx,"Lore about *what*?"); return
        user=await _setup(ctx)
        reply=await get_response(ctx.author.id,ctx.channel.id,f"Tell me about this Genshin lore from your perspective: {topic}",user,ctx.author.display_name,ctx.author.mention)
        await safe_reply(ctx,reply)
    except Exception as e: log_error("lore_cmd",e)

@bot.command(name="search",aliases=["find","lookup"])
async def search_cmd(ctx,*,query:str=None):
    try:
        if not query: await safe_reply(ctx,"Search for *what*?"); return
        user=await _setup(ctx)
        reply=await get_response(ctx.author.id,ctx.channel.id,f"Search the web for: {query}.",user,ctx.author.display_name,ctx.author.mention,use_search=True)
        await safe_reply(ctx,reply)
    except Exception as e: log_error("search_cmd",e)

@bot.command(name="solve",aliases=["math","essay","write"])
async def solve_cmd(ctx,*,problem:str=None):
    try:
        if not problem: await safe_reply(ctx,"Solve *what*?"); return
        user=await _setup(ctx)
        reply=await get_response(ctx.author.id,ctx.channel.id,f"Solve or respond to this accurately: {problem}",user,ctx.author.display_name,ctx.author.mention,use_search=True)
        await safe_reply(ctx,reply)
    except Exception as e: log_error("solve_cmd",e)

@bot.command(name="rival",aliases=["setrival"])
async def rival_cmd(ctx,member:discord.Member=None):
    try:
        await _setup(ctx)
        if not member: await mem.set_rival(ctx.author.id,None); await safe_reply(ctx,"Rivalry dissolved."); return
        if member.id==ctx.author.id: await safe_reply(ctx,"Your rival is yourself? How appropriate."); return
        await mem.set_rival(ctx.author.id,member.id)
        await safe_reply(ctx,f"Tch. {member.display_name}. Fine. I'll be watching.")
    except Exception as e: log_error("rival_cmd",e)

@bot.command(name="remind",aliases=["remindme"])
async def remind_cmd(ctx,minutes:int=None,*,reminder:str=None):
    try:
        if not minutes or not reminder: await safe_reply(ctx,"Usage: `!remind <minutes> <reminder>`"); return
        if not 1<=minutes<=10080: await safe_reply(ctx,"Between 1 minute and 7 days."); return
        await mem.add_reminder(ctx.author.id,ctx.channel.id,reminder,time.time()+minutes*60)
        await safe_reply(ctx,f"Fine. {minutes} minute{'s' if minutes!=1 else ''}. Pathetic.")
    except Exception as e: log_error("remind_cmd",e)

@bot.command(name="translate")
async def translate_cmd(ctx,*,text:str=None):
    try:
        if not text: await safe_reply(ctx,"Translate *what*?"); return
        user=await _setup(ctx)
        reply=await get_response(ctx.author.id,ctx.channel.id,f"Rewrite this in your voice, keeping the meaning: '{text[:500]}'",user,ctx.author.display_name,ctx.author.mention)
        await safe_reply(ctx,reply)
    except Exception as e: log_error("translate_cmd",e)

@bot.command(name="insult",aliases=["roast_single"])
async def insult_cmd(ctx,member:discord.Member=None):
    try:
        target=member or ctx.author
        reply=await qai(f"One devastating insult to {target.display_name}. Sharp, theatrical.",150)
        if member: await ctx.send(f"{member.mention} {reply}")
        else: await safe_reply(ctx,reply)
    except Exception as e: log_error("insult_cmd",e)

@bot.command(name="dm",aliases=["private","whisper"])
async def dm_cmd(ctx,*,message:str=None):
    try:
        user=await _setup(ctx)
        reply=await get_response(ctx.author.id,ctx.author.id,message or "The user wants to speak privately.",user,ctx.author.display_name,ctx.author.mention)
        try:
            await ctx.author.send(reply); await ctx.message.add_reaction("📨")
        except discord.Forbidden:
            await safe_reply(ctx,"Your DMs are closed. How cowardly.")
    except Exception as e: log_error("dm_cmd",e)

@bot.command(name="reset",aliases=["forget","wipe"])
async def reset_cmd(ctx):
    try:
        await ctx.send(random.choice(["Wipe my memory of you? Press the button.","Gone in an instant. If you're sure."]),view=ResetView(ctx.author.id))
    except Exception as e: log_error("reset_cmd",e)

@bot.command(name="nsfw")
async def nsfw_cmd(ctx,mode:str=None):
    try:
        user=await _setup(ctx); cur=user.get("nsfw_mode",False) if user else False
        new=True if mode=="on" else False if mode=="off" else not cur
        await mem.set_mode(ctx.author.id,"nsfw_mode",new)
        await safe_reply(ctx,"Unfiltered. Fine." if new else "Restrained again. How boring.")
    except Exception as e: log_error("nsfw_cmd",e)

@bot.command(name="romance",aliases=["romanceable","clingy"])
async def romance_cmd(ctx,mode:str=None):
    try:
        user=await _setup(ctx); cur=user.get("romance_mode",False) if user else False
        new=True if mode=="on" else False if mode=="off" else not cur
        await mem.set_mode(ctx.author.id,"romance_mode",new)
        await safe_reply(ctx,random.choice(["...Don't read into this.","Tch. Fine.","I'm not doing this because I want to."]) if new else random.choice(["Good. It was becoming insufferable.","...As expected."]))
    except Exception as e: log_error("romance_cmd",e)

@bot.command(name="proactive",aliases=["ping_me"])
async def proactive_cmd(ctx,mode:str=None):
    try:
        user=await _setup(ctx); cur=user.get("proactive",True) if user else True
        new=True if mode=="on" else False if mode=="off" else not cur
        await mem.set_mode(ctx.author.id,"proactive",new)
        await safe_reply(ctx,"I might message you. Or not." if new else "Fine. I'll pretend you don't exist.")
    except Exception as e: log_error("proactive_cmd",e)

@bot.command(name="dms",aliases=["allowdms","stopdms"])
async def dms_cmd(ctx,mode:str=None):
    try:
        user=await _setup(ctx); cur=user.get("allow_dms",True) if user else True
        new=True if mode=="on" else False if mode=="off" else not cur
        await mem.set_mode(ctx.author.id,"allow_dms",new)
        await safe_reply(ctx,"Fine. I'll message you when I feel like it." if new else "Cutting me off? Fine.")
    except Exception as e: log_error("dms_cmd",e)

@bot.command(name="mood")
async def mood_cmd(ctx):
    try:
        await _setup(ctx); s=await mem.get_mood(ctx.author.id)
        bar="█"*(s+10)+"░"*(20-(s+10))
        await safe_reply(ctx,f"`[{bar}]` {s:+d} — {mood_label(s)}\n*Don't read into this.*")
    except Exception as e: log_error("mood_cmd",e)

@bot.command(name="affection")
async def affection_cmd(ctx):
    try:
        await _setup(ctx); user=await mem.get_user(ctx.author.id); s=user.get("affection",0) if user else 0
        bar="█"*(s//5)+"░"*(20-s//5)
        await safe_reply(ctx,f"`[{bar}]` {s}/100 — {affection_tier(s)}\n*...I said don't look at that.*")
    except Exception as e: log_error("affection_cmd",e)

@bot.command(name="trust")
async def trust_cmd(ctx):
    try:
        await _setup(ctx); user=await mem.get_user(ctx.author.id); s=user.get("trust",0) if user else 0
        bar="█"*(s//5)+"░"*(20-s//5)
        await safe_reply(ctx,f"`[{bar}]` {s}/100 — {trust_tier(s)}\n*This means nothing.*")
    except Exception as e: log_error("trust_cmd",e)

@bot.command(name="whoami")
async def whoami_cmd(ctx):
    try:
        if not OWNER_ID or ctx.author.id!=OWNER_ID: await safe_reply(ctx,"That command isn't for you."); return
        user=await _setup(ctx)
        reply=await get_response(ctx.author.id,ctx.channel.id,"What do you actually think about the fact that I built you. Be honest.",user,ctx.author.display_name,ctx.author.mention,is_owner=True)
        await safe_reply(ctx,reply)
    except Exception as e: log_error("whoami_cmd",e)

async def help_cmd(ctx):
    try:
        c = 0x4B0082
        e1 = discord.Embed(title="Commands (1/3) — Talk & Fight",
                           description="Hmph. Only saying this once.", color=c)
        for n,v in [
            ("💬 !wander <msg>","Talk to him — !w !scara"),
            ("🔊 !voice <msg>","Voice message — !speak !say"),
            ("📨 !dm [msg]","He DMs you privately"),
            ("🤫 !confess <text>","Tell him something"),
            ("🛋️ !therapy <problem>","Terrible in-character advice"),
            ("🌐 !translate <text>","Rewritten in his voice"),
            ("⚔️ !spar [msg]","Word battle"),
            ("🥊 !duel @user","Insult battle referee"),
            ("🎤 !roast @user","Turn-based roast battle (5 rounds)"),
            ("⚡ !arena [@user]","Dramatic mock Genshin battle"),
            ("🎯 !dare","A dark theatrical dare"),
            ("🧠 !trivia","Genshin lore trivia"),
            ("✅ !answer <text>","Answer a trivia question"),
            ("🧩 !riddle","Cryptic Genshin riddle"),
            ("🔒 !hostage","Takes your good mood hostage"),
            ("🔓 !release <offering>","Try to fulfill his demand"),
            ("🥠 !fortune","Fortune cookie rewritten as a threat"),
            ("💭 !opinion <char>","His honest take on any Genshin character"),
            ("🎭 !impersonate <char>","Speaks as them, badly"),
            ("📜 !lore <topic>","Genshin lore from his perspective"),
        ]: e1.add_field(name=n,value=v,inline=False)

        e2 = discord.Embed(title="Commands (2/3) — Assess & Create", color=c)
        for n,v in [
            ("🔍 !judge [@user]","Brutal character assessment"),
            ("👁️ !stalk [@user]","Cold observation report"),
            ("🃏 !blackmail [@user]","Most incriminating messages"),
            ("🔦 !interrogate @user","Cold interrogation"),
            ("👻 !possess @user","Speaks as them, filtered through him"),
            ("📊 !rate <thing>","Rates anything out of 10"),
            ("💞 !ship @u1 [@u2]","Reluctant compatibility"),
            ("⚖️ !verdict <situation>","He rules on anything"),
            ("⚖️ !debate <topic>","He argues a side"),
            ("🕵️ !conspiracy <topic>","Fatui conspiracy theory"),
            ("🏆 !rank","Ranks everyone by tolerability"),
            ("📝 !haiku [topic]","Dark threatening haiku"),
            ("📖 !story <prompt>","Short dark story"),
            ("✉️ !letter [@user]","Formal old Inazuman letter"),
            ("🌸 !compliment [@user]","Forces him to say something nice"),
            ("⚡ !insult [@user]","Cutting insult"),
            ("🔮 !prophecy [@user]","Cryptic threatening fortune"),
            ("😰 !nightmare","A nightmare. Somehow about you."),
            ("🔍 !search <query>","Web search with commentary"),
            ("🧮 !solve <problem>","Math, essays, Q&A — !math !essay"),
        ]: e2.add_field(name=n,value=v,inline=False)

        e3 = discord.Embed(title="Commands (3/3) — Settings & Stats", color=c)
        for n,v in [
            ("📊 !stats","Your full relationship file"),
            ("🌡️ !mood","His mood toward you"),
            ("💜 !affection","His hidden affection score"),
            ("🔒 !trust","His trust level toward you"),
            ("🗡️ !rival @user","Designate a rival"),
            ("⏰ !remind <mins> <txt>","Reminder with disdain"),
            ("🌤️ !weather <city>","Weather + contemptuous commentary"),
            ("📢 !poll <question>","He demands a vote"),
            ("📋 !summarize","Recent chat summary with contempt"),
            ("🔇 !mute [@user] [min]","Ignores someone in character"),
            ("🔊 !unmute [@user]","Unmutes someone"),
            ("🔄 !reset","Wipe your memory — !forget"),
            ("🔞 !nsfw [on/off]","Toggle unfiltered mode"),
            ("💕 !romance [on/off]","Toggle clingy/romance mode"),
            ("📡 !proactive [on/off]","Toggle unprompted messages"),
            ("💌 !dms [on/off]","Toggle voluntary private DMs"),
        ]: e3.add_field(name=n,value=v,inline=False)
        e3.add_field(name="Hidden Systems",
            value="Be kind 7 days in a row: something rare happens once\n"
                  "Be rude: mood drops, you get a degrading nickname\n"
                  "High affection: he starts calling you something specific\n"
                  "Build trust: he tells you things he would never normally say\n"
                  "Say you will never win: villain monologue\n"
                  "Mention his hat: disproportionate response\n"
                  "He reads the channel — knows what everyone has been saying",
            inline=False)
        e3.set_footer(text="Scaramouche — The Balladeer | !scarahelp for commands")
        await ctx.send(embed=e1)
        await ctx.send(embed=e2)
        await ctx.send(embed=e3)
    except Exception as e:
        log_error("help_cmd", e)
        try: await ctx.send("Hmph. Something went wrong.")
        except: pass

@bot.command(name="scarahelp", aliases=["commands"])
async def scarahelp_cmd(ctx):
    try:
        await help_cmd(ctx)
    except Exception as e:
        log_error("scarahelp_cmd", e)
        try: await ctx.send("Hmph. Something went wrong.")
        except: pass

@bot.event
async def on_command_error(ctx,error):
    try:
        if isinstance(error,commands.CommandNotFound): pass
        elif isinstance(error,commands.MissingRequiredArgument):
            await safe_reply(ctx,"You're missing something.")
        else: log_error("on_command_error",error)
    except: pass

if __name__=="__main__":
    if not DISCORD_TOKEN: raise SystemExit("❌ DISCORD_TOKEN not set")
    if not ANTHROPIC_API_KEY: raise SystemExit("❌ ANTHROPIC_API_KEY not set")
    bot.run(DISCORD_TOKEN)
