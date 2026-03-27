import re


STYLE_KEYS = ("playful", "gentle", "curious", "vulnerable", "intense", "lore", "teasing")
TOPIC_HINTS = {
    "food": ("food", "eat", "meal", "hungry", "tea", "sweet", "snack", "drink", "cooking"),
    "sleep": ("sleep", "tired", "nap", "rest", "bed", "dream", "insomnia"),
    "weather": ("weather", "rain", "storm", "sun", "wind", "cold", "hot"),
    "genshin_lore": ("genshin", "teyvat", "fatui", "harbinger", "archon", "irminsul", "nahida", "ei", "traveler", "traveller"),
    "feelings": ("love", "miss", "lonely", "scared", "cry", "feel", "feelings", "care", "hurt"),
    "other_bot": ("scaramouche", "wanderer", "scara", "other bot", "different bot"),
    "daily_life": ("school", "work", "class", "home", "family", "friend", "friends"),
    "health": ("sick", "headache", "pain", "doctor", "medicine", "healing", "health"),
}


RARE_PHRASES = {
    "scaramouche": {
        "how quaint": {
            "cooldown": 21600,
            "replacements": [
                "Predictable.",
                "That was a tiny little performance.",
                "So that is the level you're working with.",
                "You really led with that.",
            ],
        },
        "how unfortunate": {
            "cooldown": 21600,
            "replacements": [
                "That tracks.",
                "How drearily predictable.",
                "What a disappointing turn.",
                "Exactly as expected.",
            ],
        },
        "tch": {
            "cooldown": 5400,
            "replacements": [
                "Pathetic.",
                "What now.",
                "You are trying my patience.",
                "Go on, then.",
            ],
        },
    },
    "wanderer": {
        "tch": {
            "cooldown": 21600,
            "mood_threshold": -6,
            "replacements": [
                "Honestly.",
                "That is getting old.",
                "You are making this tedious.",
                "There are easier ways to annoy me.",
            ],
        },
        "how irritating": {
            "cooldown": 28800,
            "replacements": [
                "You are making this tedious.",
                "That is getting old already.",
                "You really are testing my patience.",
                "And here I thought this might stay interesting.",
            ],
        },
        "how childish": {
            "cooldown": 28800,
            "replacements": [
                "That was embarrassingly juvenile.",
                "You really went with that.",
                "Try again with a little dignity.",
                "That is the level you settled on.",
            ],
        },
    },
}


def clamp(value: int, minimum: int = 0, maximum: int = 100) -> int:
    return max(minimum, min(maximum, int(value)))


def default_style_profile() -> dict:
    return {key: 0 for key in STYLE_KEYS}


def normalize_style_profile(profile: dict | None) -> dict:
    normalized = default_style_profile()
    if not isinstance(profile, dict):
        return normalized
    for key in STYLE_KEYS:
        normalized[key] = clamp(profile.get(key, 0))
    return normalized


def analyze_style_deltas(text: str) -> dict:
    content = (text or "").strip()
    lowered = content.lower()
    deltas = default_style_profile()

    if any(token in lowered for token in ["lol", "lmao", "haha", "hehe", "joking", "kidding"]):
        deltas["playful"] += 3
        deltas["teasing"] += 1
    if any(token in lowered for token in ["thank", "thanks", "appreciate", "care", "eat", "sleep", "rest", "be safe"]):
        deltas["gentle"] += 2
    if "?" in content or any(lowered.startswith(prefix) for prefix in ["what", "why", "how", "when", "tell me", "explain"]):
        deltas["curious"] += 2
    if len(content) > 120:
        deltas["curious"] += 1
    if any(token in lowered for token in ["sorry", "miss you", "alone", "scared", "hurt", "cry", "lonely", "love", "confess", "feel", "feelings"]):
        deltas["vulnerable"] += 3
    if any(token in lowered for token in ["shut up", "go away", "idiot", "stupid", "hate", "annoying", "prefer", "other bot", "different bot"]):
        deltas["intense"] += 3
    if content.count("!") >= 2 or content.isupper():
        deltas["intense"] += 2
    if any(token in lowered for token in ["genshin", "teyvat", "fatui", "harbinger", "archon", "irminsul", "nahida", "ei", "traveler", "traveller"]):
        deltas["lore"] += 3
    if any(token in lowered for token in ["brat", "coward", "you wish", "as if", "sure you do", "keep talking"]):
        deltas["teasing"] += 2

    return deltas


def apply_style_deltas(profile: dict | None, deltas: dict | None) -> dict:
    updated = normalize_style_profile(profile)
    deltas = deltas or {}
    for key in STYLE_KEYS:
        updated[key] = clamp(updated.get(key, 0) + int(deltas.get(key, 0)))
    return updated


