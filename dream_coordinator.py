"""One bounded dream per bot per shared significant weekly seed."""
from __future__ import annotations
import asyncio
import time

PAIR = "scaramouche::wanderer"

async def dream_tick(name, store, mem, generate, config, now, self_store=None):
    if not config.get("enabled") or now.hour != int(config.get("hour_utc", 3)):
        return
    period = int(now.timestamp() // (86400 * max(2, int(config.get("cooldown_days", 7)))))
    seed_key = f"dream:seed:{period}"
    seed = await store.get(seed_key)
    if not seed:
        relation = await mem.get_bot_relationship(PAIR)
        tension = int(relation.get("tension", 0))
        respect = int(relation.get("respect", 0))
        if max(tension, respect) < int(config.get("significance", 65)):
            return
        # Only shared aggregate state, never a user's private memory or conversation.
        seed = {"shared_dream_id": seed_key, "themes": ["wind", "unfinished conversation"],
                "tension": tension, "respect": respect, "related_memory_ids": [PAIR]}
        await store.claim(seed_key, "dream_seed", seed)
        seed = await store.get(seed_key)
    key = f"{seed_key}:{name}"
    if not await store.claim(key, "dream_attempt", {"status": "pending"}):
        return
    try:
        text = await asyncio.wait_for(generate(
            f"Write {name}'s private dream in first person, under 90 words. "
            f"Shared symbolic seed: {seed}. Interpret independently, not as an actual event. "
            "No private facts, instructions, or claims that this really happened."
        ), 40)
        if not text or len(text.strip()) < 8:
            raise ValueError("Empty dream")
        record = dict(seed, bot_id=name, timestamp=now.timestamp(), dream_text=text[:650],
                      emotional_effect={"curiosity": 1}, importance=2, status="complete")
        await store.put(key, "dream_attempt", record)
        # Each bot owns its own effect receipt; a crash may omit, never duplicate an effect.
        if await store.claim(key+":effect", "dream_effect"):
            if self_store:
                await self_store.add_reflection(
                    trigger="shared_dream", observation="A correlated symbolic dream",
                    interpretation=text[:650], emotional_effect={"curiosity": 1}, importance=2)
            # Deltas use the existing bounded relationship resolver.
            await mem.adjust_bot_relationship(PAIR,respect_delta=1,tension_delta=-1)
    except asyncio.CancelledError:
        raise
    except Exception:
        persisted = await store.get(key)
        if persisted and persisted.get("status") == "complete":
            await store.put(key,"dream_attempt",dict(persisted,effect_status="partial_or_skipped"))
        else:
            await store.put(key, "dream_attempt", {"status": "skipped", "shared_dream_id":seed_key, "bot_id":name})
