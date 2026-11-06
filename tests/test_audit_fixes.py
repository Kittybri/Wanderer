"""Regression tests for the November audit fixes on Wanderer's main line.

Run from the repository root (nothing beyond requirements.txt is needed):

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import atexit
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace as NS
from unittest import mock
from unittest.mock import AsyncMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
# Every database these tests touch lives in a throwaway folder (memory.py picks its folder when first imported).
_DATA_DIR = tempfile.mkdtemp(prefix="scaramouche-tests-")
atexit.register(shutil.rmtree, _DATA_DIR, True)
os.environ["MEMORY_DATA_DIR"] = _DATA_DIR
os.environ.setdefault("DISCORD_TOKEN", "test-token")
os.environ.setdefault("OWNER_ID", "999")
os.environ.setdefault("GROQ_API_KEY", "test-key")

import discord  # noqa: E402

import memory  # noqa: E402
import docfix_guard  # noqa: E402
import narration  # noqa: E402
import video_render_worker as worker  # noqa: E402
import bot  # noqa: E402

DOC = "https://docs.google.com/document/d/abcdefghijklmnopqrstuvwx/edit"
DOC_ID = "abcdefghijklmnopqrstuvwx"


# ── helpers ──────────────────────────────────────────────────────────────────
def use_fresh_memory(test: unittest.TestCase) -> memory.Memory:
    """A new, empty pair of databases for one test; bot.py's ``mem`` points at it until the test ends."""
    folder = tempfile.mkdtemp(prefix="mem-", dir=_DATA_DIR)
    for name, value in (
        ("_data_dir", folder),
        ("DB_PATH", os.path.join(folder, "wanderer.db")),
        ("SHARED_DB_PATH", os.path.join(folder, "shared_state.db")),
    ):
        patcher = mock.patch.object(memory, name, value)
        patcher.start()
        test.addCleanup(patcher.stop)
    store = memory.Memory("wanderer")
    patcher = mock.patch.object(bot, "mem", store)
    patcher.start()
    test.addCleanup(patcher.stop)
    return store


class Typing:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def make_ctx(author_id: int = 5, *, guild_id: int | None = None, members: dict | None = None, nsfw: bool = False):
    guild = None
    if guild_id is not None:
        roster = members or {}
        guild = NS(id=guild_id, get_member=lambda uid: roster.get(uid))
    author = NS(id=author_id, name=f"user{author_id}", display_name=f"user{author_id}", bot=False,
                mention=f"<@{author_id}>", send=AsyncMock())
    channel = NS(id=9000 + author_id, guild=guild, is_nsfw=lambda: nsfw)
    return NS(author=author, guild=guild, channel=channel, reply=AsyncMock(), send=AsyncMock(), typing=Typing)


def said(ctx) -> str:
    """Everything the bot posted where the command was used (not DMs)."""
    calls = ctx.reply.await_args_list + ctx.send.await_args_list
    return "\n".join(str(call.args[0]) for call in calls if call.args)


class BotTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.mem = use_fresh_memory(self)
        await self.mem.init()
        self.use(bot, "OWNER_ID", 999)
        self.use(bot, "DISCORD_SEND_MIN_INTERVAL_S", 0)
        self.use(bot, "_setup", self._fake_setup)

    def use(self, target, name, value):
        patcher = mock.patch.object(target, name, value)
        patcher.start()
        self.addCleanup(patcher.stop)
        return value

    async def _fake_setup(self, ctx):
        await self.mem.upsert_user(ctx.author.id, ctx.author.name, ctx.author.display_name)
        return await self.mem.get_user(ctx.author.id)

    async def seed_messages(self):
        """User 1 talks in a DM, in server 100 (channel 10) and in server 200 (channel 20)."""
        await self.mem.track_channel(10, 100)
        await self.mem.track_channel(20, 200)
        await self.mem.add_message(1, 1, "user", "dm secret")  # DMs are stored under the user id, never tracked
        await self.mem.add_message(1, 10, "user", "said in server A")
        await self.mem.add_message(1, 20, "user", "said in server B")


