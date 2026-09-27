"""Private, user-scoped face commands with delete-versus-enrollment race protection."""
from __future__ import annotations
import asyncio
import json
import time
import discord
from discord.ext import commands
from world_store import WorldStore
from face_memory import BACKEND, enroll_face_profile, match_face

class FaceProfiles(WorldStore):
    async def init(self):
        async with self.connect() as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.executescript("""
                CREATE TABLE IF NOT EXISTS face_profiles(
                  profile_key TEXT PRIMARY KEY, owner_user_id INTEGER,
                  label TEXT, profile_json TEXT, updated_ts REAL);
                CREATE TABLE IF NOT EXISTS face_consent_generation(
                  user_id INTEGER PRIMARY KEY, generation INTEGER NOT NULL DEFAULT 0);
                CREATE INDEX IF NOT EXISTS idx_face_owner ON face_profiles(owner_user_id);
            """)
            await db.commit()

    async def snapshot(self,uid):
        async with self.connect() as db:
            await db.execute("INSERT OR IGNORE INTO face_consent_generation(user_id) VALUES(?)",(uid,))
            await db.commit()
            generation=await (await db.execute("SELECT generation FROM face_consent_generation WHERE user_id=?",(uid,))).fetchone()
            row=await (await db.execute("SELECT profile_json FROM face_profiles WHERE profile_key=? AND owner_user_id=?",(f"user:{uid}",uid))).fetchone()
            if not row:
                row=await (await db.execute("SELECT profile_json FROM face_profiles WHERE profile_key='owner_face' AND owner_user_id=?",(uid,))).fetchone()
        try:
            profile=json.loads(row[0]) if row else None
            if profile is not None and not isinstance(profile,dict):
                profile={}
        except (ValueError,TypeError):
            profile={}
        return generation[0],profile

    async def save(self,uid,generation,profile):
        async with self.connect() as db:
            await db.execute("BEGIN IMMEDIATE")
            row=await (await db.execute("SELECT generation FROM face_consent_generation WHERE user_id=?",(uid,))).fetchone()
            if not row or row[0]!=generation:
                return False
            await db.execute("INSERT INTO face_profiles VALUES(?,?,?,?,?) ON CONFLICT(profile_key) DO UPDATE SET profile_json=excluded.profile_json,updated_ts=excluded.updated_ts",
                             (f"user:{uid}",uid,"",json.dumps(profile),time.time()))
            await db.execute("UPDATE face_consent_generation SET generation=generation+1 WHERE user_id=?",(uid,))
            # Successfully re-enrolled owner templates replace the legacy version.
            await db.execute("DELETE FROM face_profiles WHERE profile_key='owner_face' AND owner_user_id=?",(uid,))
            await db.commit()
        return True

    async def delete(self,uid):
        async with self.connect() as db:
            await db.execute("BEGIN IMMEDIATE")
            await db.execute("INSERT INTO face_consent_generation VALUES(?,1) ON CONFLICT(user_id) DO UPDATE SET generation=generation+1",(uid,))
            await db.execute("DELETE FROM face_profiles WHERE owner_user_id=?",(uid,))
            await db.commit()

def install_face_commands(bot,path):
    profiles=FaceProfiles(path)
    # Replace old owner-only commands, including aliases, without duplicate registration.
    for name in ("enrollface","faceinfo","deleteface","recognizeface"):
        bot.remove_command(name)

    async def say(ctx,text):
        await ctx.reply(text,mention_author=False,allowed_mentions=discord.AllowedMentions.none())

    async def private(ctx):
        if ctx.guild:
            await say(ctx,"Use these face-memory commands in a DM with me. Only enroll your own face with your consent.")
            return False
        await profiles.init()
        return True

    async def data(ctx):
        attachments=ctx.message.attachments
        if len(attachments)!=1:
            await say(ctx,"Attach one clear image of only yourself. No raw photos are retained by this feature; Discord still hosts your attachment.")
            return None
        attachment=attachments[0]
        if attachment.size>8*1024*1024 or not (attachment.content_type or "").startswith("image/"):
            await say(ctx,"Use an image smaller than 8 MB.")
            return None
        return await asyncio.wait_for(attachment.read(),15)

    @bot.command(name="enrollface",aliases=["rememberface","reenrollface"])
    @commands.cooldown(1,20,commands.BucketType.user)
    @commands.max_concurrency(2,per=commands.BucketType.default,wait=False)
    async def enroll(ctx):
        if not await private(ctx):
            return
        image=await data(ctx)
        if image is None:
            return
        generation,profile=await profiles.snapshot(ctx.author.id)
        result=await asyncio.to_thread(enroll_face_profile,profile,image)
        if not result.get("ok"):
            await say(ctx,"Enrollment skipped: "+result.get("reason","unknown")+". No template was saved.")
            return
        saved=await profiles.save(ctx.author.id,generation,result["profile"])
        await say(ctx,f"Enrolled {result['sample_count']} sample(s). Add different lighting/angles with !enrollface. Use !deleteface to remove them."
                  if saved else "Your face-memory settings changed during enrollment. Nothing was saved; retry if intended.")

    @bot.command(name="faceinfo",aliases=["facestatus"])
    async def status(ctx):
        if not await private(ctx):
            return
        _,profile=await profiles.snapshot(ctx.author.id)
        message="No enrolled template."
        if profile is not None:
            message=(f"Local {BACKEND}: {profile.get('sample_count',0)} samples; explicit matching only."
                     if profile.get("backend")==BACKEND else "Legacy/incompatible template: use !enrollface to replace it or !deleteface.")
        await say(ctx,message)

    @bot.command(name="deleteface",aliases=["forgetface"])
    async def delete(ctx):
        if not await private(ctx):
            return
        await profiles.delete(ctx.author.id)
        await say(ctx,"Your active face templates are deleted. Your Discord uploads and administrator backups are separate; remove those separately if needed.")

    @bot.command(name="recognizeface")
    @commands.cooldown(1,20,commands.BucketType.user)
    @commands.max_concurrency(2,per=commands.BucketType.default,wait=False)
    async def recognize(ctx):
        if not await private(ctx):
            return
        image=await data(ctx)
        if image is None:
            return
        _,profile=await profiles.snapshot(ctx.author.id)
        result=await asyncio.to_thread(match_face,image,profile)
        if result.get("ok"):
            await say(ctx,f"Result: {result['status']}. Similarity {result['score']:.3f}; threshold {result['threshold']:.3f}. This is an estimate, not identity verification.")
        else:
            await say(ctx,"Recognition skipped: "+result.get("reason","unknown")+".")
    return profiles
