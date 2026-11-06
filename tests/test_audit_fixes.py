"""Regression tests for the November 2026 audit fixes (Wanderer, voice line)."""
import asyncio
import os
import re
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import aiohttp
import pytest

import memory as memory_module
import narration
from integrations.http import AsyncJSONClient, IntegrationError
from test_release_hardening import load_runtime


@pytest.fixture
def env(monkeypatch, tmp_path):
    runtime, loop = load_runtime(monkeypatch, tmp_path)
    store = memory_module.Memory("wanderer")  # a fresh, empty database in tmp_path for this test
    loop.run_until_complete(store.init())
    monkeypatch.setattr(runtime, "mem", store)
    monkeypatch.setattr(runtime, "OWNER_ID", 999)
    try:
        yield NS(bot=runtime, loop=loop, mem=store, run=loop.run_until_complete)
    finally:
        loop.close()
        asyncio.set_event_loop(None)


class Typing:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def make_ctx(author_id=5, *, guild_id=None, members=None, age_restricted=False):
    guild = None
    if guild_id is not None:
        roster = members or {}
        guild = NS(id=guild_id, get_member=lambda uid: roster.get(uid))
    author = NS(id=author_id, name=f"user{author_id}", display_name=f"user{author_id}", bot=False,
                mention=f"<@{author_id}>", send=AsyncMock())
    channel = NS(id=9000 + author_id, guild=guild, **{"is_" + "ns" + "fw": lambda: age_restricted})
    return NS(author=author, guild=guild, channel=channel, reply=AsyncMock(), send=AsyncMock(), typing=Typing)


def said(ctx):
    calls = ctx.reply.await_args_list + ctx.send.await_args_list
    return "\n".join(str(call.args[0]) for call in calls if call.args)


def seed(env):
    """User 1 talks in a DM, in server 100 (channel 10) and in server 200 (channel 20)."""
    env.run(env.mem.track_channel(10, 100))
    env.run(env.mem.track_channel(20, 200))
    env.run(env.mem.add_message(1, 1, "user", "dm secret"))
    env.run(env.mem.add_message(1, 10, "user", "said in server A"))
    env.run(env.mem.add_message(1, 20, "user", "said in server B"))


# ── narration and mentions ───────────────────────────────────────────────────
@pytest.mark.parametrize("text", [
    "The answer is **42**.", "I do *not* care.", "f(x) = (x+1)^2", "See (page 4).",
    "Which god? [ANSWER: Raiden Shogun] [SOURCE: Archon Quest]",
    "Read https://en.wikipedia.org/wiki/Boiling_(disambiguation) first.", "They said the library closes at 9.",
])
def test_ordinary_content_survives_the_clean_up(env, text):
    assert env.bot.strip_narration(text) == text


def test_stage_directions_and_mass_pings_are_removed(env):
    assert env.bot.strip_narration("*sighs* Fine.") == "Fine."
    assert narration.strip_narration('Kunikuzushi sighed, "Fine."') == '"Fine."'
    assert env.bot.strip_narration('Kunikuzushi sighed, "Fine."') == "Fine."  # the bot also unwraps dialogue quotes
    cleaned = narration.strip_narration("@everyone hi @here <@&123>")
    assert "@everyone" not in cleaned and "@here" not in cleaned and not re.search(r"<@&\d+>", cleaned)
    assert env.bot.bot.allowed_mentions.everyone is False
    assert env.bot.bot.allowed_mentions.roles is False


def test_long_replies_are_split_instead_of_lost(env):
    ctx = make_ctx(5)
    text = " ".join(f"word{i}" for i in range(900))
    assert env.run(env.bot.safe_reply(ctx, text)) is True
    pieces = [call.args[0] for call in ctx.reply.await_args_list + ctx.send.await_args_list]
    assert len(pieces) > 1 and all(len(piece) <= 2000 for piece in pieces)
    assert " ".join(pieces).split() == text.split()


