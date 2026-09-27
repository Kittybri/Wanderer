"""Birthday decorations with durable write-ahead restoration records."""
from __future__ import annotations
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import discord

def birthday_window(now, timezone_name):
    local = now.astimezone(ZoneInfo(timezone_name))
    return local.month == 1 and local.day == 3, local

async def restore_decorations(bot, store, now):
    for key, record in await store.recent("birthday_restore",100,oldest=True):
        if record["restore_at"] > now.timestamp():
            continue
        guild = bot.get_guild(record["guild_id"])
        if not guild:
            await store.put(key,"birthday_restore",record)
            continue
        obj = guild.get_channel(record["object_id"]) if record["type"]=="channel" else guild.get_role(record["object_id"])
        if obj is None:
            # Missing cache/permissions is not proof of deletion; preserve originals.
            await store.put(key,"birthday_restore",record)
            continue
        # Respect a subsequent administrator edit.
        if obj.name == record["temporary"]:
            try:
                await obj.edit(name=record["original"],reason="Restore temporary birthday decoration")
            except discord.HTTPException:
                await store.put(key,"birthday_restore",record)
                continue
        await store.remove(key)

async def run_birthday(bot, store, config, now):
    await restore_decorations(bot,store,now)
    for guild_key, settings in list(config.get("guilds",{}).items())[:20]:
        guild = bot.get_guild(int(guild_key))
        if not guild or not settings.get("enabled"):
            continue
        active, local = birthday_window(now,settings.get("timezone","UTC"))
        if not active:
            continue
        channel = guild.get_channel(int(settings.get("channel_id") or 0))
        if not channel:
            continue
        key = f"birthday:{guild.id}:{local.year}"
        if await store.claim(key,"birthday",{"guild_id":guild.id,"year":local.year}):
            try:
                await channel.send("January third. My birthday. A few well-chosen words will do for tribute.",
                                   allowed_mentions=discord.AllowedMentions.none())
            except discord.HTTPException:
                # Receipt intentionally prevents reconnect spam after ambiguous sends.
                pass
        if not settings.get("decorations_enabled"):
            continue
        end = (local+timedelta(days=1)).replace(hour=0,minute=0,second=0,microsecond=0).timestamp()
        for kind, objects in (("channel",settings.get("channels",{})),("role",settings.get("roles",{}))):
            for object_id, temporary in list(objects.items())[:10]:
                obj = guild.get_channel(int(object_id)) if kind=="channel" else guild.get_role(int(object_id))
                if not obj or (kind=="role" and (obj.is_default() or obj.managed or obj>=guild.me.top_role)):
                    continue
                permission = guild.me.guild_permissions.manage_channels if kind=="channel" else guild.me.guild_permissions.manage_roles
                if not permission:
                    continue
                receipt = f"decoration:{guild.id}:{kind}:{object_id}:{local.year}"
                restore_key = "restore:"+receipt
                record = {"guild_id":guild.id,"object_id":int(object_id),"type":kind,
                          "original":obj.name,"temporary":str(temporary)[:90],"restore_at":end}
                if await store.get(receipt) is not None:
                    continue
                # Both writes precede the Discord edit; cancellation cannot lose originals.
                if not await store.claim(restore_key,"birthday_restore",record):
                    continue
                await store.claim(receipt,"birthday_decoration",{})
                try:
                    await obj.edit(name=record["temporary"],reason="Opt-in birthday decoration")
                except discord.HTTPException:
                    pass