# ── narration and mentions ───────────────────────────────────────────────────
class NarrationTests(unittest.TestCase):
    def test_stage_directions_are_removed(self):
        for raw, expected in [
            ("*sighs* Fine.", "Fine."),
            ("(smiles faintly) Come here.", "Come here."),
            ("[he looks away] Whatever.", "Whatever."),
            ('Kunikuzushi sighed, "Fine."', '"Fine."'),
        ]:
            with self.subTest(raw=raw):
                self.assertEqual(narration.strip_narration(raw), expected)

    def test_ordinary_content_survives(self):
        for text in [
            "The answer is **42**.",
            "I do *not* care.",
            "f(x) = (x+1)^2",
            "See (page 4).",
            "[ANSWER: Paris] Obviously.",
            "Which god? [ANSWER: Raiden Shogun] [SOURCE: Archon Quest]",  # !trivia reads these tags
            "Read https://en.wikipedia.org/wiki/Boiling_(disambiguation) first.",
            "They said the library closes at 9.",
        ]:
            with self.subTest(text=text):
                self.assertEqual(narration.strip_narration(text), text)
                self.assertEqual(bot.strip_narration(text), text)

    def test_mass_and_role_mentions_never_survive(self):
        for text in ["@everyone look at this", "hi @here", "<@&123> role ping", "@@everyone", "<@&<@&1>1>"]:
            with self.subTest(text=text):
                cleaned = narration.strip_narration(text)
                self.assertNotIn("@everyone", cleaned)
                self.assertNotIn("@here", cleaned)
                self.assertIsNone(re.search(r"<@&\d+>", cleaned))  # leftovers such as "<@& 1>" cannot ping

    def test_the_bot_never_pings_everyone_or_roles(self):
        self.assertFalse(bot.bot.allowed_mentions.everyone)
        self.assertFalse(bot.bot.allowed_mentions.roles)

    def test_long_text_is_split_under_discords_limit(self):
        text = " ".join(f"word{i}" for i in range(900))
        pieces = narration.chunk_text(text, bot.MESSAGE_CHAR_LIMIT)
        self.assertGreater(len(pieces), 1)
        self.assertTrue(all(len(piece) <= 2000 for piece in pieces))
        self.assertEqual(" ".join(pieces).split(), text.split())


