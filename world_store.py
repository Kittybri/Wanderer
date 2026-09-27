"""Shared durable job records for dreams, event receipts and restoration."""
from __future__ import annotations
import json
import time
from contextlib import asynccontextmanager
import aiosqlite

class WorldStore:
    def __init__(self, path):
        self.path = str(path)

    @asynccontextmanager
    async def connect(self):
        async with aiosqlite.connect(self.path, timeout=15) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA busy_timeout=15000")
            yield db

    async def init(self):
        async with self.connect() as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.executescript("""
                CREATE TABLE IF NOT EXISTS persistent_world_events(
                    key TEXT PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL,
                    created_at REAL NOT NULL, updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_world_kind
                    ON persistent_world_events(kind,updated_at);
            """)
            await db.commit()

    async def claim(self, key, kind, payload=None, *, now=None):
        now = time.time() if now is None else now
        async with self.connect() as db:
            c = await db.execute("INSERT OR IGNORE INTO persistent_world_events VALUES(?,?,?,?,?)",
                (key,kind,json.dumps(payload or {}),now,now))
            await db.commit()
            return bool(c.rowcount)

    async def put(self, key, kind, payload):
        now = time.time()
        async with self.connect() as db:
            await db.execute("""INSERT INTO persistent_world_events VALUES(?,?,?,?,?)
                ON CONFLICT(key) DO UPDATE SET kind=excluded.kind,payload=excluded.payload,updated_at=excluded.updated_at""",
                (key,kind,json.dumps(payload),now,now))
            await db.commit()

    async def get(self, key):
        async with self.connect() as db:
            row = await (await db.execute("SELECT payload FROM persistent_world_events WHERE key=?",(key,))).fetchone()
        return json.loads(row["payload"]) if row else None

    async def recent(self, kind, limit=10, *, oldest=False):
        async with self.connect() as db:
            rows = await (await db.execute(
                "SELECT key,payload FROM persistent_world_events WHERE kind=? ORDER BY updated_at " + ("ASC" if oldest else "DESC") + " LIMIT ?",
                (kind,max(1,min(100,limit))))).fetchall()
        return [(r["key"],json.loads(r["payload"])) for r in rows]

    async def remove(self, key):
        async with self.connect() as db:
            await db.execute("DELETE FROM persistent_world_events WHERE key=?",(key,))
            await db.commit()
