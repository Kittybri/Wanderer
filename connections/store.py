"""Additive, transactional schema in the bots' canonical shared SQLite database."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import aiosqlite

SCHEMA = (
    "CREATE TABLE IF NOT EXISTS connections_migrations (version INTEGER PRIMARY KEY, name TEXT NOT NULL)",
    """CREATE TABLE IF NOT EXISTS connected_accounts (
        user_id INTEGER NOT NULL, provider TEXT NOT NULL, revision TEXT NOT NULL UNIQUE,
        masked_identity TEXT NOT NULL, credentials BLOB, scopes TEXT NOT NULL,
        status TEXT NOT NULL, expiry REAL NOT NULL, connected_at REAL NOT NULL,
        updated_at REAL NOT NULL, last_refresh_at REAL, refresh_owner TEXT,
        refresh_until REAL NOT NULL DEFAULT 0, retry_after REAL NOT NULL DEFAULT 0,
        PRIMARY KEY(user_id, provider))""",
    """CREATE TABLE IF NOT EXISTS connected_account_bot_grants (
        user_id INTEGER NOT NULL, provider TEXT NOT NULL, bot_name TEXT NOT NULL,
        enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),
        PRIMARY KEY(user_id, provider, bot_name),
        FOREIGN KEY(user_id, provider) REFERENCES connected_accounts(user_id, provider) ON DELETE CASCADE)""",
    """CREATE TABLE IF NOT EXISTS connection_sessions (
        id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, provider TEXT NOT NULL,
        bot_name TEXT NOT NULL, link_hash TEXT NOT NULL UNIQUE, state_hash TEXT UNIQUE,
        browser_hash TEXT, redirect_uri TEXT NOT NULL, stage TEXT NOT NULL,
        created_at REAL NOT NULL, expires_at REAL NOT NULL, sealed BLOB,
        masked_identity TEXT, scopes TEXT, expiry REAL, notified INTEGER NOT NULL DEFAULT 0,
        UNIQUE(user_id, provider, bot_name))""",
    "CREATE INDEX IF NOT EXISTS connection_sessions_expiry ON connection_sessions(expires_at)",
    # No user identifiers or credentials in the bounded global admission counter.
    "CREATE TABLE IF NOT EXISTS connection_admission (bucket INTEGER PRIMARY KEY, count INTEGER NOT NULL)",
    "CREATE TABLE IF NOT EXISTS connection_attempts (user_id INTEGER PRIMARY KEY, bucket INTEGER NOT NULL, count INTEGER NOT NULL)",
)


class Store:
    def __init__(self, path):
        self.path = str(path)
        self._initialized = False
        self._lock = None

    async def initialize(self):
        if self._initialized:
            return
        if self._lock is None:
            self._lock = asyncio.Lock()
        async with self._lock:
            async with aiosqlite.connect(self.path, timeout=5) as db:
                await db.execute("PRAGMA foreign_keys=ON")
                await db.execute("BEGIN IMMEDIATE")
                try:
                    for statement in SCHEMA:
                        await db.execute(statement)
                    await db.execute("INSERT OR IGNORE INTO connections_migrations VALUES (1, 'encrypted_connections')")
                    await db.commit()
                except BaseException:
                    await db.rollback()
                    raise
            self._initialized = True

    @asynccontextmanager
    async def transaction(self):
        await self.initialize()
        async with aiosqlite.connect(self.path, timeout=5) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA foreign_keys=ON")
            await db.execute("BEGIN IMMEDIATE")
            try:
                yield db
                await db.commit()
            except BaseException:
                await db.rollback()
                raise


async def one(db, sql, args=()):
    async with db.execute(sql, args) as cursor:
        row = await cursor.fetchone()
        return dict(row) if row else None