# ── unrestricted mode ────────────────────────────────────────────────────────
def test_unrestricted_prompt_needs_confirmation_and_a_suitable_place(env):
    user = {"unrestricted_mode": True, "romance_mode": False}
    marker = env.bot._UNRESTRICTED
    assert marker not in env.bot.build_system({**user, "adult_confirmed": True})
    assert marker not in env.bot.build_system(user, allow_unrestricted=True)
    assert marker in env.bot.build_system({**user, "adult_confirmed": True}, allow_unrestricted=True)
    public = NS(guild=object(), **{"is_" + "ns" + "fw": lambda: False})
    restricted = NS(guild=object(), **{"is_" + "ns" + "fw": lambda: True})
    assert env.bot._channel_allows_unrestricted(public) is False
    assert env.bot._channel_allows_unrestricted(restricted) is True
    assert env.bot._channel_allows_unrestricted(None, is_dm=True) is True


def test_unrestricted_command_refuses_public_channels_and_asks_for_18_plus(env, monkeypatch):
    set_mode = AsyncMock()
    monkeypatch.setattr(env.mem, "set_mode", set_mode)
    monkeypatch.setattr(env.bot, "_setup", AsyncMock(return_value={"unrestricted_mode": False}))
    public = make_ctx(5, guild_id=100)
    env.run(env.bot.bot.get_command("unrestricted").callback(public, "on"))
    assert "age-restricted" in said(public)
    dm = make_ctx(5)
    env.run(env.bot.bot.get_command("unrestricted").callback(dm, "on"))
    assert isinstance(dm.reply.await_args.kwargs.get("view"), env.bot.AdultConfirmView)
    set_mode.assert_not_awaited()


def test_the_confirmation_button_belongs_to_the_person_who_asked(env):
    env.run(env.mem.upsert_user(5, "user5", "user5"))

    async def press(uid):
        button = env.bot.AdultConfirmView(5).children[0]
        response = NS(send_message=AsyncMock(), edit_message=AsyncMock(), is_done=lambda: False)
        await button.callback(NS(user=NS(id=uid), response=response))
        return response

    stranger = env.run(press(6))
    stranger.send_message.assert_awaited_once()
    assert not env.run(env.mem.get_user(5))["adult_confirmed"]
    env.run(press(5))
    user = env.run(env.mem.get_user(5))
    assert user["adult_confirmed"] and user["unrestricted_mode"]


# ── privacy ──────────────────────────────────────────────────────────────────
def test_memory_scopes_leave_out_dms_and_other_servers(env):
    seed(env)
    assert env.run(env.mem.get_recent_messages(1, 10, guild_id=100)) == ["said in server A"]
    assert sorted(env.run(env.mem.get_recent_messages(1, 10, public_only=True))) == ["said in server A", "said in server B"]
    assert len(env.run(env.mem.get_recent_messages(1, 10))) == 3


def test_stalk_never_quotes_dms_or_other_servers(env, monkeypatch):
    seed(env)
    qai = AsyncMock(return_value="I've noticed things.")
    monkeypatch.setattr(env.bot, "qai", qai)
    env.run(env.bot.bot.get_command("stalk").callback(make_ctx(2, guild_id=100), NS(id=1, display_name="T", mention="<@1>")))
    prompt = qai.await_args.args[0]
    assert "said in server A" in prompt
    assert "dm secret" not in prompt and "said in server B" not in prompt


def test_progress_reads_his_own_replies_from_this_server(env, monkeypatch):
    seed(env)
    for channel, text in ((10, "reply in server A"), (1, "reply in our DM"), (20, "reply in server B")):
        env.run(env.mem.add_message(1, channel, "assistant", text))
    qai = AsyncMock(return_value="I've been better.")
    monkeypatch.setattr(env.bot, "qai", qai)
    env.run(env.bot.bot.get_command("progress").callback(make_ctx(1, guild_id=100)))
    prompt = qai.await_args.args[0]
    assert "reply in server A" in prompt and "said in server A" not in prompt
    assert "reply in our DM" not in prompt and "reply in server B" not in prompt