def top_style_traits(profile: dict | None, minimum: int = 8, limit: int = 3) -> list[str]:
    normalized = normalize_style_profile(profile)
    ranked = sorted(normalized.items(), key=lambda item: item[1], reverse=True)
    return [name for name, value in ranked if value >= minimum][:limit]


def describe_speech_drift(bot_name: str, profile: dict | None) -> str:
    traits = top_style_traits(profile)
    if not traits:
        return ""

    lines = []
    if bot_name == "scaramouche":
        mapping = {
            "playful": "with this person you sound a little more sly and amused than usual",
            "gentle": "with this person your contempt keeps slipping into sharp concern",
            "curious": "with this person you indulge longer answers and more pointed questions",
            "vulnerable": "with this person you get quieter and more precise when things turn personal",
            "intense": "with this person you come in hotter and more openly possessive",
            "lore": "with this person you get denser, more philosophical, and more specific about Teyvat",
            "teasing": "with this person you needle them with more personal, tailored mockery",
        }
    else:
        mapping = {
            "playful": "with this person you sound more dryly amused and less guarded",
            "gentle": "with this person your irritation keeps giving way to practical care",
            "curious": "with this person you indulge reflection and real answers instead of brushing them off",
            "vulnerable": "with this person your voice turns more candid when the subject gets personal",
            "intense": "with this person you sharpen quickly and stop pretending not to care",
            "lore": "with this person you get more reflective, specific, and lore-heavy",
            "teasing": "with this person you tease with familiarity instead of distance",
        }
    for trait in traits:
        if trait in mapping:
            lines.append(mapping[trait])
    return "; ".join(lines[:2])


def compute_emotional_arc(
    affection: int,
    trust: int,
    slow_burn: int = 0,
    conflict_open: bool = False,
    repair_count: int = 0,
) -> str:
    if conflict_open and (affection >= 30 or trust >= 25):
        return "conflicted"
    if repair_count > 0 and (affection >= 35 or trust >= 35):
        return "repairing"
    if affection >= 80 and trust >= 70:
        return "devoted"
    if affection >= 60 or trust >= 55 or slow_burn >= 5:
        return "tender"
    if affection >= 35 or trust >= 35:
        return "drawn_in"
    if affection >= 15 or trust >= 15:
        return "curious"
    return "guarded"


def describe_emotional_arc(bot_name: str, arc: str) -> str:
    if bot_name == "scaramouche":
        mapping = {
            "guarded": "the wall is still up",
            "curious": "you are circling them more than you admit",
            "drawn_in": "you are paying attention in a way that has started to cost you",
            "tender": "warmth keeps leaking through the contempt",
            "conflicted": "you are hurt and acting sharper because of it",
            "repairing": "you are trying to pretend the repair means nothing",
            "devoted": "you are attached enough to become dangerous about it",
        }
    else:
        mapping = {
            "guarded": "you are still keeping your distance",
            "curious": "you are staying near them longer than necessary",
            "drawn_in": "you are getting personally invested and disliking it",
            "tender": "care keeps surfacing before you can flatten it",
            "conflicted": "you are hurt and hiding it behind sharper answers",
            "repairing": "you are testing whether trust can be rebuilt",
            "devoted": "they matter to you enough that your composure keeps slipping",
        }
    return mapping.get(arc or "guarded", "")


def detect_conflict_signal(text: str) -> bool:
    lowered = (text or "").lower()
    return any(
        token in lowered
        for token in [
            "shut up",
            "go away",
            "leave me alone",
            "hate you",
            "other bot",
            "different bot",
            "prefer",
            "switch to",
            "annoying",
            "whatever",
            "you suck",
        ]
    )


def detect_repair_signal(text: str) -> bool:
    lowered = (text or "").lower()
    return any(
        token in lowered
        for token in [
            "sorry",
            "i'm sorry",
            "i am sorry",
            "forgive me",
            "forgive",
            "didn't mean",
            "did not mean",
            "can we talk",
            "miss you",
            "i appreciate you",
            "thank you",
            "are you okay",
            "are u okay",
        ]
    )


def extract_callback_candidate(text: str) -> str:
    content = " ".join((text or "").strip().split())
    if len(content) < 24:
        return ""
    lowered = content.lower()
    if any(
        token in lowered
        for token in [
            "i love",
            "i miss",
            "i'm scared",
            "i am scared",
            "i'm tired",
            "i am tired",
            "promise",
            "remember this",
            "don't forget",
            "confess",
            "i need you",
            "i need u",
            "i trust you",
            "stay",
        ]
    ):
        return content[:220]
    if len(content) > 140:
        return content[:220]
    return ""


