"""Audience attribution for optional two-bot banter (no Discord side effects)."""
import re
from dataclasses import dataclass, field


def safe_reference_name(value: str) -> str:
    """Display-only name: not a mention, instruction, or verified relationship."""
    return re.sub(r"[^\w .'-]", "", str(value or ""))[:48].strip()


def jealousy_context(partner_name: str, bystander_name: str) -> str:
    """Keep the jealous joke aimed at the *partner*, not the third person."""
    name = safe_reference_name(bystander_name)
    if not name:
        return ""
    return (
        f"\nJEALOUSY_REFERENCE: {name!r} is a romance-mode person in the channel, "
        f"not the author of this message. PARTNER_SPEAKER: {partner_name}. "
        "Keep your jealous, competitive teasing as sharp as usual; you may "
        "reference or tag the romance-mode person as part of a clearly framed "
        "joke. Do not present that person as the one who made the partner's "
        "statement, and never invent an opinion they did not give."
    )


def coherent_partner_reply(text: str, partner_name: str, bystander_name: str = "") -> str:
    """Preserve natural banter and @ mentions; reject only clear misattribution."""
    text = (text or "").strip()
    if not text:
        return ""
    name = safe_reference_name(bystander_name)
    if name and re.match(
        rf"^(?:hey\s+)?{re.escape(name)}\s*[,!:](?:\s|$)",
        text, flags=re.IGNORECASE,
    ):
        return ""
    return text


def contextual_romance_tag(text: str, name: str, mention: str) -> str:
    """Use the existing romance ping inside the jealousy joke, not as its addressee.

    Called only after the original 45% romance mention selection.
    """
    text = (text or "").strip()
    if not text or not mention:
        return text
    if mention in text:
        return text
    name = safe_reference_name(name)
    if name:
        hit = re.search(rf"(?<!\w){re.escape(name)}(?!\w)", text, flags=re.IGNORECASE)
        if hit:
            return text[:hit.start()] + mention + text[hit.end():]
    return text + f" And don't expect {mention} to rescue that argument."


@dataclass(frozen=True)
class TurnEnvelope:
    """Immutable attribution for a bot-to-bot turn; no Discord side effects."""
    source_message_id: int
    channel_id: int
    speaker_id: int
    speaker_kind: str
    addressee_id: int
    addressee_kind: str
    explicit_human_target_ids: frozenset[int] = field(default_factory=frozenset)
    romance_target_id: int | None = None
    mode: str = "rivalry"


def authorized_ping_ids(turn: TurnEnvelope, *, romance_ping_selected: bool = False) -> frozenset[int]:
    """Allow verified interaction targets without suppressing in-character mention text."""
    ids = set(turn.explicit_human_target_ids)
    if turn.speaker_id > 0:
        ids.add(turn.speaker_id)
    if romance_ping_selected and turn.romance_target_id is not None:
        ids.add(turn.romance_target_id)
    return frozenset(uid for uid in ids if isinstance(uid, int) and uid > 0)
