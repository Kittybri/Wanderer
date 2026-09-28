"""Deterministic VC character decisions; no LLM calls and no voice cloning."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from awareness_features import classify_safety, is_sensitive_memory


class Handoff(str, Enum):
    AGREE = "agree"
    DISAGREE = "disagree"
    CORRECT = "correct"
    TAKE_OVER = "take_over"
    FINISH_THOUGHT = "finish_thought"
    DEFUSE = "defuse"


@dataclass(frozen=True)
class VoiceEvent:
    kind: str
    user_id: int
    text: str = ""
    data: object = None


def urgent(text):
    return classify_safety(text).protective or bool(
        re.search(r"\b(serious|urgent|emergency|actually need help)\b", text, re.I)
    )


def interruption_kind(text, count):
    if urgent(text):
        return "urgent"
    if re.search(r"\b(sorry|accident|go ahead|didn't mean)\b", text, re.I):
        return "accidental_overlap"
    if re.search(r"\b(hate you|idiot|stupid|shut up)\b", text, re.I):
        return "hostile"
    deliberate = bool(
        re.search(r"\b(interrupt|stop talking|not letting you finish)\b", text, re.I)
    )
    if deliberate and count >= 3:
        return "repeated_deliberate"
    if re.search(r"\b(haha|kidding|teasing|joking)\b", text, re.I):
        return "playful"
    return "normal"


def interruption_context(name, kind):
    if kind == "urgent":
        return "URGENT: stop banter, annoyance and games. Address the user's real need with practical care. No grudge."
    if kind == "accidental_overlap":
        return (
            "Accidental overlap. Adapt naturally, with no emotional penalty or grudge."
        )
    if name == "wanderer":
        return f"Interruption: {kind}. Adapt, clarify and keep helping; do not imitate Scaramouche's wounded pride. No automatic grudge."
    return f"Interruption: {kind}. Brief, temporary pride/irritation or amusement may color your dialogue. Remain useful. Only explicit repeated provocation warrants conflict; never treat VAD alone as a grievance."


def safe_parody(text):
    if not text or len(text) > 180 or urgent(text) or is_sensitive_memory(text):
        return False
    if re.search(
        r"https?://|@|\d{4,}|[<>{}]|\b(sex|nude|rape|kill|murder|steal|stole|crime|gun|bomb|hurt|die|dead|money|dollars|buy|sell|invest|identity|gender|diagnosis|secret|address|phone|email|login|my name|i am|i'm)\b",
        text,
        re.I,
    ):
        return False
    # Intentionally narrow game vocabulary: no open-ended model paraphrasing can
    # turn a private disclosure into a joke or invent a statement by the user.
    allowed = set(
        "guys maybe we you they should could can will fight the boss first second now later next again attack heal dodge run wait team game quest puzzle strategy hat hats this that is was a an good bad great terrible silly funny joke best worst plan use try our their your and or but not yes no please just really very too so then here there win lose level shield sword magic".split()
    )
    return all(word in allowed for word in re.findall(r"[a-z']+", text.lower()))


def parody(name, text):
    if not safe_parody(text):
        return ""
    quote = text.strip().replace('"', "'")
    if name == "wanderer":
        return f'"{quote}" You do make it sound dramatic. Still, let us see whether it works.'
    return f'Oh, "{quote}". What a revolutionary contribution. Consider me overwhelmed.'


def handoff_context(name, kind, topic):
    if urgent(topic):
        kind = Handoff.DEFUSE
    role = (
        "Be the sharp, theatrical critic, but give useful substance; do not sabotage the answer."
        if name == "scaramouche"
        else "Be the practical helper and mediator. Correct unhelpful theatrics; provide concrete help, not a softer copy of Scaramouche."
    )
    return f"STRUCTURED VOICE DUO: {kind.value}. {role} One brief useful turn, then hand off. Never claim the partner said words not in conversation history. No microphone-triggered bot replies."


def priority_status(channel, member):
    try:
        allowed = bool(channel.permissions_for(member).priority_speaker)
    except (AttributeError, TypeError):
        return {"permission": False, "activation": "unavailable"}
    return {
        "permission": allowed,
        "activation": "not_implemented",
        "reason": "Discord opcode supports priority; discord.py AudioPlayer manages ordinary speaking state. Permission is not activation.",
    }
