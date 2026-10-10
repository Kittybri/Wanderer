"""Audience attribution for optional two-bot banter (no Discord side effects)."""
import re


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
        f"not the speaker and not the addressee. PRIMARY_ADDRESSEE: {partner_name}. "
        "You may mention that name *in the third person* in one jealous jab "
        "at the partner, but do not assert they said anything, address them "
        "directly, ping them, or treat them as the person you are replying to."
    )


def coherent_partner_reply(text: str, partner_name: str, bystander_name: str = "") -> str:
    """Reject misaddressed/pinging optional replies and make the bot target explicit."""
    text = (text or "").strip()
    if not text or "@" in text:
        return ""
    name = safe_reference_name(bystander_name)
    if name and re.match(rf"^(?:hey\s+)?{re.escape(name)}(?=\W|$)", text, flags=re.IGNORECASE):
        return ""
    if not re.match(rf"^{re.escape(partner_name)}(?=\W|$)", text, flags=re.IGNORECASE):
        return f"{partner_name}, {text}"
    return text
