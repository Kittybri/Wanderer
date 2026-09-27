"""Opt-in, single-listener ambient playback using Discord's current audio interface."""
from __future__ import annotations
import asyncio
import os
import time
from zoneinfo import ZoneInfo
import discord

def eligible(user, member, channel, now, config):
    if not user or not user.get("lullaby_enabled") or not user.get("voice_enabled", True) or not user.get("proactive", True):
        return False
    if int(user.get("affection", 0)) < int(config.get("min_affection", 75)):
        return False
    if str(member.status) not in ("online", "idle") or now.timestamp()-float(user.get("last_active",0)) > 1800:
        return False
    hour = now.astimezone(ZoneInfo(user.get("timezone_name") or "UTC")).hour
    start = max(20,min(23,int(user.get("lullaby_start_hour",23))))
    if not (hour >= start or hour < 3):
        return False
    # This explicit opt-in is the only quiet-hours exception. Never join a group.
    if len(channel.members) != 1 or channel.members[0].id != member.id or channel.guild.voice_client:
        return False
    p = channel.permissions_for(channel.guild.me)
    return bool(p.view_channel and p.connect and p.speak)

async def playback(channel, path, duration=180, final_line=None):
    voice = None
    source = None
    listener_ids = {getattr(m,"id",None) for m in channel.members if not m.bot}
    def same_listener():
        return (len(channel.members)==2 and
                {getattr(m,"id",None) for m in channel.members if not m.bot} == listener_ids)
    try:
        voice = await channel.connect(timeout=15, reconnect=False, self_deaf=True)
        source = discord.FFmpegPCMAudio(path, options=f"-t {max(1,min(300,int(duration)))}")
        voice.play(source)
        deadline = time.monotonic()+max(1,min(300,int(duration)))
        while voice.is_playing() and time.monotonic()<deadline:
            # Abort immediately if somebody joins or the listener leaves.
            if not same_listener():
                break
            await asyncio.sleep(1)
        voice.stop()
        if final_line and same_listener():
            await asyncio.wait_for(final_line(voice),20)
    finally:
        if voice:
            voice.stop()
        if source:
            source.cleanup()
        if voice:
            await voice.disconnect(force=True)

async def lullaby_tick(bot, mem, store, config, now, final_line=None):
    path = config.get("ambient_path","")
    if not config.get("enabled") or not os.path.isfile(path):
        return
    for cid in config.get("channel_ids",[])[:10]:
        channel = bot.get_channel(int(cid))
        if not isinstance(channel, discord.VoiceChannel) or len(channel.members)!=1:
            continue
        member = channel.members[0]
        if member.bot:
            continue
        user = await mem.get_user(member.id)
        if not eligible(user,member,channel,now,config):
            continue
        if await mem.get_duo_session(channel.id):
            continue
        key = f"lullaby:{member.id}"
        receipt = await store.get(key)
        cooldown = max(86400,int(config.get("cooldown_seconds",604800)))
        if receipt and now.timestamp()-receipt.get("timestamp",0)<cooldown:
            continue
        # Shared claim serializes multiple instances and reconnects for this night.
        day_key = key+":"+now.astimezone(ZoneInfo(user.get("timezone_name") or "UTC")).strftime("%Y-%m-%d")
        if not await store.claim(day_key,"lullaby_attempt"):
            continue
        await store.put(key,"lullaby_cooldown",{"timestamp":now.timestamp()})
        await playback(channel,path,config.get("duration_seconds",180),final_line)
        return