# ── render worker ────────────────────────────────────────────────────────────
class WorkerAuthTests(unittest.TestCase):
    SECRET = "s" * 32

    def test_no_secret_means_nobody_is_authorized(self):
        with mock.patch.object(worker, "VIDEO_RENDER_SECRET", ""):
            self.assertFalse(worker._authorized({}))
            self.assertFalse(worker._authorized({"X-Render-Secret": ""}))

    def test_a_short_secret_is_refused(self):
        with mock.patch.object(worker, "VIDEO_RENDER_SECRET", "short"):
            self.assertFalse(worker._authorized({"X-Render-Secret": "short"}))

    def test_the_secret_must_match(self):
        with mock.patch.object(worker, "VIDEO_RENDER_SECRET", self.SECRET):
            self.assertTrue(worker._authorized({"X-Render-Secret": self.SECRET}))
            self.assertTrue(worker._authorized({"Authorization": f"Bearer {self.SECRET}"}))
            self.assertFalse(worker._authorized({"X-Render-Secret": self.SECRET[:-1] + "x"}))
            self.assertFalse(worker._authorized({}))

    def test_render_requests_can_only_set_voice_settings(self):
        cleaned = worker._clean_env_overrides({
            "FISH_AUDIO_API_KEY": "k", "SCARAMOUCHE_VOICE_ID": "v", "PATH": "/tmp/evil", "PYTHONPATH": "/tmp",
            "LD_PRELOAD": "/tmp/x.so", "HTTPS_PROXY": "http://evil.example", "VOICE_ID": 5, "PARTNER_VOICE_ID": "a\x00b",
        })
        self.assertEqual(cleaned, {"FISH_AUDIO_API_KEY": "k", "SCARAMOUCHE_VOICE_ID": "v"})
        self.assertEqual(worker._clean_env_overrides(["PATH"]), {})

    def test_listens_on_loopback_unless_told_otherwise(self):
        if os.getenv("VIDEO_RENDER_HOST"):
            self.skipTest("VIDEO_RENDER_HOST is set in this environment")
        self.assertEqual(worker.VIDEO_RENDER_HOST, "127.0.0.1")

    def test_refuses_to_start_without_a_secret(self):
        folder = tempfile.mkdtemp(prefix="worker-", dir=_DATA_DIR)  # no video_render_worker.env or .env here
        for name in ("video_render_worker.py", "google_docs_bridge.py"):
            shutil.copy(ROOT / name, folder)
        env = {k: v for k, v in os.environ.items() if k not in {"VIDEO_RENDER_SECRET", "VIDEO_RENDER_SHARED_SECRET"}}
        proc = subprocess.run(
            [sys.executable, "video_render_worker.py"], cwd=folder, env=env, capture_output=True, text=True, timeout=60,
            check=False,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("VIDEO_RENDER_SECRET", proc.stderr)


# ── memory scoping ───────────────────────────────────────────────────────────
class MemoryScopingTests(BotTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        await self.seed_messages()

    async def test_server_scope_leaves_out_dms_and_other_servers(self):
        self.assertEqual(await self.mem.get_recent_messages(1, 10, guild_id=100), ["said in server A"])

    async def test_public_scope_never_includes_dms(self):
        await self.mem.track_channel(30, None)  # a row without a server never counts as public
        await self.mem.add_message(1, 30, "user", "no server")
        self.assertCountEqual(
            await self.mem.get_recent_messages(1, 10, public_only=True), ["said in server A", "said in server B"],
        )

    async def test_unscoped_history_is_unchanged(self):
        self.assertEqual(len(await self.mem.get_recent_messages(1, 10)), 3)

    async def test_profiling_only_sees_what_the_audience_could_see(self):
        self.assertEqual(await bot._visible_messages(make_ctx(2, guild_id=100), 1, 10), ["said in server A"])
        self.assertEqual(len(await bot._visible_messages(make_ctx(1), 1, 10)), 3)  # your own DM with the bot
        self.assertCountEqual(
            await bot._visible_messages(make_ctx(2), 1, 10), ["said in server A", "said in server B"],
        )

    async def test_stalk_never_quotes_dms_or_other_servers(self):
        qai = self.use(bot, "qai", AsyncMock(return_value="I've noticed things."))
        target = NS(id=1, display_name="Target", mention="<@1>")
        await bot.stalk_cmd.callback(make_ctx(2, guild_id=100), target)
        prompt = qai.await_args.args[0]
        self.assertIn("said in server A", prompt)
        self.assertNotIn("dm secret", prompt)
        self.assertNotIn("said in server B", prompt)

    async def test_rank_counts_only_this_servers_messages(self):
        await self.mem.add_message(2, 10, "user", "hi")
        await self.mem.add_message(2, 10, "assistant", "a bot reply is not counted")
        for _ in range(5):
            await self.mem.add_message(3, 20, "user", "busy elsewhere")
        members = {uid: NS(id=uid, display_name=f"member{uid}", bot=False) for uid in (1, 2, 3)}
        ctx = make_ctx(1, guild_id=100, members=members)
        self.use(bot, "qai", AsyncMock(return_value="Tolerable. Barely."))
        await bot.rank_cmd.callback(ctx)
        description = ctx.send.await_args.kwargs["embed"].description
        self.assertIn("member1** — 1 messages", description)
        self.assertIn("member2** — 1 messages", description)
        self.assertNotIn("member3", description)  # a member here, but only active in another server

    async def test_progress_reads_his_own_replies_and_only_from_this_server(self):
        await self.mem.add_message(1, 10, "assistant", "reply in server A")
        await self.mem.add_message(1, 1, "assistant", "reply in our DM")
        await self.mem.add_message(1, 20, "assistant", "reply in server B")
        qai = self.use(bot, "qai", AsyncMock(return_value="I've been better."))
        await bot.progress_cmd.callback(make_ctx(1, guild_id=100))
        prompt = qai.await_args.args[0]
        self.assertIn("reply in server A", prompt)  # his replies, not the person's own messages
        self.assertNotIn("said in server A", prompt)
        self.assertNotIn("reply in our DM", prompt)
        self.assertNotIn("reply in server B", prompt)

    async def test_adult_confirmation_is_stored(self):
        await self.mem.upsert_user(5, "user5", "user5")
        self.assertFalse((await self.mem.get_user(5))["adult_confirmed"])
        await self.mem.set_mode(5, "adult_confirmed", True)
        self.assertTrue((await self.mem.get_user(5))["adult_confirmed"])
        with self.assertRaises(ValueError):
            await self.mem.set_mode(5, "affection", True)

    async def test_mood_swings_work(self):
        await self.mem.upsert_user(5, "user5", "user5")
        await self.mem.random_mood_swing(5)


# ── unfiltered mode ──────────────────────────────────────────────────────────
class AdultModeTests(BotTestCase):
    def test_unfiltered_prompt_needs_confirmation_and_an_allowed_place(self):
        user = {"nsfw_mode": True, "romance_mode": False}
        self.assertNotIn(bot._NSFW, bot.build_system({**user, "adult_confirmed": False}, allow_nsfw=True))
        self.assertNotIn(bot._NSFW, bot.build_system({**user, "adult_confirmed": True}, allow_nsfw=False))
        self.assertNotIn(bot._NSFW, bot.build_system({**user, "adult_confirmed": True}))
        self.assertIn(bot._NSFW, bot.build_system({**user, "adult_confirmed": True}, allow_nsfw=True))
        romance = {**user, "romance_mode": True, "adult_confirmed": True}
        self.assertIn(bot._NSFW_ROMANCE.format(name="Kai"), bot.build_system(romance, "Kai", allow_nsfw=True))
        self.assertNotIn(bot._NSFW_ROMANCE.format(name="Kai"), bot.build_system(romance, "Kai"))

    def test_only_dms_and_age_restricted_channels_allow_it(self):
        guild = NS(id=1)
        self.assertTrue(bot._channel_allows_nsfw(None, is_dm=True))
        self.assertFalse(bot._channel_allows_nsfw(None))
        self.assertFalse(bot._channel_allows_nsfw(NS(guild=guild, is_nsfw=lambda: False)))
        self.assertTrue(bot._channel_allows_nsfw(NS(guild=guild, is_nsfw=lambda: True)))
        confirmed = {"nsfw_mode": True, "adult_confirmed": True}
        self.assertFalse(bot._unfiltered(confirmed, False))
        self.assertFalse(bot._unfiltered({"nsfw_mode": True}, True))
        self.assertFalse(bot._unfiltered({"adult_confirmed": True}, True))
        self.assertTrue(bot._unfiltered(confirmed, True))

    async def test_command_refuses_public_channels(self):
        ctx = make_ctx(5, guild_id=100)
        await bot.nsfw_cmd.callback(ctx, "on")
        self.assertIn("age-restricted", said(ctx))
        self.assertFalse((await self.mem.get_user(5))["nsfw_mode"])

    async def test_command_asks_for_an_18_plus_confirmation_first(self):
        ctx = make_ctx(5)  # a DM
        await bot.nsfw_cmd.callback(ctx, "on")
        self.assertIsInstance(ctx.reply.await_args.kwargs.get("view"), bot.AdultConfirmView)
        self.assertFalse((await self.mem.get_user(5))["nsfw_mode"])

    async def test_once_confirmed_the_command_works_in_age_restricted_channels(self):
        await self.mem.upsert_user(5, "user5", "user5")
        await self.mem.set_mode(5, "adult_confirmed", True)
        await bot.nsfw_cmd.callback(make_ctx(5, guild_id=100, nsfw=True), "on")
        self.assertTrue((await self.mem.get_user(5))["nsfw_mode"])

    async def test_the_confirmation_button_belongs_to_the_person_who_asked(self):
        await self.mem.upsert_user(5, "user5", "user5")
        button = bot.AdultConfirmView(5).children[0]

        def interaction(uid):
            return NS(user=NS(id=uid), response=NS(send_message=AsyncMock(), edit_message=AsyncMock(), is_done=lambda: False))

        stranger = interaction(6)
        await button.callback(stranger)
        stranger.response.send_message.assert_awaited_once()
        self.assertFalse((await self.mem.get_user(5))["adult_confirmed"])
        asker = interaction(5)
        await button.callback(asker)
        user = await self.mem.get_user(5)
        self.assertTrue(user["adult_confirmed"] and user["nsfw_mode"])


# ── !fixdoc (the owner's design from branch fix/wanderer-docfix-confirmation) ──────────────────────────────
class DocFixPendingTests(unittest.TestCase):
    def test_a_preview_is_bound_to_one_person_and_used_once(self):
        now = [100.0]
        pending = docfix_guard.DocFixPending(ttl_seconds=10, clock=lambda: now[0])
        token = pending.create(11, {"revision": "r-1", "revision_text": "good"})
        self.assertIsNone(pending.take(12, token))
        self.assertEqual(pending.take(11, token)["revision_text"], "good")
        self.assertIsNone(pending.take(11, token))

    def test_expiry_and_forget_prevent_a_later_overwrite(self):
        now = [100.0]
        pending = docfix_guard.DocFixPending(ttl_seconds=10, clock=lambda: now[0])
        token = pending.create(11, {"value": "one"})
        now[0] = 111.0
        self.assertIsNone(pending.take(11, token))
        token = pending.create(11, {"value": "two"})
        pending.forget(11)
        self.assertIsNone(pending.take(11, token))


class FixDocTests(BotTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.use(bot, "_DOCFIX_PENDING", docfix_guard.DocFixPending(ttl_seconds=600, limit=12))
        self.doc = {"doc_id": DOC_ID, "revision_id": "rev-1", "text": "My essay\nIt are good.", "title": "Essay"}
        self.written: list[tuple] = []
        self.use(bot, "google_docs_ready", lambda: (True, ""))
        self.use(bot, "fetch_google_doc", lambda link, **options: dict(self.doc))
        self.use(bot, "overwrite_google_doc", self._overwrite)
        self.use(bot, "_rewrite_google_doc_text", AsyncMock(side_effect=lambda name, text, instructions="": text.upper()))

    def _overwrite(self, link, text, *, required_revision_id=None):
        self.written.append((text, required_revision_id))
        return {"doc_id": DOC_ID, "title": "Essay", "chars_written": len(text)}

    async def test_only_the_operator_can_use_it(self):
        ctx = make_ctx(5)
        await bot._run_docfix_request(ctx, DOC)
        self.assertIn("limited to the bot operator", said(ctx))
        self.assertEqual(self.written, [])

    async def test_requests_and_confirmations_stay_in_a_dm(self):
        ctx = make_ctx(999, guild_id=100)
        await bot._run_docfix_request(ctx, DOC)
        self.assertIn("DM", said(ctx))
        self.assertEqual(self.written, [])

    async def test_nothing_is_written_until_the_exact_preview_is_confirmed(self):
        ctx = make_ctx(999)
        await bot._run_docfix_request(ctx, f"{DOC} fix the grammar")
        self.assertEqual(self.written, [])
        preview = ctx.author.send.await_args
        self.assertIn("file", preview.kwargs)
        token = re.search(r"!fixdoc confirm (\S+)`", preview.args[0]).group(1)
        await bot._run_docfix_request(make_ctx(999), f"confirm {token}")
        self.assertEqual(self.written, [("MY ESSAY\nIT ARE GOOD.", "rev-1")])
        again = make_ctx(999)
        await bot._run_docfix_request(again, f"confirm {token}")  # one use only
        self.assertIn("expired or was already used", said(again))
        self.assertEqual(len(self.written), 1)

    async def test_a_document_that_changed_after_the_preview_is_left_alone(self):
        ctx = make_ctx(999)
        await bot._run_docfix_request(ctx, DOC)
        token = re.search(r"!fixdoc confirm (\S+)`", ctx.author.send.await_args.args[0]).group(1)
        self.doc["revision_id"] = "rev-2"
        confirm = make_ctx(999)
        await bot._run_docfix_request(confirm, f"confirm {token}")
        self.assertIn("changed after your preview", said(confirm))
        self.assertEqual(self.written, [])

    async def test_the_worker_cannot_be_used_for_unreviewed_writes(self):
        self.use(bot, "google_docs_ready", lambda: (False, "no local credential"))
        ctx = make_ctx(999)
        await bot._run_docfix_request(ctx, DOC)
        self.assertIn("cannot safely confirm writes", said(ctx))
        self.assertEqual(self.written, [])

    def test_only_an_explicit_command_starts_an_edit(self):
        source = (ROOT / "bot.py").read_text()
        self.assertIn('raw_stripped.lower().startswith("!fixdoc ")', source)
        self.assertNotIn("and _looks_like_docfix_request(raw_stripped)", source)
        self.assertIn('"writeControl"] = {"requiredRevisionId": required_revision_id}', (ROOT / "google_docs_bridge.py").read_text())


# ── !memories and long replies ───────────────────────────────────────────────
class MemoriesCommandTests(BotTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.use(self.mem, "get_top_topics", AsyncMock(return_value=[]))
        self.use(self.mem, "get_memory_bank_entries", AsyncMock(return_value=[{"kind": "secret", "memory": "told you in a DM"}]))
        self.use(self.mem, "get_scene_state", AsyncMock(return_value=None))

    async def test_in_a_server_they_are_sent_privately(self):
        ctx = make_ctx(5, guild_id=100)
        await bot.memories_cmd.callback(ctx)
        self.assertIn("told you in a DM", ctx.author.send.await_args.args[0])
        self.assertNotIn("told you in a DM", said(ctx))

    async def test_closed_dms_are_no_reason_to_post_them_publicly(self):
        ctx = make_ctx(5, guild_id=100)
        ctx.author.send.side_effect = discord.Forbidden(NS(status=403, reason="Forbidden"), "Cannot send messages")
        await bot.memories_cmd.callback(ctx)
        self.assertNotIn("told you in a DM", said(ctx))
        self.assertIn("DMs are closed", said(ctx))

    async def test_in_a_dm_they_are_shown_directly(self):
        ctx = make_ctx(5)
        await bot.memories_cmd.callback(ctx)
        self.assertIn("told you in a DM", said(ctx))


class LongReplyTests(BotTestCase):
    TEXT = " ".join(f"word{i}" for i in range(900))  # about 6,000 characters

    def assert_delivered_in_pieces(self, ctx):
        pieces = [call.args[0] for call in ctx.reply.await_args_list + ctx.send.await_args_list]
        self.assertGreater(len(pieces), 1)
        self.assertTrue(all(len(piece) <= 2000 for piece in pieces))
        self.assertEqual(" ".join(pieces).split(), self.TEXT.split())

    async def test_safe_reply_splits_instead_of_failing(self):
        ctx = make_ctx(5)
        await bot.safe_reply(ctx, self.TEXT)
        ctx.reply.assert_awaited_once()
        self.assert_delivered_in_pieces(ctx)

    async def test_safe_send_splits_instead_of_failing(self):
        ctx = make_ctx(5)
        await bot.safe_send(ctx, self.TEXT)
        self.assert_delivered_in_pieces(ctx)


if __name__ == "__main__":
    unittest.main()