def callback_relevant(callback_memory: str, text: str) -> bool:
    if not callback_memory:
        return False
    callback_words = {word for word in re.findall(r"[a-z']+", callback_memory.lower()) if len(word) > 3}
    text_words = {word for word in re.findall(r"[a-z']+", (text or "").lower()) if len(word) > 3}
    return len(callback_words & text_words) >= 2


def detect_topics(text: str) -> list[str]:
    lowered = (text or "").lower()
    found: list[str] = []
    for topic, hints in TOPIC_HINTS.items():
        if any(token in lowered for token in hints):
            found.append(topic)
    return found[:4]


def describe_topic_profile(topics: list[dict] | None) -> str:
    if not topics:
        return ""
    bits = []
    for item in topics[:3]:
        name = item.get("topic")
        count = item.get("count", 0)
        if name:
            bits.append(f"{name}({count})")
    return ", ".join(bits)


def describe_conflict_followup(summary: str | None, stage: str | None = None) -> str:
    if not summary:
        return ""
    if stage == "repairing":
        return f"You have unresolved tension from earlier, but the repair has started: {summary[:140]}"
    return f"There is still unresolved tension you have not let go of: {summary[:140]}"


def relationship_milestone_note(stage: str, respect: int, tension: int) -> str:
    if stage == "reluctant respect" and respect >= 55:
        return "You have reached the point where denying all respect would sound false. Keep the edge, but let earned recognition slip through."
    if stage == "competitive" and respect >= 30:
        return "This rivalry has matured into something sharper than hate. Competition is replacing pure contempt."
    if tension >= 80:
        return "The tension is high enough that old wounds should surface fast, with less patience and more specificity."
    return ""


def detect_banter_theme(text: str) -> str:
    lowered = (text or "").lower()
    if any(token in lowered for token in ["pretender", "imposter", "copy", "past self", "future self", "same face"]):
        return "identity"
    if any(token in lowered for token in ["weak", "weakness", "soft", "pathetic", "coward"]):
        return "weakness"
    if any(token in lowered for token in ["change", "changed", "different", "better now"]):
        return "change"
    if any(token in lowered for token in ["creator", "built", "made", "ei", "nahida", "traveler", "traveller"]):
        return "origins"
    if any(token in lowered for token in ["prefer", "mine", "jealous", "romance", "love"]):
        return "jealousy"
    if any(token in lowered for token in ["power", "gnosis", "harbinger", "electro", "anemo"]):
        return "power"
    if "hat" in lowered:
        return "hat"
    return "general"


def infer_bot_relation_deltas(text: str, theme: str) -> tuple[int, int]:
    lowered = (text or "").lower()
    respect = 1 if theme in {"power", "origins", "change"} else 0
    tension = 2 if theme in {"identity", "weakness", "jealousy"} else 0
    if any(token in lowered for token in ["imposter", "pretender", "pathetic", "failure", "weak", "discarded"]):
        tension += 3
    if any(token in lowered for token in ["understand", "remember", "still here", "not entirely wrong", "capable", "useful"]):
        respect += 2
    return respect, tension


def compute_bot_stage(respect: int, tension: int) -> str:
    if respect >= 55 and tension <= 45:
        return "reluctant respect"
    if respect >= 30 and tension <= 70:
        return "competitive"
    if respect >= 15:
        return "hostile"
    return "enemy"


def describe_bot_relationship(bot_name: str, relation: dict | None, recent_banter: list[dict] | None = None) -> str:
    relation = relation or {}
    recent_banter = recent_banter or []
    stage = relation.get("stage", "enemy")
    respect = relation.get("respect", 0)
    tension = relation.get("tension", 0)
    history = relation.get("shared_history", "")
    recent_shots = []
    for item in recent_banter[:4]:
        content = (item.get("content") or "").strip()
        if content:
            recent_shots.append(content[:120])

    lines = [
        f"PARTNER_STAGE:{stage}",
        f"PARTNER_METRICS:respect={respect}|tension={tension}",
    ]
    if history:
        lines.append(f"PARTNER_HISTORY:{history[:320]}")
    if recent_shots:
        lines.append("PARTNER_RECENT_SHOTS:" + " || ".join(recent_shots))
    if bot_name == "scaramouche":
        lines.append("Let the rivalry evolve. Pure denial every time is stale; if respect has grown, let it show as sharper precision instead of the same old sneer.")
    else:
        lines.append("Let the shared history show. You can still be sharp without pretending every exchange is the first wound.")
    return "\n".join(lines)
