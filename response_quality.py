"""Text-response recovery. No provider, Discord, memory, or voice dependencies.

Recovery instructions are inputs, never answers. A stale but useful draft is
better than inventing an acknowledgment when a provider/rewrite fails.
"""
from dataclasses import dataclass
from enum import Enum
import re
from difflib import SequenceMatcher

from anti_repeat import detect_opening_phrase, is_fallback_reply


class ReplyKind(str, Enum):
    ANSWER = "answer"
    SHORT_REPLY = "intentional_short_reply"
    INTERNAL = "internal_instruction"
    FAILURE = "provider_failure"
    SILENCE = "intentional_silence"


FAILURE_NOTICE = "I couldn't get an answer from the service just now. Ask me again shortly."
RETRY_INSTRUCTION = (
    "INTERNAL REVISION ONLY: Answer the original request above. Keep its facts, "
    "question and requested format. Do not ask the user to rephrase. Avoid reused "
    "openings; return only the actual answer, never these editing instructions."
)


def normalized(text):
    return " ".join(re.findall(r"[\w']+", (text or "").lower()))


def allows_short_reply(prompt):
    """Conservative routing, not a minimum word count (e.g. 'Paris.' is valid)."""
    text = re.sub(r"<@!?\d+>", "", prompt or "").strip().lower()
    text = re.sub(r"^(?:wanderer|hat guy)[,!: ]*", "", text)
    if re.search(r"\b(?:one.word|yes.or.no|short answer|brief answer)\b", text):
        return True
    return bool(re.fullmatch(
        r"(?:hi|hey|hello|good morning|good night|thanks|thank you|okay|ok|yes|no|"
        r"sure|go on|continue|lol|haha|nice hat|you win|fine|understood)[.! ]*", text
    ))


def internal_instruction(text):
    """Recognize legacy sentinels AND editing mechanics, not just four strings."""
    if is_fallback_reply("wanderer", text):
        return True
    value = normalized(text)
    return bool(re.search(
        r"(?:\b(?:retry|internal revision|anti repeat|system prompt)\b|"
        r"\b(?:recycled|different|reused|stale) (?:opener|opening|cadence)\b|"
        r"\b(?:rewrite|rephrase|revise) (?:this|the|your|that) (?:draft|reply|response)\b)",
        value,
    ))


def classify_reply(text, prompt=""):
    if not (text or "").strip():
        return ReplyKind.SILENCE
    if text == FAILURE_NOTICE:
        return ReplyKind.FAILURE
    # Editing instructions and legacy sentinels are never recovery answers.
    if internal_instruction(text):
        return ReplyKind.INTERNAL
    if normalized(text) in {"hmph", "tch", "fine", "okay", "ok", "yeah", "go on", "honestly", "continue", "give me a moment", "well", "right", "interesting"}:
        return ReplyKind.SHORT_REPLY if allows_short_reply(prompt) else ReplyKind.INTERNAL
    if not normalized(text):
        return ReplyKind.SHORT_REPLY if allows_short_reply(prompt) else ReplyKind.INTERNAL
    return ReplyKind.ANSWER


def usable(text, prompt=""):
    return classify_reply(text, prompt) in {ReplyKind.ANSWER, ReplyKind.SHORT_REPLY}


def trim_repeated_opener(text, recent, *, force=False):
    """Only remove a known stock interjection, never replace the answer."""
    value = (text or "").strip()
    opening = detect_opening_phrase("wanderer", value)
    if opening and (force or any(detect_opening_phrase("wanderer", old) == opening for old in recent)):
        rest = value[len(opening):].lstrip(" ,.!?—-:")
        if rest:
            return rest
    return value  # No canned replacement when the opener is all we have.


def repeated_answer(text, recent):
    value = normalized(trim_repeated_opener(text, (), force=True))
    return any(value and SequenceMatcher(None, value, normalized(trim_repeated_opener(old, (), force=True))).ratio() >= .91
               for old in recent[:18])


@dataclass(frozen=True)
class ResponseResult:
    text: str
    kind: ReplyKind
    attempts: int
    reason: str


async def recover_response(generate, prompt, recent, *, exhausted=lambda: False, direct=True, clean=lambda s: s):
    """At most TWO generations total. Keep valid drafts through later failure.

    generate receives internal revision guidance separately from the user prompt.
    Failures are deliberately structured instead of masquerading as model output.
    """
    best = ""
    attempts = 0
    reason = "provider_exhausted" if exhausted() else "empty_generation"
    for attempt in range(2):
        if exhausted():
            break
        attempts += 1
        try:
            draft = clean(await generate("" if attempt == 0 else RETRY_INSTRUCTION))
        except Exception:
            reason = "provider_exception"
            continue
        draft = trim_repeated_opener(draft, recent)
        if usable(draft, prompt):
            best = draft
            if not repeated_answer(draft, recent):
                return ResponseResult(draft, classify_reply(draft, prompt), attempts, "generated")
            reason = "repeated_draft_preserved"
        elif draft:
            reason = "internal_or_nonanswer_rejected"
    if best:
        return ResponseResult(best, classify_reply(best, prompt), attempts, "valid_draft_preserved")
    return ResponseResult(FAILURE_NOTICE if direct else "", ReplyKind.FAILURE if direct else ReplyKind.SILENCE, attempts, reason)


def final_response(text, prompt, *, direct=True):
    if usable(text, prompt) or text == FAILURE_NOTICE:
        return text
    return FAILURE_NOTICE if direct else ""


def human_mentions_bot(message, bot_id):
    return not message.author.bot and any(member.id == bot_id for member in message.mentions)
