"""Batch C: isolated SQLite upgrade and two-bot concurrency regression tests."""
import asyncio
import sqlite3
import time

from memory import Memory


def _store(tmp_path, bot_name):
    db = Memory(bot_name)
    db.db_path = str(tmp_path / (bot_name + ".db"))
    db.shared_db_path = str(tmp_path / "shared.db")
    return db


def _legacy(path):
    with sqlite3.connect(path) as conn:
        conn.execute(
            """CREATE TABLE duo_sessions(
                channel_id INTEGER PRIMARY KEY, mode TEXT DEFAULT 'both',
                topic TEXT, initiator_bot TEXT, initiator_user_id INTEGER DEFAULT 0,
                last_speaker TEXT, awaiting_bot TEXT, autoplay_remaining INTEGER DEFAULT 0,
                next_autoplay_ts REAL DEFAULT 0, expires_ts REAL DEFAULT 0,
                updated_ts REAL DEFAULT 0
            )"""
        )
        conn.execute(
            "INSERT INTO duo_sessions(channel_id,mode,topic,initiator_bot,"
            "initiator_user_id,awaiting_bot,autoplay_remaining,next_autoplay_ts,"
            "expires_ts,updated_ts) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (9042, "trial", "original topic", "scaramouche", 77,
             "wanderer", 2, time.time()-1, time.time()+1200, time.time()),
        )


def test_additive_upgrade_retains_existing_sessions_and_is_idempotent(tmp_path):
    async def run():
        path = tmp_path / "shared.db"
        _legacy(str(path))
        db = _store(tmp_path, "scaramouche")
        await db.init()
        session = await db.get_duo_session(9042)
        assert session and session["topic"] == "original topic"
        assert session["initiator_user_id"] == 77
        assert session["awaiting_bot"] == "wanderer"
        assert session["autoplay_remaining"] == 2
        assert await db.get_duo_reply_anchor(9042, "wanderer") is None
        assert await db.record_duo_reply_anchor(9042, "wanderer", 1234, 999)
        await db.init()
        assert (await db.get_duo_session(9042))["topic"] == "original topic"
        assert await db.get_duo_reply_anchor(9042, "wanderer") == 1234
        with sqlite3.connect(path) as connection:
            assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            names = {row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
            assert {"duo_sessions", "duo_reply_anchors"}.issubset(names)
    asyncio.run(run())


def test_simultaneous_independent_connections_preserve_first_source(tmp_path):
    async def run():
        a = _store(tmp_path, "scaramouche")
        b = _store(tmp_path, "wanderer")
        await a.init()
        await b.init()
        await a.set_duo_session(
            20, "trial", "competing messages", "scaramouche",
            awaiting_bot="wanderer", autoplay_turns=3,
        )
        outcomes = await asyncio.gather(
            a.record_duo_reply_anchor(20, "wanderer", 101, 999),
            b.record_duo_reply_anchor(20, "wanderer", 102, 999),
        )
        assert sorted(outcomes) == [False, True]
        saved = await a.get_duo_reply_anchor(20, "wanderer")
        assert saved in {101, 102}
        assert await b.get_duo_reply_anchor(20, "wanderer") == saved
        assert not await b.record_duo_reply_anchor(20, "wanderer", 103, 999)
        assert await a.get_duo_reply_anchor(20, "wanderer") == saved
    asyncio.run(run())


def test_old_speaker_cannot_overwrite_anchor_after_handoff_or_clear(tmp_path):
    async def run():
        a = _store(tmp_path, "scaramouche")
        b = _store(tmp_path, "wanderer")
        await a.init()
        await b.init()
        await a.set_duo_session(
            21, "trial", "handoff", "scaramouche",
            awaiting_bot="wanderer", autoplay_turns=3,
        )
        assert await a.record_duo_reply_anchor(21, "wanderer", 111, 99)
        await b.bump_duo_session(
            21, "wanderer", partner_bot="scaramouche",
            reply_source_message_id=222, reply_source_author_id=88,
        )
        assert await a.get_duo_reply_anchor(21, "scaramouche") == 222
        assert not await a.record_duo_reply_anchor(21, "wanderer", 333, 99)
        assert await b.get_duo_reply_anchor(21, "scaramouche") == 222
        await a.clear_duo_session(21)
        assert await b.get_duo_reply_anchor(21, "scaramouche") is None
    asyncio.run(run())
