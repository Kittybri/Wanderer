"""Bounded feature state in EXISTING bot/shared databases; never stores audio."""

from __future__ import annotations

import json
import time
import uuid
import aiosqlite

PREFERENCES = (
    "vc_party_features_enabled",
    "mockingbird_enabled",
    "interrogation_game_enabled",
    "escape_room_enabled",
    "voice_reactions_enabled",
)
SOCIAL_KINDS = {
    "playful_interruptions",
    "repeated_interruptions",
    "left_during_speech",
    "solved_escape",
    "interrogation_completed",
    "mockingbird_consent",
}


class SocialStore:
    def __init__(self, mem, bot_name):
        self.mem, self.name, self.ready = mem, bot_name, False

    async def init(self):
        if self.ready:
            return
        async with aiosqlite.connect(self.mem.db_path, timeout=15) as db:
            await db.execute("BEGIN IMMEDIATE")
            columns = {
                r[1]
                for r in await (
                    await db.execute("PRAGMA table_info(user_preferences)")
                ).fetchall()
            }
            for name in PREFERENCES:
                if name not in columns:
                    await db.execute(
                        f"ALTER TABLE user_preferences ADD COLUMN {name} INTEGER DEFAULT 0"
                    )
            await db.commit()
        async with aiosqlite.connect(self.mem.shared_db_path, timeout=15) as db:
            await db.executescript("""
                CREATE TABLE IF NOT EXISTS vc_social (
                    bot TEXT,user_id INTEGER,guild_id INTEGER,kind TEXT,ts REAL,
                    PRIMARY KEY(bot,user_id,guild_id,kind));
                CREATE TABLE IF NOT EXISTS vc_feature_budget (scope TEXT PRIMARY KEY,ts REAL);
                CREATE TABLE IF NOT EXISTS vc_games (
                    id TEXT PRIMARY KEY,bot TEXT,guild_id INTEGER,state TEXT,expires REAL,data TEXT);
                CREATE TABLE IF NOT EXISTS vc_presence (
                    bot TEXT,channel_id INTEGER,user_id INTEGER,ts REAL,
                    PRIMARY KEY(bot,channel_id,user_id));
                CREATE TABLE IF NOT EXISTS vc_duo_output (
                    bot TEXT,channel_id INTEGER,user_id INTEGER,content TEXT,ts REAL,
                    PRIMARY KEY(bot,channel_id,user_id));
            """)
            await db.execute("DELETE FROM vc_presence WHERE ts<?", (time.time() - 20,))
            await db.execute(
                "DELETE FROM vc_duo_output WHERE ts<?", (time.time() - 120,)
            )
            await db.execute(
                "DELETE FROM vc_social WHERE ts<?", (time.time() - 30 * 86400,)
            )
            await db.commit()
        self.ready = True

    async def preferences(self, uid):
        await self.init()
        async with aiosqlite.connect(self.mem.db_path, timeout=15) as db:
            row = await (
                await db.execute(
                    f"SELECT {','.join(PREFERENCES)} FROM user_preferences WHERE user_id=?",
                    (uid,),
                )
            ).fetchone()
        return {
            key: bool(row[i]) if row else False for i, key in enumerate(PREFERENCES)
        }

    async def preference(self, uid, name, enabled):
        if name not in PREFERENCES:
            raise ValueError("Unknown VC preference")
        await self.init()
        async with aiosqlite.connect(self.mem.db_path, timeout=15) as db:
            await db.execute(
                "INSERT OR IGNORE INTO user_preferences(user_id) VALUES (?)", (uid,)
            )
            await db.execute(
                f"UPDATE user_preferences SET {name}=? WHERE user_id=?",
                (int(bool(enabled)), uid),
            )
            await db.commit()
        if not enabled:
            await self.forget(uid)

    async def budget(self, guild, uid, feature, *, seconds=600, days=0, hourly=4):
        """Atomically reserve both a per-user cooldown and shared guild spacing."""
        await self.init()
        now = time.time()
        scopes = [
            (f"vc:user:{guild}:{uid}:{feature}", max(seconds, days * 86400)),
            (f"vc:guild:{guild}", 3600 / max(1, min(12, hourly))),
        ]
        async with aiosqlite.connect(self.mem.shared_db_path, timeout=15) as db:
            await db.execute("BEGIN IMMEDIATE")
            for scope, duration in scopes:
                row = await (
                    await db.execute(
                        "SELECT ts FROM vc_feature_budget WHERE scope=?", (scope,)
                    )
                ).fetchone()
                if row and now - row[0] < duration:
                    return False
            for scope, _ in scopes:
                await db.execute(
                    "INSERT OR REPLACE INTO vc_feature_budget VALUES (?,?)",
                    (scope, now),
                )
            await db.execute(
                "DELETE FROM vc_feature_budget WHERE ts<?", (now - 366 * 86400,)
            )
            await db.commit()
        return True

    async def remember(self, uid, gid, kind):
        if kind not in SOCIAL_KINDS:
            raise ValueError("Not an allowed compact social event")
        await self.init()
        async with aiosqlite.connect(self.mem.shared_db_path, timeout=15) as db:
            await db.execute(
                "INSERT OR REPLACE INTO vc_social VALUES (?,?,?,?,?)",
                (self.name, uid, gid, kind, time.time()),
            )
            await db.execute(
                "DELETE FROM vc_social WHERE ts<?", (time.time() - 30 * 86400,)
            )
            await db.commit()

    async def recall(self, uid, gid):
        await self.init()
        async with aiosqlite.connect(self.mem.shared_db_path, timeout=15) as db:
            rows = await (
                await db.execute(
                    "SELECT kind FROM vc_social WHERE bot=? AND user_id=? AND guild_id=? AND ts>? ORDER BY ts DESC LIMIT 4",
                    (self.name, uid, gid, time.time() - 30 * 86400),
                )
            ).fetchall()
        return [r[0] for r in rows]

    async def forget(self, uid):
        await self.init()
        async with aiosqlite.connect(self.mem.shared_db_path, timeout=15) as db:
            await db.execute(
                "DELETE FROM vc_social WHERE bot=? AND user_id=?", (self.name, uid)
            )
            await db.execute(
                "DELETE FROM vc_presence WHERE bot=? AND user_id=?", (self.name, uid)
            )
            await db.execute(
                "DELETE FROM vc_duo_output WHERE bot=? AND user_id=?", (self.name, uid)
            )
            await db.commit()

    async def create_game(self, gid, data, ttl):
        await self.init()
        game = dict(
            data,
            id=uuid.uuid4().hex[:16],
            bot=self.name,
            guild_id=gid,
            state="created",
            expires=time.time() + min(900, ttl),
            created=time.time(),
        )
        async with aiosqlite.connect(self.mem.shared_db_path, timeout=15) as db:
            await db.execute("BEGIN IMMEDIATE")
            row = await (
                await db.execute(
                    "SELECT COUNT(*) FROM vc_games WHERE guild_id=?",
                    (gid,),
                )
            ).fetchone()
            total = await (
                await db.execute(
                    "SELECT COUNT(*) FROM vc_games WHERE bot=?", (self.name,)
                )
            ).fetchone()
            if row[0] >= 1 or total[0] >= 25:
                raise ValueError("A game or cleanup is already pending")
            await db.execute(
                "INSERT INTO vc_games VALUES (?,?,?,?,?,?)",
                (
                    game["id"],
                    self.name,
                    gid,
                    game["state"],
                    game["expires"],
                    json.dumps(game),
                ),
            )
            await db.commit()
        return game

    async def save_game(self, game):
        async with aiosqlite.connect(self.mem.shared_db_path, timeout=15) as db:
            await db.execute(
                "UPDATE vc_games SET state=?,expires=?,data=? WHERE id=? AND bot=?",
                (
                    game["state"],
                    game["expires"],
                    json.dumps(game),
                    game["id"],
                    self.name,
                ),
            )
            await db.commit()

    async def games(self):
        await self.init()
        async with aiosqlite.connect(self.mem.shared_db_path, timeout=15) as db:
            rows = await (
                await db.execute(
                    "SELECT data FROM vc_games WHERE bot=? LIMIT 25", (self.name,)
                )
            ).fetchall()
        return [json.loads(r[0]) for r in rows]

    async def delete_game(self, gid):
        async with aiosqlite.connect(self.mem.shared_db_path, timeout=15) as db:
            await db.execute(
                "DELETE FROM vc_games WHERE id=? AND bot=?", (gid, self.name)
            )
            await db.commit()

    async def presence(self, channel, participants):
        await self.init()
        async with aiosqlite.connect(self.mem.shared_db_path, timeout=15) as db:
            await db.execute(
                "DELETE FROM vc_presence WHERE bot=? AND channel_id=?",
                (self.name, channel),
            )
            for uid in list(participants)[:8]:
                await db.execute(
                    "INSERT INTO vc_presence VALUES (?,?,?,?)",
                    (self.name, channel, uid, time.time()),
                )
            await db.execute("DELETE FROM vc_presence WHERE ts<?", (time.time() - 20,))
            await db.execute(
                "DELETE FROM vc_duo_output WHERE ts<?", (time.time() - 120,)
            )
            await db.commit()

    async def duo_output(self, channel, uid, text=None, partner=None):
        async with aiosqlite.connect(self.mem.shared_db_path, timeout=15) as db:
            if text is not None:
                await db.execute(
                    "INSERT OR REPLACE INTO vc_duo_output VALUES (?,?,?,?,?)",
                    (self.name, channel, uid, text[:600], time.time()),
                )
                await db.commit()
                return ""
            row = await (
                await db.execute(
                    "SELECT content FROM vc_duo_output WHERE bot=? AND channel_id=? AND user_id=? AND ts>?",
                    (partner, channel, uid, time.time() - 120),
                )
            ).fetchone()
            return row[0] if row else ""

    async def partner_ready(self, partner, channel, uid):
        await self.init()
        async with aiosqlite.connect(self.mem.shared_db_path, timeout=15) as db:
            row = await (
                await db.execute(
                    "SELECT ts FROM vc_presence WHERE bot=? AND channel_id=? AND user_id=?",
                    (partner, channel, uid),
                )
            ).fetchone()
        return bool(row and time.time() - row[0] < 15)

    async def claim_duo(self, channel):
        """Claim an existing coordinator turn, not an independent dialogue queue."""
        async with aiosqlite.connect(self.mem.shared_db_path, timeout=15) as db:
            await db.execute("BEGIN IMMEDIATE")
            row = await (
                await db.execute(
                    "SELECT mode,topic,initiator_user_id,autoplay_remaining FROM duo_sessions WHERE channel_id=? AND awaiting_bot=? AND mode LIKE 'vc:%' AND next_autoplay_ts<=? AND expires_ts>? AND autoplay_remaining>0",
                    (channel, self.name, time.time(), time.time()),
                )
            ).fetchone()
            if not row:
                return None
            await db.execute(
                "UPDATE duo_sessions SET next_autoplay_ts=? WHERE channel_id=?",
                (time.time() + 90, channel),
            )
            await db.commit()
        return dict(mode=row[0], topic=row[1], user_id=row[2], remaining=row[3])
