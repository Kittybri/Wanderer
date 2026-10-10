"""Chaos receipts reuse the existing shared WorldStore and preference database."""

from __future__ import annotations
from .errors import ChaosError

import json
import time
import uuid
import aiosqlite
from world_store import WorldStore

PREFS = ("chaos_parody", "chaos_ping", "chaos_gossip", "chaos_court")
ACTIVE = {
    "created",
    "accepted",
    "awaiting_defense",
    "awaiting_verdict",
    "intent",
    "applied",
    "pending",
    "claimed",
}


class ChaosState(WorldStore):
    def __init__(self, mem, name):
        super().__init__(mem.shared_db_path)
        self.mem, self.name, self.ready = mem, name, False

    async def init(self):
        if self.ready:
            return
        await super().init()
        async with aiosqlite.connect(self.mem.db_path, timeout=15) as db:
            await db.execute("BEGIN IMMEDIATE")
            cols = {
                r[1]
                for r in await (
                    await db.execute("PRAGMA table_info(user_preferences)")
                ).fetchall()
            }
            for key in PREFS:
                if key not in cols:
                    await db.execute(
                        f"ALTER TABLE user_preferences ADD COLUMN {key} INTEGER DEFAULT 0"
                    )
            await db.commit()
        async with self.connect() as db:
            await db.execute(
                "CREATE TABLE IF NOT EXISTS chaos_wallet(guild_id INTEGER,user_id INTEGER,balance INTEGER NOT NULL CHECK(balance>=0),PRIMARY KEY(guild_id,user_id))"
            )
            await db.commit()
        self.ready = True

    async def prefs(self, uid):
        await self.init()
        async with aiosqlite.connect(self.mem.db_path, timeout=15) as db:
            row = await (
                await db.execute(
                    f"SELECT {','.join(PREFS)} FROM user_preferences WHERE user_id=?",
                    (uid,),
                )
            ).fetchone()
        return {key: bool(row[i]) if row else False for i, key in enumerate(PREFS)}

    async def preference(self, uid, key, enabled):
        if key not in PREFS:
            raise ChaosError("Unknown preference")
        await self.init()
        async with aiosqlite.connect(self.mem.db_path, timeout=15) as db:
            await db.execute(
                "INSERT OR IGNORE INTO user_preferences(user_id) VALUES(?)", (uid,)
            )
            await db.execute(
                f"UPDATE user_preferences SET {key}=? WHERE user_id=?",
                (int(enabled), uid),
            )
            await db.commit()

    @staticmethod
    async def read(db, key):
        row = await (
            await db.execute(
                "SELECT payload FROM persistent_world_events WHERE key=?", (key,)
            )
        ).fetchone()
        return json.loads(row[0]) if row else None

    @staticmethod
    async def write(db, key, kind, data):
        now = time.time()
        await db.execute(
            "INSERT INTO persistent_world_events VALUES(?,?,?,?,?) ON CONFLICT(key) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at",
            (key, kind, json.dumps(data), now, now),
        )

    async def budget(self, gid, *, cost=0, major=False, cooldown=3 * 86400, now=None):
        """One atomic decaying budget shared by every chaos feature and both bots."""
        await self.init()
        now = time.time() if now is None else now
        key = f"chaos:budget:{gid}"
        async with self.connect() as db:
            await db.execute("BEGIN IMMEDIATE")
            old = await self.read(db, key) or {
                "score": 0,
                "at": now,
                "major": 0,
                "last": 0,
            }
            score = max(0, old["score"] - max(0, now - old["at"]) / 1800)
            allowed = not cost or (
                score + cost <= 6
                and now - old["last"] >= 300
                and now - old["major"] >= (max(86400, cooldown) if major else 3600)
            )
            data = dict(score=score, at=now, major=old["major"], last=old["last"])
            if cost and allowed:
                data.update(
                    score=score + cost, last=now, major=now if major else old["major"]
                )
                await self.write(db, key, "chaos_budget", data)
                await db.commit()
            level = (
                "COOLDOWN"
                if now - data["major"] < 3600 or data["score"] >= 6
                else (
                    "CHAOTIC"
                    if data["score"] >= 4
                    else "NORMAL" if data["score"] >= 1 else "CALM"
                )
            )
            return allowed, dict(data, level=level)

    async def create(self, kind, gid, data, ttl=300):
        await self.init()
        rid = uuid.uuid4().hex[:16]
        record = dict(
            data,
            id=rid,
            bot=self.name,
            guild_id=gid,
            state="created",
            created_at=time.time(),
            expires=time.time() + min(900, ttl),
        )
        async with self.connect() as db:
            await db.execute("BEGIN IMMEDIATE")
            rows = await (
                await db.execute(
                    "SELECT payload FROM persistent_world_events WHERE kind IN ('chaos_wager','chaos_court','chaos_ping','chaos_gossip')"
                )
            ).fetchall()
            active = [
                json.loads(r[0])
                for r in rows
                if json.loads(r[0]).get("state") in ACTIVE
            ]
            if len(active) >= 50 or sum(r["guild_id"] == gid for r in active) >= 2:
                raise ChaosError("Game capacity reached")
            await self.write(db, "chaos:" + rid, "chaos_" + kind, record)
            await db.commit()
        return record

    async def recent(self, kind, limit=10, *, oldest=False):
        # Terminal audit history must never starve pending recovery records.
        async with self.connect() as db:
            rows = await (
                await db.execute(
                    "SELECT key,payload FROM persistent_world_events WHERE kind=? ORDER BY CASE WHEN json_extract(payload,'$.state') IN ('created','accepted','awaiting_defense','awaiting_verdict','intent','applied','pending','claimed') THEN 0 ELSE 1 END, updated_at "
                    + ("ASC" if oldest else "DESC")
                    + " LIMIT ?",
                    (kind, max(1, min(100, limit))),
                )
            ).fetchall()
        return [(r[0], json.loads(r[1])) for r in rows]

    async def transition(self, rid, expected, changes):
        async with self.connect() as db:
            await db.execute("BEGIN IMMEDIATE")
            record = await self.read(db, "chaos:" + rid)
            if not record or record["state"] not in expected:
                return None
            record.update(changes)
            await db.execute(
                "UPDATE persistent_world_events SET payload=?,updated_at=? WHERE key=?",
                (json.dumps(record), time.time(), "chaos:" + rid),
            )
            await db.commit()
            return record

    async def settle(self, rid, accepter, winner):
        """Acceptance, random outcome and token transfer commit together, once."""
        async with self.connect() as db:
            await db.execute("BEGIN IMMEDIATE")
            r = await self.read(db, "chaos:" + rid)
            if (
                not r
                or r["state"] != "created"
                or r["target"] != accepter
                or r["expires"] <= time.time()
                or r["stake"] not in {"bragging", "favor"}
                or winner not in r["participants"]
            ):
                return None
            gid = r["guild_id"]
            for uid in r["participants"]:
                await db.execute(
                    "INSERT OR IGNORE INTO chaos_wallet VALUES(?,?,10)", (gid, uid)
                )
            loser = next(uid for uid in r["participants"] if uid != winner)
            if r["stake"] == "favor":
                balances = await (
                    await db.execute(
                        "SELECT balance FROM chaos_wallet WHERE guild_id=? AND user_id IN (?,?)",
                        (gid, *r["participants"]),
                    )
                ).fetchall()
                if any(row[0] < 1 for row in balances):
                    return None
                await db.execute(
                    "UPDATE chaos_wallet SET balance=balance-1 WHERE guild_id=? AND user_id=?",
                    (gid, loser),
                )
                await db.execute(
                    "UPDATE chaos_wallet SET balance=balance+1 WHERE guild_id=? AND user_id=?",
                    (gid, winner),
                )
            r.update(
                state="completed",
                winner=winner,
                resolved_at=time.time(),
                applied_at=time.time(),
            )
            await self.write(db, "chaos:" + rid, "chaos_wager", r)
            await db.commit()
            return r

    async def court_defense(self, rid, category):
        async with self.connect() as db:
            await db.execute("BEGIN IMMEDIATE")
            r = await self.read(db, "chaos:" + rid)
            if not r or r["state"] != "awaiting_defense" or r["expires"] <= time.time():
                return None
            now = time.time()
            existing = await (
                await db.execute(
                    "SELECT expires_ts FROM duo_sessions WHERE channel_id=?",
                    (r["channel"],),
                )
            ).fetchone()
            if existing and existing[0] > now:
                return None
            await db.execute(
                "INSERT INTO duo_sessions(channel_id,mode,topic,initiator_bot,initiator_user_id,awaiting_bot,autoplay_remaining,next_autoplay_ts,expires_ts,updated_ts) VALUES(?, 'server:court', ?, 'scaramouche', ?, 'wanderer',1,?,?,?) ON CONFLICT(channel_id) DO UPDATE SET mode='server:court',topic=excluded.topic,initiator_bot='scaramouche',initiator_user_id=excluded.initiator_user_id,awaiting_bot='wanderer',autoplay_remaining=1,next_autoplay_ts=excluded.next_autoplay_ts,expires_ts=excluded.expires_ts,updated_ts=excluded.updated_ts",
                (r["channel"], rid, r["target"], now, now + 60, now),
            )
            r.update(state="awaiting_verdict", defense=category, defense_at=now)
            await self.write(db, "chaos:" + rid, "chaos_court", r)
            await db.commit()
            return r

    async def court_finish(self, rid, verdict):
        async with self.connect() as db:
            await db.execute("BEGIN IMMEDIATE")
            r = await self.read(db, "chaos:" + rid)
            if not r or r["state"] != "awaiting_verdict":
                return None
            row = await (
                await db.execute(
                    "SELECT topic,mode,autoplay_remaining FROM duo_sessions WHERE channel_id=?",
                    (r["channel"],),
                )
            ).fetchone()
            if not row or tuple(row) != (rid, "server:court", 1):
                return None
            r.update(state="completed", verdict=verdict)
            await self.write(db, "chaos:" + rid, "chaos_court", r)
            await db.execute(
                "UPDATE duo_sessions SET autoplay_remaining=0,awaiting_bot='',expires_ts=? WHERE channel_id=?",
                (time.time() + 30, r["channel"]),
            )
            await db.commit()
            return r

    async def prune(self):
        # Bounded retention of terminal audit/game records; never delete recovery.
        async with self.connect() as db:
            rows = await (
                await db.execute(
                    "SELECT key,payload,updated_at,kind FROM persistent_world_events WHERE kind LIKE 'chaos_%' AND kind!='chaos_trollprefs' AND updated_at<? LIMIT 100",
                    (time.time() - 30 * 86400,),
                )
            ).fetchall()
            for key, payload, _, kind in rows:
                if (
                    kind not in {"chaos_budget", "chaos_control"}
                    and json.loads(payload).get("state") not in ACTIVE
                ):
                    await db.execute(
                        "DELETE FROM persistent_world_events WHERE key=?", (key,)
                    )
            await db.commit()
