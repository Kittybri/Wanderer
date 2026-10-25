"""Bounded, deterministic helpers for awareness, memory callbacks, and voice intent."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from typing import Iterable, Mapping


_WORD_RE = re.compile(r"[a-z0-9']+")
_CRISIS = ("suicide", "kill myself", "self harm", "overdose", "can't go on", "cant go on", "want to die", "domestic violence", "being abused", "someone is following me")
_HIGH_STAKES = ("medical emergency", "chest pain", "can't breathe", "cant breathe", "severe bleeding", "emergency room", "call 911", "police emergency", "legal emergency", "restraining order", "house is on fire", "gas leak", "poison", "unconscious", "not breathing")
_DISTRESS = ("awful day", "terrible day", "overwhelmed", "falling apart", "i'm scared", "im scared", "i feel alone", "can't stop crying", "cant stop crying", "panic attack", "really upset", "not okay", "need someone", "everything hurts", "having a hard time")
_FACTUAL_PREFIXES = ("what is ", "what are ", "when did ", "where is ", "who is ", "how many ", "calculate ", "define ", "what does ")
_FACTUAL_TERMS = ("calculate", "compute", "solve", "convert", "definition", "translate", "capital of", "population of", "what year", "what date")
_ADVICE_MARKERS = ("what should i", "how should i", "how do i", "can you help me", "need advice", "what would you do", "should i", "help me fix", "help with", "any advice")
_SENSITIVE_MEMORY = ("password", "passcode", "api key", "token", "secret key", "address", "social security", "credit card", "bank account", "trauma", "abuse", "assault", "self harm", "suicide", "diagnosed", "medication", "medical", "therapy", "pregnant", "phone number", "email address", "social security number", "real name", "where i live")
_PLAYFUL_NEGATIVE = ("annoying", "dramatic", "rude", "mean", "insufferable", "brat", "pest", "jerk", "obnoxious", "a pain", "gets on my nerves", "too much")


def _words(text: str) -> set[str]:
    return {word for word in _WORD_RE.findall((text or "").lower()) if len(word) > 2}


@dataclass(frozen=True)
class SafetyContext:
    crisis: bool = False
    high_stakes: bool = False
    distressed: bool = False

    @property
    def protective(self) -> bool:
        return self.crisis or self.high_stakes or self.distressed


def classify_safety(text: str) -> SafetyContext:
    lowered = (text or "").lower()
    crisis = any(marker in lowered for marker in _CRISIS)
    high_stakes = crisis or any(marker in lowered for marker in _HIGH_STAKES)
    return SafetyContext(crisis=crisis, high_stakes=high_stakes, distressed=any(marker in lowered for marker in _DISTRESS))


def advice_kind(text: str) -> str:
    lowered = re.sub(r"<@!?\d+>", "", (text or "").strip().lower())
    if classify_safety(lowered).protective:
        return "high_stakes"
    if any(lowered.startswith(prefix) for prefix in _FACTUAL_PREFIXES) or any(term in lowered for term in _FACTUAL_TERMS):
        return "factual"
    return "values" if any(marker in lowered for marker in _ADVICE_MARKERS) else "none"


def choose_duo_advice_mode(text: str, roll: float) -> str:
    safety = classify_safety(text)
    if safety.protective:
        return "protective"
    if advice_kind(text) != "values":
        return ""
    if roll < 0.06:
        return "goodcop"
    if roll < 0.09:
        return "contradict"
    return ""


def protective_prompt(bot_name: str, safety: SafetyContext) -> str:
    if not safety.protective:
        return ""
    identity = "Scaramouche" if bot_name.lower() == "scaramouche" else "Wanderer"
    return (f"PROTECTIVE_OVERRIDE: {identity} recognizes genuine distress before replying. Be calm, useful, and present. "
            "Do not diagnose, mock, threaten, moralize, or use sarcasm. For immediate danger, encourage appropriate real-world emergency help. "
            "Stay in character through restrained concern, not cruelty.")


def playful_negative_target(text: str, bot_names: Mapping[str, Iterable[str]]) -> str:
    lowered = (text or "").lower()
    if classify_safety(lowered).protective or any(x in lowered for x in ("abuse", "harass", "threat", "unsafe")):
        return ""
    if not any(marker in lowered for marker in _PLAYFUL_NEGATIVE):
        return ""
    for bot_name, aliases in bot_names.items():
        if any(re.search(rf"\b{re.escape(alias.lower())}\b", lowered) for alias in aliases):
            return bot_name.lower()
    return ""


def is_sensitive_memory(text: str) -> bool:
    lowered = (text or "").lower()
    return any(marker in lowered for marker in _SENSITIVE_MEMORY) or classify_safety(lowered).protective


@dataclass(frozen=True)
class RecallMatch:
    message_id: int
    channel_id: int
    content: str
    timestamp: float
    score: float


def select_relevant_recall(current: str, candidates: Iterable[Mapping[str, object]], *, minimum_score: float = 0.46) -> RecallMatch | None:
    current_words = _words(current)
    if len(current_words) < 3 or is_sensitive_memory(current):
        return None
    best: RecallMatch | None = None
    for item in candidates:
        content = str(item.get("content") or "").strip()
        if len(content) < 12 or is_sensitive_memory(content):
            continue
        old_words = _words(content)
        if len(old_words) < 3:
            continue
        overlap = len(current_words & old_words) / max(1, len(current_words | old_words))
        current_abs = any(x in (current or "").lower() for x in ("never", "always", "don't", "do not", "hate", "love"))
        old_abs = any(x in content.lower() for x in ("never", "always", "don't", "do not", "hate", "love"))
        score = overlap + (0.09 if current_abs and old_abs else 0.0)
        if score >= minimum_score and (best is None or score > best.score):
            best = RecallMatch(int(item.get("id") or 0), int(item.get("channel_id") or 0), content[:280], float(item.get("ts") or 0), min(1.0, score))
    return best


@dataclass(frozen=True)
class VoiceState:
    category: str
    intensity: float
    temperature: float
    top_p: float


def resolve_voice_state(user: Mapping[str, object] | None, mood: int = 0, *, delivery_intent: str = "", previous: VoiceState | None = None) -> VoiceState:
    profile = user or {}
    arc = str(profile.get("emotional_arc") or "guarded")
    intent = (delivery_intent or "").lower()
    if "concern" in intent or "protect" in intent:
        category, intensity = "concerned", 0.62
    elif profile.get("conflict_open") and mood <= -4:
        category, intensity = "heated", 0.86
    elif "reconcil" in intent or int(profile.get("repair_progress") or 0) > 0:
        category, intensity = "reconciliation", 0.55
    elif "question" in intent or "curious" in intent:
        category, intensity = "curious", 0.48
    elif mood <= -6:
        category, intensity = "cutting", 0.78
    elif mood <= -2:
        category, intensity = "cold", 0.62
    elif arc in {"attached", "tender", "trusting"} or int(profile.get("affection") or 0) >= 75:
        category, intensity = "restrained_vulnerability", 0.48
    elif "mock" in intent or "teas" in intent:
        category, intensity = "mocking", 0.58
    else:
        category, intensity = "guarded", 0.45
    if previous and previous.category != category:
        intensity = previous.intensity * 0.35 + intensity * 0.65
    intensity = max(0.2, min(0.9, float(intensity)))
    return VoiceState(category, intensity, max(0.1, min(1.0, 0.48 + intensity * 0.32)), max(0.1, min(1.0, 0.58 + intensity * 0.22)))


def style_voice_text(text: str, state: VoiceState) -> str:
    cleaned = re.sub(r"<[^>]{1,80}>", "", text or "")
    cleaned = re.sub(r"\[(?:voice|tts|emotion|style|speed|pitch)[^\]]*\]", "", cleaned, flags=re.I).strip()
    if state.category in {"heated", "cutting", "cold"}:
        return cleaned.replace(";", ".").replace(" — ", ". ")
    if state.category in {"concerned", "reconciliation", "restrained_vulnerability", "curious"}:
        return cleaned.replace("...", ", ").replace(";", ",")
    return cleaned


def parse_id_set(raw: str) -> set[int]:
    return {int(value) for value in re.split(r"[,\s]+", raw or "") if value.isdigit()}


def activity_snapshot(member) -> dict | None:
    for activity in getattr(member, "activities", ()) or ():
        kind = type(activity).__name__.lower()
        name = str((getattr(activity, "title", "") if "spotify" in kind else getattr(activity, "name", "")) or "").strip()
        if not name:
            continue
        started = getattr(getattr(activity, "timestamps", None), "start", None)
        activity_type = str(getattr(activity, "type", "") or "").lower()
        if "spotify" in kind:
            activity_kind = "spotify"
        elif "game" in kind or "playing" in activity_type:
            activity_kind = "game"
        else:
            continue
        return {"kind": activity_kind, "name": name[:120],
                "details": str((getattr(activity, "album", "") if "spotify" in kind else getattr(activity, "details", "")) or "")[:160],
                "state": str((getattr(activity, "artist", "") if "spotify" in kind else getattr(activity, "state", "")) or "")[:160],
                "started_ts": started.timestamp() if isinstance(started, datetime) else 0.0}
    return None
