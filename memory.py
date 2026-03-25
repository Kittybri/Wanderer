"""
memory.py — Scaramouche Bot v6
Full persistence: mood, affection, trust, grudges, rivalry, milestones,
inside jokes, absence tracking, anniversaries, slow burn, personality drift,
memory summaries, muted users, contradiction tracking, name progression.
"""

import aiosqlite
import time
import json
import os

# Use Railway volume if available, otherwise current directory
_data_dir = "/data" if os.path.isdir("/data") else "."
DB_PATH = os.path.join(_data_dir, "scaramouche.db")


class Memory:
    # In-memory only (resets on restart — intentional for mute)
    _muted: dict[int, float] = {}
    db_path: str = DB_PATH

    async def init(self):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id          INTEGER PRIMARY KEY,
                    username         TEXT,
                    display_name     TEXT,
                    romance_mode     INTEGER DEFAULT 0,
                    nsfw_mode        INTEGER DEFAULT 0,
                    proactive        INTEGER DEFAULT 1,
                    allow_dms        INTEGER DEFAULT 1,
                    mood             INTEGER DEFAULT 0,
                    affection        INTEGER DEFAULT 0,
                    trust            INTEGER DEFAULT 0,
                    rival_id         INTEGER DEFAULT NULL,
                    grudge_nick      TEXT    DEFAULT NULL,
                    affection_nick   TEXT    DEFAULT NULL,
                    message_count    INTEGER DEFAULT 0,
                    milestone_last   INTEGER DEFAULT 0,
                    first_seen       REAL    DEFAULT 0,
                    last_seen        REAL    DEFAULT 0,
                    last_active      REAL    DEFAULT 0,
                    greeted_today    INTEGER DEFAULT 0,
                    anniversary_last INTEGER DEFAULT 0,
                    slow_burn        INTEGER DEFAULT 0,
                    slow_burn_day    INTEGER DEFAULT 0,
                    slow_burn_fired  INTEGER DEFAULT 0,
                    drift_score      INTEGER DEFAULT 0,
                    memory_summary   TEXT    DEFAULT NULL,
                    summary_msg_count INTEGER DEFAULT 0,
                    last_statement   TEXT    DEFAULT NULL
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id     INTEGER,
                    channel_id  INTEGER,
                    role        TEXT,
                    content     TEXT,
                    ts          REAL
                );
                CREATE TABLE IF NOT EXISTS channels (
                    channel_id  INTEGER PRIMARY KEY,
                    guild_id    INTEGER,
                    last_active REAL
                );
                CREATE TABLE IF NOT EXISTS proactive_cooldown (
                    channel_id  INTEGER PRIMARY KEY,
                    last_sent   REAL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS dm_cooldown (
                    user_id   INTEGER PRIMARY KEY,
                    last_sent REAL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS reminders (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id     INTEGER,
                    channel_id  INTEGER,
                    reminder    TEXT,
                    due_ts      REAL,
                    done        INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS inside_jokes (
                    id      INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    joke    TEXT,
                    ts      REAL
                );
                CREATE TABLE IF NOT EXISTS lore_cooldown (
                    channel_id  INTEGER PRIMARY KEY,
                    last_sent   REAL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS starter_cooldown (
                    channel_id  INTEGER PRIMARY KEY,
                    last_sent   REAL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS trivia (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id     INTEGER,
                    correct     INTEGER DEFAULT 0,
                    wrong       INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS roast_battles (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id  INTEGER,
                    user1_id    INTEGER,
                    user2_id    INTEGER,
                    round       INTEGER DEFAULT 0,
                    scores      TEXT    DEFAULT '{}',
                    active      INTEGER DEFAULT 1,
                    ts          REAL
                );
            """)
            migrations = [
                ("allow_dms",          "INTEGER DEFAULT 1"),
                ("mood",               "INTEGER DEFAULT 0"),
                ("affection",          "INTEGER DEFAULT 0"),
                ("trust",              "INTEGER DEFAULT 0"),
                ("rival_id",           "INTEGER DEFAULT NULL"),
                ("grudge_nick",        "TEXT DEFAULT NULL"),
                ("affection_nick",     "TEXT DEFAULT NULL"),
                ("message_count",      "INTEGER DEFAULT 0"),
                ("milestone_last",     "INTEGER DEFAULT 0"),
                ("first_seen",         "REAL DEFAULT 0"),
                ("last_active",        "REAL DEFAULT 0"),
                ("greeted_today",      "INTEGER DEFAULT 0"),
                ("anniversary_last",   "INTEGER DEFAULT 0"),
                ("slow_burn",          "INTEGER DEFAULT 0"),
                ("slow_burn_day",      "INTEGER DEFAULT 0"),
                ("slow_burn_fired",    "INTEGER DEFAULT 0"),
                ("drift_score",        "INTEGER DEFAULT 0"),
                ("memory_summary",     "TEXT DEFAULT NULL"),
                ("summary_msg_count",  "INTEGER DEFAULT 0"),
                ("last_statement",     "TEXT DEFAULT NULL"),
            ]
            for col, default in migrations:
                try:
                    await db.execute(f"ALTER TABLE users ADD COLUMN {col} {default}")
                except Exception:
                    pass
            await db.commit()

    # ── Users ────────────────────────────────────────────────────────────────
    async def upsert_user(self, user_id: int, username: str, display_name: str):
        now = time.time()
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT first_seen FROM users WHERE user_id=?", (user_id,)) as cur:
                row = await cur.fetchone()
            if row:
                await db.execute(
                    "UPDATE users SET username=?,display_name=?,last_seen=?,last_active=? WHERE user_id=?",
                    (username, display_name, now, now, user_id))
            else:
                await db.execute(
                    "INSERT INTO users (user_id,username,display_name,last_seen,last_active,first_seen) VALUES (?,?,?,?,?,?)",
                    (user_id, username, display_name, now, now, now))
            await db.commit()

    async def get_user(self, user_id: int) -> dict | None:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("""
                SELECT user_id,username,display_name,romance_mode,nsfw_mode,proactive,allow_dms,
                       mood,affection,trust,rival_id,grudge_nick,affection_nick,message_count,
                       milestone_last,first_seen,last_seen,last_active,greeted_today,anniversary_last,
                       slow_burn,slow_burn_fired,drift_score,memory_summary,last_statement
                FROM users WHERE user_id=?
            """, (user_id,)) as cur:
                row = await cur.fetchone()
                if not row: return None
                return {
                    "user_id": row[0], "username": row[1], "display_name": row[2],
                    "romance_mode": bool(row[3]), "nsfw_mode": bool(row[4]),
                    "proactive": bool(row[5]), "allow_dms": bool(row[6]),
                    "mood": row[7] or 0, "affection": row[8] or 0, "trust": row[9] or 0,
                    "rival_id": row[10], "grudge_nick": row[11], "affection_nick": row[12],
                    "message_count": row[13] or 0, "milestone_last": row[14] or 0,
                    "first_seen": row[15] or 0, "last_seen": row[16] or 0,
                    "last_active": row[17] or 0, "greeted_today": bool(row[18]),
                    "anniversary_last": row[19] or 0,
                    "slow_burn": row[20] or 0, "slow_burn_fired": bool(row[21]),
                    "drift_score": row[22] or 0, "memory_summary": row[23],
                    "last_statement": row[24],
                }

    async def set_mode(self, user_id: int, field: str, value: bool):
        allowed = {"nsfw_mode","romance_mode","proactive","allow_dms"}
        if field not in allowed: raise ValueError(f"Unknown: {field}")
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(f"UPDATE users SET {field}=? WHERE user_id=?", (int(value), user_id))
            await db.commit()

    # ── Mood ─────────────────────────────────────────────────────────────────
    async def update_mood(self, user_id: int, delta: int):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE users SET mood=MAX(-10,MIN(10,mood+?)) WHERE user_id=?", (delta, user_id))
            await db.commit()

    async def get_mood(self, user_id: int) -> int:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT mood FROM users WHERE user_id=?", (user_id,)) as cur:
                row = await cur.fetchone(); return row[0] if row else 0

    async def random_mood_swing(self, user_id: int):
        """Randomly shift mood slightly — unpredictable personality."""
        delta = random.choice([-3, -2, -1, -1, 0, 0, 1, 2])
        await self.update_mood(user_id, delta)

    # ── Affection ─────────────────────────────────────────────────────────────
    async def update_affection(self, user_id: int, delta: int):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE users SET affection=MAX(0,MIN(100,affection+?)) WHERE user_id=?", (delta, user_id))
            await db.commit()

    async def set_affection_nick(self, user_id: int, nick: str):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE users SET affection_nick=? WHERE user_id=?", (nick, user_id))
            await db.commit()

    # ── Trust ─────────────────────────────────────────────────────────────────
    async def update_trust(self, user_id: int, delta: int):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE users SET trust=MAX(0,MIN(100,trust+?)) WHERE user_id=?", (delta, user_id))
            await db.commit()

    # ── Grudge ────────────────────────────────────────────────────────────────
    async def set_grudge_nick(self, user_id: int, nick: str | None):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE users SET grudge_nick=? WHERE user_id=?", (nick, user_id))
            await db.commit()

    # ── Rivalry ───────────────────────────────────────────────────────────────
    async def set_rival(self, user_id: int, rival_id: int | None):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE users SET rival_id=? WHERE user_id=?", (rival_id, user_id))
            await db.commit()

    # ── Slow burn ─────────────────────────────────────────────────────────────
    async def increment_slow_burn(self, user_id: int) -> tuple[int, bool]:
        """
        Increment slow burn if user was kind today and hasn't been incremented yet today.
        Returns (new_score, threshold_hit).
        Threshold is 7 consecutive kind days.
        """
        today = int(time.time() // 86400)
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT slow_burn, slow_burn_day, slow_burn_fired FROM users WHERE user_id=?",
                (user_id,)
            ) as cur:
                row = await cur.fetchone()
                if not row: return 0, False
                score, last_day, fired = row[0] or 0, row[1] or 0, bool(row[2])

            if last_day == today:
                return score, False  # Already counted today

            # If last kind day was yesterday, continue streak; else reset
            if today - last_day <= 1:
                new_score = score + 1
            else:
                new_score = 1  # Reset streak

            await db.execute(
                "UPDATE users SET slow_burn=?, slow_burn_day=? WHERE user_id=?",
                (new_score, today, user_id))
            await db.commit()

        # Threshold: 7 consecutive kind days, hasn't fired yet
        if new_score >= 7 and not fired:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("UPDATE users SET slow_burn_fired=1 WHERE user_id=?", (user_id,))
                await db.commit()
            return new_score, True
        return new_score, False

    async def reset_slow_burn_fired(self, user_id: int):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE users SET slow_burn=0, slow_burn_fired=0 WHERE user_id=?", (user_id,))
            await db.commit()

    # ── Personality drift ─────────────────────────────────────────────────────
    async def update_drift(self, user_id: int, delta: int):
        """Drift: 0=unchanged, 100=maximally drifted. Changes subtly over weeks."""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE users SET drift_score=MAX(0,MIN(100,drift_score+?)) WHERE user_id=?", (delta, user_id))
            await db.commit()

    # ── Memory summary ────────────────────────────────────────────────────────
    async def needs_summary(self, user_id: int) -> bool:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT message_count, summary_msg_count FROM users WHERE user_id=?", (user_id,)
            ) as cur:
                row = await cur.fetchone()
                if not row: return False
                count, last = row[0] or 0, row[1] or 0
                return count >= 80 and (count - last) >= 50

    async def save_summary(self, user_id: int, summary: str):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT message_count FROM users WHERE user_id=?", (user_id,)) as cur:
                row = await cur.fetchone(); count = row[0] if row else 0
            await db.execute(
                "UPDATE users SET memory_summary=?, summary_msg_count=? WHERE user_id=?",
                (summary[:1000], count, user_id))
            await db.commit()

    # ── Contradiction tracking ────────────────────────────────────────────────
    async def update_last_statement(self, user_id: int, statement: str):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE users SET last_statement=? WHERE user_id=?", (statement[:300], user_id))
            await db.commit()

    # ── Message count & milestones ────────────────────────────────────────────
    async def increment_message_count(self, user_id: int) -> tuple[int, bool]:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE users SET message_count=message_count+1 WHERE user_id=?", (user_id,))
            await db.commit()
            async with db.execute("SELECT message_count,milestone_last FROM users WHERE user_id=?", (user_id,)) as cur:
                row = await cur.fetchone()
                if not row: return 1, False
                count, last = row
        for m in [50,100,250,500,1000]:
            if count >= m and last < m:
                async with aiosqlite.connect(DB_PATH) as db:
                    await db.execute("UPDATE users SET milestone_last=? WHERE user_id=?", (m, user_id))
                    await db.commit()
                return count, True
        return count, False

    async def get_top_users(self, limit: int = 8) -> list[dict]:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT user_id,display_name,message_count FROM users ORDER BY message_count DESC LIMIT ?", (limit,)
            ) as cur:
                rows = await cur.fetchall()
        return [{"user_id":r[0],"display_name":r[1],"message_count":r[2]} for r in rows]

    # ── Greetings ─────────────────────────────────────────────────────────────
    async def should_greet(self, user_id: int) -> bool:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT greeted_today,last_active FROM users WHERE user_id=?", (user_id,)) as cur:
                row = await cur.fetchone()
                if not row: return False
                return not row[0] and (time.time() - (row[1] or 0)) < 172800

    async def mark_greeted(self, user_id: int):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE users SET greeted_today=1 WHERE user_id=?", (user_id,))
            await db.commit()

    async def reset_daily_greetings(self):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE users SET greeted_today=0"); await db.commit()

    # ── Anniversary ───────────────────────────────────────────────────────────
    async def check_anniversary(self, user_id: int) -> bool:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT first_seen,anniversary_last,message_count FROM users WHERE user_id=?", (user_id,)
            ) as cur:
                row = await cur.fetchone()
                if not row: return False
                first, ann_last, count = row
                if count < 10 or not first: return False
                days = (time.time()-first)/86400
                if days < 30: return False
                years = int(days/365.25)
                if years == 0: return False
                ann_ts = first + years*365.25*86400
                return abs(time.time()-ann_ts)<172800 and (time.time()-(ann_last or 0))>365.25*86400*0.9

    async def mark_anniversary(self, user_id: int):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE users SET anniversary_last=? WHERE user_id=?", (time.time(), user_id))
            await db.commit()

    # ── Absence ───────────────────────────────────────────────────────────────
    async def get_absent_romance_users(self, days: float = 3.0) -> list[dict]:
        cutoff = time.time() - days*86400
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("""
                SELECT user_id,display_name,last_active,
                       (julianday('now')-julianday(datetime(last_active,'unixepoch'))) as days_gone
                FROM users WHERE romance_mode=1 AND allow_dms=1
                  AND last_active>0 AND last_active<? AND message_count>5
            """, (cutoff,)) as cur:
                rows = await cur.fetchall()
        return [{"user_id":r[0],"display_name":r[1],"last_active":r[2],"days_gone":round(r[3] or 0,1)} for r in rows]

    # ── Inside jokes ─────────────────────────────────────────────────────────
    async def add_inside_joke(self, user_id: int, joke: str):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT COUNT(*) FROM inside_jokes WHERE user_id=?", (user_id,)) as cur:
                count = (await cur.fetchone())[0]
            if count >= 10:
                await db.execute("DELETE FROM inside_jokes WHERE id=(SELECT id FROM inside_jokes WHERE user_id=? ORDER BY ts ASC LIMIT 1)", (user_id,))
            await db.execute("INSERT INTO inside_jokes (user_id,joke,ts) VALUES (?,?,?)", (user_id,joke[:200],time.time()))
            await db.commit()

    async def get_random_inside_joke(self, user_id: int) -> str | None:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT joke FROM inside_jokes WHERE user_id=? ORDER BY RANDOM() LIMIT 1", (user_id,)) as cur:
                row = await cur.fetchone(); return row[0] if row else None

    async def get_joke_count(self, user_id: int) -> int:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT COUNT(*) FROM inside_jokes WHERE user_id=?", (user_id,)) as cur:
                return (await cur.fetchone())[0]

    # ── Conversation history ──────────────────────────────────────────────────
    async def get_history(self, user_id: int, channel_id: int, limit: int = 35) -> list[dict]:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("""
                SELECT role,content FROM messages WHERE user_id=? AND channel_id=?
                ORDER BY ts DESC LIMIT ?
            """, (user_id,channel_id,limit)) as cur:
                rows = await cur.fetchall()
        return [{"role":r[0],"content":r[1]} for r in reversed(rows)]

    async def get_random_old_message(self, user_id: int) -> str | None:
        cutoff = time.time()-86400*2
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT content FROM messages WHERE user_id=? AND role='user' AND ts<? ORDER BY RANDOM() LIMIT 1", (user_id,cutoff)) as cur:
                row = await cur.fetchone(); return row[0] if row else None

    async def get_recent_messages(self, user_id: int, limit: int = 10) -> list[str]:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT content FROM messages WHERE user_id=? AND role='user' ORDER BY ts DESC LIMIT ?", (user_id,limit)) as cur:
                return [r[0] for r in await cur.fetchall()]

    async def get_channel_recent(self, channel_id: int, limit: int = 20) -> list[dict]:
        """Get recent messages from all users in a channel."""
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("""
                SELECT m.role, m.content, u.display_name FROM messages m
                LEFT JOIN users u ON m.user_id=u.user_id
                WHERE m.channel_id=? ORDER BY m.ts DESC LIMIT ?
            """, (channel_id,limit)) as cur:
                rows = await cur.fetchall()
        return [{"role":r[0],"content":r[1],"name":r[2] or "?"} for r in reversed(rows)]

    async def add_message(self, user_id: int, channel_id: int, role: str, content: str):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT INTO messages (user_id,channel_id,role,content,ts) VALUES (?,?,?,?,?)", (user_id,channel_id,role,content,time.time()))
            await db.commit()

    async def reset_user(self, user_id: int):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM messages WHERE user_id=?", (user_id,))
            await db.execute("DELETE FROM inside_jokes WHERE user_id=?", (user_id,))
            await db.execute("""UPDATE users SET mood=0,affection=0,trust=0,rival_id=NULL,grudge_nick=NULL,
                affection_nick=NULL,message_count=0,milestone_last=0,slow_burn=0,slow_burn_fired=0,
                drift_score=0,memory_summary=NULL,last_statement=NULL WHERE user_id=?""", (user_id,))
            await db.commit()

    # ── Mute (in-memory) ──────────────────────────────────────────────────────
    def mute_user(self, user_id: int, seconds: int = 600):
        Memory._muted[user_id] = time.time() + seconds

    def is_muted(self, user_id: int) -> bool:
        exp = Memory._muted.get(user_id, 0)
        if exp and time.time() > exp:
            del Memory._muted[user_id]; return False
        return bool(exp)

    def unmute_user(self, user_id: int):
        Memory._muted.pop(user_id, None)

    # ── Trivia ────────────────────────────────────────────────────────────────
    async def update_trivia(self, user_id: int, correct: bool):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT id FROM trivia WHERE user_id=?", (user_id,)) as cur:
                row = await cur.fetchone()
            if row:
                col = "correct" if correct else "wrong"
                await db.execute(f"UPDATE trivia SET {col}={col}+1 WHERE user_id=?", (user_id,))
            else:
                await db.execute("INSERT INTO trivia (user_id,correct,wrong) VALUES (?,?,?)",
                                 (user_id, 1 if correct else 0, 0 if correct else 1))
            await db.commit()

    # ── Roast battles ─────────────────────────────────────────────────────────
    async def start_roast_battle(self, channel_id: int, u1: int, u2: int) -> int:
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(
                "INSERT INTO roast_battles (channel_id,user1_id,user2_id,round,scores,active,ts) VALUES (?,?,?,0,'{}',1,?)",
                (channel_id,u1,u2,time.time()))
            await db.commit()
            return cur.lastrowid

    async def get_active_roast(self, channel_id: int) -> dict | None:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT id,user1_id,user2_id,round,scores FROM roast_battles WHERE channel_id=? AND active=1", (channel_id,)
            ) as cur:
                row = await cur.fetchone()
                if not row: return None
                return {"id":row[0],"user1":row[1],"user2":row[2],"round":row[3],"scores":json.loads(row[4])}

    async def end_roast_battle(self, battle_id: int):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE roast_battles SET active=0 WHERE id=?", (battle_id,))
            await db.commit()

    async def increment_roast_round(self, battle_id: int):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE roast_battles SET round=round+1 WHERE id=?", (battle_id,))
            await db.commit()

    # ── Reminders ─────────────────────────────────────────────────────────────
    async def add_reminder(self, user_id: int, channel_id: int, reminder: str, due_ts: float):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT INTO reminders (user_id,channel_id,reminder,due_ts) VALUES (?,?,?,?)", (user_id,channel_id,reminder,due_ts))
            await db.commit()

    async def get_due_reminders(self) -> list[dict]:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT id,user_id,channel_id,reminder FROM reminders WHERE due_ts<=? AND done=0", (time.time(),)) as cur:
                rows = await cur.fetchall()
            if rows:
                await db.execute(f"UPDATE reminders SET done=1 WHERE id IN ({','.join('?'*len(rows))})", [r[0] for r in rows])
                await db.commit()
        return [{"id":r[0],"user_id":r[1],"channel_id":r[2],"reminder":r[3]} for r in rows]

    # ── Channels ──────────────────────────────────────────────────────────────
    async def track_channel(self, channel_id: int, guild_id: int):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT INTO channels (channel_id,guild_id,last_active) VALUES (?,?,?) ON CONFLICT(channel_id) DO UPDATE SET last_active=excluded.last_active", (channel_id,guild_id,time.time()))
            await db.commit()

    async def get_active_channels(self) -> list[tuple]:
        cutoff = time.time()-86400*3
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT channel_id,guild_id FROM channels WHERE last_active>?", (cutoff,)) as cur:
                return await cur.fetchall()

    # ── Cooldowns ─────────────────────────────────────────────────────────────
    async def can_proactive(self, channel_id: int, cooldown: int = 3600) -> bool:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT last_sent FROM proactive_cooldown WHERE channel_id=?", (channel_id,)) as cur:
                row = await cur.fetchone(); return not row or (time.time()-row[0])>=cooldown

    async def set_proactive_sent(self, channel_id: int):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT INTO proactive_cooldown (channel_id,last_sent) VALUES (?,?) ON CONFLICT(channel_id) DO UPDATE SET last_sent=excluded.last_sent", (channel_id,time.time()))
            await db.commit()

    async def can_lore_drop(self, channel_id: int, cooldown: int = 21600) -> bool:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT last_sent FROM lore_cooldown WHERE channel_id=?", (channel_id,)) as cur:
                row = await cur.fetchone(); return not row or (time.time()-row[0])>=cooldown

    async def set_lore_sent(self, channel_id: int):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT INTO lore_cooldown (channel_id,last_sent) VALUES (?,?) ON CONFLICT(channel_id) DO UPDATE SET last_sent=excluded.last_sent", (channel_id,time.time()))
            await db.commit()

    async def can_starter(self, channel_id: int, cooldown: int = 10800) -> bool:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT last_sent FROM starter_cooldown WHERE channel_id=?", (channel_id,)) as cur:
                row = await cur.fetchone(); return not row or (time.time()-row[0])>=cooldown

    async def set_starter_sent(self, channel_id: int):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT INTO starter_cooldown (channel_id,last_sent) VALUES (?,?) ON CONFLICT(channel_id) DO UPDATE SET last_sent=excluded.last_sent", (channel_id,time.time()))
            await db.commit()

    # ── Romance helpers ───────────────────────────────────────────────────────
    async def get_romance_users(self) -> list[int]:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT user_id FROM users WHERE romance_mode=1 AND proactive=1") as cur:
                return [r[0] for r in await cur.fetchall()]

    async def get_user_last_channel(self, user_id: int) -> int | None:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT channel_id FROM messages WHERE user_id=? ORDER BY ts DESC LIMIT 1", (user_id,)) as cur:
                row = await cur.fetchone(); return row[0] if row else None

    # ── DM cooldown ───────────────────────────────────────────────────────────
    async def can_dm_user(self, user_id: int, cooldown: int = 7200) -> bool:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT last_sent FROM dm_cooldown WHERE user_id=?", (user_id,)) as cur:
                row = await cur.fetchone(); return not row or (time.time()-row[0])>=cooldown

    async def set_dm_sent(self, user_id: int):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT INTO dm_cooldown (user_id,last_sent) VALUES (?,?) ON CONFLICT(user_id) DO UPDATE SET last_sent=excluded.last_sent", (user_id,time.time()))
            await db.commit()

    async def get_dm_eligible_users(self) -> list[dict]:
        cutoff = time.time()-86400*7
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("""
                SELECT u.user_id,u.display_name,u.romance_mode,u.nsfw_mode
                FROM users u WHERE u.allow_dms=1 AND u.last_seen>?
                  AND EXISTS (SELECT 1 FROM messages m WHERE m.user_id=u.user_id)
            """, (cutoff,)) as cur:
                rows = await cur.fetchall()
        return [{"user_id":r[0],"display_name":r[1],"romance_mode":bool(r[2]),"nsfw_mode":bool(r[3])} for r in rows]

    # ── Stats ─────────────────────────────────────────────────────────────────
    async def get_stats(self, user_id: int) -> dict:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("""
                SELECT message_count,mood,affection,trust,first_seen,grudge_nick,
                       affection_nick,romance_mode,nsfw_mode,drift_score,slow_burn
                FROM users WHERE user_id=?
            """, (user_id,)) as cur:
                row = await cur.fetchone()
                if not row: return {}
            async with db.execute("SELECT COUNT(*) FROM inside_jokes WHERE user_id=?", (user_id,)) as cur:
                jokes = (await cur.fetchone())[0]
        return {
            "message_count":row[0] or 0, "mood":row[1] or 0, "affection":row[2] or 0,
            "trust":row[3] or 0, "first_seen":row[4] or 0, "grudge_nick":row[5],
            "affection_nick":row[6], "romance_mode":bool(row[7]), "nsfw_mode":bool(row[8]),
            "drift_score":row[9] or 0, "slow_burn":row[10] or 0, "joke_count":jokes,
        }
