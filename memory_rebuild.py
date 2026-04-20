from __future__ import annotations

import os
from typing import Any

import discord


REBUILD_HISTORY_PER_CHANNEL = int(os.getenv("REBUILD_HISTORY_PER_CHANNEL", "1200") or "1200")


def user_can_manage_rebuild(ctx, owner_id: int) -> bool:
    if owner_id and getattr(getattr(ctx, "author", None), "id", 0) == owner_id:
        return True
    perms = getattr(getattr(ctx, "author", None), "guild_permissions", None)
    return bool(perms and (perms.administrator or perms.manage_guild or perms.manage_messages))


def _history_channels_for_ctx(ctx) -> list[Any]:
    current = getattr(ctx, "channel", None)
    guild = getattr(ctx, "guild", None)
    me = getattr(ctx, "me", None) or getattr(guild, "me", None)
    channels: list[Any] = []
    seen: set[int] = set()

    def add_channel(channel: Any):
        channel_id = getattr(channel, "id", None)
        if channel_id is None or channel_id in seen or not hasattr(channel, "history"):
            return
        seen.add(channel_id)
        channels.append(channel)

    if guild is None:
        add_channel(current)
        return channels

    if isinstance(current, discord.Thread):
        add_channel(current)

    for channel in sorted(getattr(guild, "text_channels", []), key=lambda item: (item.position, item.id)):
        try:
            perms = channel.permissions_for(me) if me else None
            if perms and perms.read_messages and perms.read_message_history:
                add_channel(channel)
        except Exception:
            continue
    return channels


async def collect_rebuild_records(ctx, *, target_user_id: int | None = None, per_channel_limit: int | None = None):
    limit = per_channel_limit if per_channel_limit and per_channel_limit > 0 else REBUILD_HISTORY_PER_CHANNEL
    records: list[dict[str, Any]] = []
    user_ids: set[int] = set()
    channels = _history_channels_for_ctx(ctx)
    guild = getattr(ctx, "guild", None)

    for channel in channels:
        try:
            async for message in channel.history(limit=limit, oldest_first=False):
                content = (getattr(message, "content", None) or "").strip()
                if not content or content.startswith(("!", "/")):
                    continue
                author = getattr(message, "author", None)
                if not author or getattr(author, "bot", False):
                    continue
                if target_user_id is not None and getattr(author, "id", 0) != target_user_id:
                    continue
                user_ids.add(author.id)
                logical_channel_id = author.id if guild is None else channel.id
                records.append(
                    {
                        "user_id": author.id,
                        "username": str(author),
                        "display_name": getattr(author, "display_name", None) or getattr(author, "name", "user"),
                        "channel_id": logical_channel_id,
                        "message_id": getattr(message, "id", 0),
                        "content": content,
                        "created_ts": float(message.created_at.timestamp()) if getattr(message, "created_at", None) else 0.0,
                    }
                )
        except Exception:
            continue

    records.sort(key=lambda item: (item["created_ts"], item["channel_id"], item["message_id"]))
    return records, {
        "channels_scanned": len(channels),
        "channel_ids": [getattr(channel, "id", 0) for channel in channels],
        "user_ids": sorted(user_ids),
        "messages_replayed": len(records),
        "limit_per_channel": limit,
    }
