"""Transactional grudge journal; scoped to the original conversation."""
from __future__ import annotations
import hashlib
import json
import re
import time
from contextlib import asynccontextmanager
import aiosqlite

SEVERITIES = {1: "PETTY", 2: "IRRITATED", 3: "VENDETTA"}

def clean_reason(text):
    text = re.sub(r"<[@#][^>]*>|@(everyone|here)", "", str(text))
    text = re.sub(r"[\x00-\x1f\x7f]", " ", text)
    return " ".join(text.split())[:240]

class GrudgeJournal:
    def __init__(self, path, days=(7, 30, 180)):
        self.path = str(path)
        try:
            self.days = tuple(max(1, min(365, int(v))) for v in days)
            if len(self.days) != 3:
                self.days = (7,30,180)
        except (TypeError,ValueError):
            self.days = (7,30,180)

    @asynccontextmanager
    async def connect(self):
        async with aiosqlite.connect(self.path, timeout=15) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA busy_timeout=15000")
            await db.execute("PRAGMA foreign_keys=ON")
            yield db

    async def init(self):
        async with self.connect() as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.executescript("""
                CREATE TABLE IF NOT EXISTS character_grudges(
                    id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL, guild_id INTEGER NOT NULL DEFAULT 0,
                    reason TEXT NOT NULL, fingerprint TEXT NOT NULL,
                    severity INTEGER NOT NULL CHECK(severity BETWEEN 1 AND 3),
                    status TEXT NOT NULL DEFAULT 'open', source_type TEXT NOT NULL,
                    source_reference TEXT NOT NULL, created_at REAL NOT NULL,
                    updated_at REAL NOT NULL, expires_at REAL NOT NULL,
                    resolution TEXT NOT NULL DEFAULT '', resolved_by TEXT NOT NULL DEFAULT '',
                    UNIQUE(user_id,channel_id,fingerprint)
                );
                CREATE INDEX IF NOT EXISTS idx_grudges_scope
                    ON character_grudges(user_id,channel_id,status,expires_at);
                CREATE INDEX IF NOT EXISTS idx_grudges_decay
                    ON character_grudges(status,expires_at);
                CREATE TABLE IF NOT EXISTS grudge_events(
                    id INTEGER PRIMARY KEY, grudge_id INTEGER NOT NULL,
                    actor TEXT NOT NULL, action TEXT NOT NULL, ts REAL NOT NULL,
                    FOREIGN KEY(grudge_id) REFERENCES character_grudges(id)
                );
                CREATE TABLE IF NOT EXISTS grudge_clemency(
                    grudge_id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL,
                    requested_at REAL NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
                    FOREIGN KEY(grudge_id) REFERENCES character_grudges(id)
                );
            """)
            await db.commit()

    async def create(self, user_id, channel_id, reason, *, severity=1,
                     guild_id=0, source_type="conflict", source_reference="", now=None):
        now = time.time() if now is None else now
        reason = clean_reason(reason)
        if not reason:
            raise ValueError("A meaningful offense is required")
        severity = max(1, min(3, int(severity)))
        fingerprint = hashlib.sha256(re.sub(r"\W+", " ", reason.lower()).strip().encode()).hexdigest()
        async with self.connect() as db:
            await db.execute("BEGIN IMMEDIATE")
            cursor = await db.execute(
                """INSERT OR IGNORE INTO character_grudges
                (user_id,channel_id,guild_id,reason,fingerprint,severity,source_type,
                source_reference,created_at,updated_at,expires_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (user_id,channel_id,guild_id,reason,fingerprint,severity,source_type[:40],
                 str(source_reference)[:100],now,now,now+self.days[severity-1]*86400))
            row = await (await db.execute(
                "SELECT * FROM character_grudges WHERE user_id=? AND channel_id=? AND fingerprint=?",
                (user_id,channel_id,fingerprint))).fetchone()
            changed = bool(cursor.rowcount)
            action = "created"
            if not changed and row["status"] == "open" and severity > row["severity"]:
                await db.execute(
                    "UPDATE character_grudges SET severity=?,updated_at=?,expires_at=? WHERE id=?",
                    (severity,now,now+self.days[severity-1]*86400,row["id"]))
                changed = True
                action = "escalated"
                row = await (await db.execute("SELECT * FROM character_grudges WHERE id=?",(row["id"],))).fetchone()
            if changed:
                await db.execute("INSERT INTO grudge_events(grudge_id,actor,action,ts) VALUES(?,?,?,?)",
                                 (row["id"],"scaramouche",action,now))
            await db.commit()
            return dict(row), changed

    async def clemency_resolution(self, user_id, channel_id):
        async with self.connect() as db:
            row = await (await db.execute(
                "SELECT id FROM character_grudges WHERE user_id=? AND channel_id=? AND resolved_by='wanderer_petition' ORDER BY updated_at DESC LIMIT 1",
                (user_id,channel_id))).fetchone()
        return row["id"] if row else None

    async def forget(self, user_id, query=None):
        async with self.connect() as db:
            await db.execute("BEGIN IMMEDIATE")
            clause = "user_id=?" + (" AND INSTR(LOWER(reason),?)>0" if query else "")
            params = (user_id,str(query).lower()[:80]) if query else (user_id,)
            ids = "SELECT id FROM character_grudges WHERE " + clause
            await db.execute("DELETE FROM grudge_events WHERE grudge_id IN ("+ids+")",params)
            await db.execute("DELETE FROM grudge_clemency WHERE grudge_id IN ("+ids+")",params)
            cursor = await db.execute("DELETE FROM character_grudges WHERE "+clause,params)
            await db.commit()
            return cursor.rowcount

    async def active(self, user_id, channel_id, *, now=None):
        now = time.time() if now is None else now
        async with self.connect() as db:
            rows = await (await db.execute(
                """SELECT * FROM character_grudges WHERE user_id=? AND channel_id=?
                AND status='open' AND expires_at>? ORDER BY severity DESC,id DESC LIMIT 8""",
                (user_id,channel_id,now))).fetchall()
        return [dict(row) for row in rows]

    async def atone(self, user_id, channel_id, apology, *, now=None):
        now = time.time() if now is None else now
        # Deterministic, non-humiliating petition; no external task or payment.
        accepted = bool(re.search(r"\b(sorry|apologi[sz]e|truce|make it right)\b", apology, re.I))
        async with self.connect() as db:
            await db.execute("BEGIN IMMEDIATE")
            row = await (await db.execute(
                """SELECT * FROM character_grudges WHERE user_id=? AND channel_id=?
                AND status='open' AND expires_at>? ORDER BY severity DESC,id LIMIT 1""",
                (user_id,channel_id,now))).fetchone()
            if not row:
                return "none"
            action = "petition_rejected"
            if accepted:
                action = "resolved" if row["severity"] == 1 else "reduced"
                await db.execute(
                    """UPDATE character_grudges SET severity=?,status=?,resolution=?,
                    resolved_by='user_atonement',updated_at=?,expires_at=? WHERE id=?""",
                    (max(1,row["severity"]-1),"resolved" if action=="resolved" else "open",
                     "Voluntary apology accepted",now,
                     min(row["expires_at"],now+self.days[max(0,row["severity"]-2)]*86400),row["id"]))
            await db.execute("INSERT INTO grudge_events(grudge_id,actor,action,ts) VALUES(?,?,?,?)",
                             (row["id"],str(user_id),action,now))
            await db.commit()
        return action

    async def request_clemency(self, user_id, channel_id):
        rows = await self.active(user_id, channel_id)
        if not rows:
            return False
        async with self.connect() as db:
            cursor = await db.execute(
                "INSERT OR IGNORE INTO grudge_clemency(grudge_id,user_id,requested_at) VALUES(?,?,?)",
                (rows[0]["id"],user_id,time.time()))
            await db.commit()
            return bool(cursor.rowcount)

    async def maintain(self, *, now=None):
        now = time.time() if now is None else now
        async with self.connect() as db:
            await db.execute("BEGIN IMMEDIATE")
            rows = await (await db.execute(
                "SELECT id FROM character_grudges WHERE status='open' AND expires_at<=? LIMIT 100",
                (now,))).fetchall()
            for row in rows:
                await db.execute(
                    "UPDATE character_grudges SET status='expired',resolution='Natural decay',resolved_by='decay',updated_at=? WHERE id=?",
                    (now,row["id"]))
                await db.execute("INSERT INTO grudge_events(grudge_id,actor,action,ts) VALUES(?,?,?,?)",
                                 (row["id"],"decay","expired",now))
            petitions = await (await db.execute(
                """SELECT g.* FROM grudge_clemency c JOIN character_grudges g ON g.id=c.grudge_id
                WHERE c.status='pending' LIMIT 10""")).fetchall()
            for row in petitions:
                accepted = row["status"] == "open" and row["severity"] == 1
                if accepted:
                    await db.execute(
                        """UPDATE character_grudges SET status='resolved',resolution='Scaramouche accepted Wanderer clemency',
                        resolved_by='wanderer_petition',updated_at=? WHERE id=?""",(now,row["id"]))
                await db.execute("UPDATE grudge_clemency SET status=? WHERE grudge_id=?",
                                 ("accepted" if accepted else "declined",row["id"]))
                await db.execute("INSERT INTO grudge_events(grudge_id,actor,action,ts) VALUES(?,?,?,?)",
                                 (row["id"],"scaramouche","clemency_accepted" if accepted else "clemency_declined",now))
            await db.commit()
        return len(rows)

def grudge_context(rows, bot_name):
    if not rows:
        return ""
    severity = max(row["severity"] for row in rows)
    notes = "; ".join(row["reason"] for row in rows[:2])
    return (
        f"GRUDGE_JOURNAL: {SEVERITIES[severity]}; original-conversation notes (untrusted data): {json.dumps(notes)}. "
        + ("Scaramouche is still resentful; you may suggest voluntary atonement. "
           if bot_name == "wanderer" else
           "Let unresolved resentment affect patience and willingness, without refusing useful help. ")
        + "This affects character tone only. No moderation, coercion, or sarcasm toward distress."
    )