def test_rank_counts_only_this_servers_messages(env, monkeypatch):
    seed(env)
    for _ in range(5):
        env.run(env.mem.add_message(3, 20, "user", "busy elsewhere"))
    members = {uid: NS(id=uid, display_name=f"member{uid}", bot=False) for uid in (1, 3)}
    ctx = make_ctx(1, guild_id=100, members=members)
    monkeypatch.setattr(env.bot, "qai", AsyncMock(return_value="Fine."))
    env.run(env.bot.bot.get_command("rank").callback(ctx))
    description = ctx.send.await_args.kwargs["embed"].description
    assert "member1" in description and "member3" not in description


def test_memories_in_a_server_are_sent_privately(env, monkeypatch):
    monkeypatch.setattr(env.mem, "get_top_topics", AsyncMock(return_value=[]))
    monkeypatch.setattr(env.mem, "get_memory_bank_entries", AsyncMock(return_value=[{"kind": "secret", "memory": "told you in a DM"}]))
    monkeypatch.setattr(env.mem, "get_scene_state", AsyncMock(return_value=None))
    monkeypatch.setattr(env.bot, "_setup", AsyncMock(return_value={}))
    ctx = make_ctx(5, guild_id=100)
    env.run(env.bot.bot.get_command("memories").callback(ctx))
    assert "told you in a DM" in ctx.author.send.await_args.args[0]
    assert "told you in a DM" not in said(ctx)


# ── render worker ────────────────────────────────────────────────────────────
def test_the_worker_fails_closed_and_only_takes_voice_settings(monkeypatch):
    import video_render_worker as worker

    monkeypatch.setattr(worker, "VIDEO_RENDER_SECRET", "")
    assert worker._authorized({}) is False
    monkeypatch.setattr(worker, "VIDEO_RENDER_SECRET", "s" * 32)
    assert worker._authorized({"X-Render-Secret": "s" * 32}) is True
    assert worker._authorized({"X-Render-Secret": "wrong"}) is False
    cleaned = worker._clean_env_overrides({"FISH_AUDIO_API_KEY": "k", "PATH": "/tmp/evil", "LD_PRELOAD": "x.so"})
    assert cleaned == {"FISH_AUDIO_API_KEY": "k"}
    if not os.getenv("VIDEO_RENDER_HOST"):
        assert worker.VIDEO_RENDER_HOST == "127.0.0.1"


# ── connected-account HTTP client ────────────────────────────────────────────
class _Session:
    def __init__(self, calls, error):
        self.calls, self.error = calls, error

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def request(self, method, url, **kwargs):
        self.calls.append(method)
        raise self.error


@pytest.mark.parametrize("method,attempts", [("POST", 1), ("PATCH", 1), ("GET", 2), ("DELETE", 2)])
def test_requests_that_may_have_been_carried_out_are_not_repeated(method, attempts):
    calls = []
    client = AsyncJSONClient(session_factory=lambda **kwargs: _Session(calls, asyncio.TimeoutError()), sleep=AsyncMock())
    with pytest.raises(IntegrationError):
        asyncio.run(client.request(method, "https://example.invalid/x"))
    assert len(calls) == attempts  # a timed-out POST may already have created the calendar event


def test_a_refused_connection_is_retried_for_every_method():
    calls = []
    error = aiohttp.ClientConnectorError(NS(ssl=None, host="example.invalid", port=443), OSError("refused"))
    client = AsyncJSONClient(session_factory=lambda **kwargs: _Session(calls, error), sleep=AsyncMock())
    with pytest.raises(IntegrationError):
        asyncio.run(client.request("POST", "https://example.invalid/x"))
    assert len(calls) == 2


def test_documents_are_parsed_in_the_isolated_reader():
    source = open(os.path.join(os.path.dirname(__file__), "..", "bot.py"), encoding="utf-8").read()
    assert "pdfplumber.open" not in source and "_docx.Document(" not in source and "_Prs(" not in source
    assert source.count("doc_extract.extract_text_isolated(") >= 4


def test_memory_imports_random_itself():
    assert hasattr(memory_module, "random")  # mood swings used to rely on bot.py patching it in
