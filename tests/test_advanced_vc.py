import asyncio
import json
import sqlite3
import time
from collections import Counter
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock

import pytest

from voice_conversation.features import AdvancedVC, VoiceFeatureRouter
from voice_conversation.personality import (
    VoiceEvent,
    Handoff,
    interruption_kind,
    interruption_context,
    parody,
    safe_parody,
    priority_status,
    handoff_context,
)
from voice_conversation.social_store import SocialStore, PREFERENCES
from voice_conversation.games import Games, QUESTIONS, PUZZLES


def run(coro):
    return asyncio.run(coro)


async def setup(tmp_path, name="scaramouche"):
    mem = NS(
        db_path=str(tmp_path / (name + ".db")),
        shared_db_path=str(tmp_path / "shared.db"),
        get_duo_session=AsyncMock(return_value=None),
        clear_duo_session=AsyncMock(),
        bump_duo_session=AsyncMock(),
        set_duo_session=AsyncMock(),
    )
    with sqlite3.connect(mem.db_path) as db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS user_preferences(user_id INTEGER PRIMARY KEY, voice_enabled INTEGER DEFAULT 1)"
        )
    bot = NS(
        get_guild=Mock(),
        fetch_channel=AsyncMock(),
        get_channel=Mock(),
        is_closed=lambda: False,
    )
    service = NS(
        name=name,
        mem=mem,
        sessions={},
        send=AsyncMock(),
        bot=bot,
        leave=AsyncMock(),
        command=AsyncMock(),
    )
    cfg = {
        "guilds": {
            "5": {
                "enabled": True,
                "allowed_voice_channels": [10],
                "allowed_game_channels": [20],
                "features": {
                    k: True
                    for k in (
                        "mockingbird",
                        "duo",
                        "interrogate",
                        "escape",
                        "soundboard",
                        "awareness",
                    )
                },
            }
        }
    }
    owner = AdvancedVC(service, cfg)
    await owner.store.init()
    session = NS(
        channel_id=10,
        participants={1},
        active=True,
        initiator=1,
        state=NS(value="LISTENING"),
        current_user=1,
        busy=lambda: False,
        submit=AsyncMock(return_value=True),
        cancel_response=AsyncMock(),
        generation=0,
        metrics=Counter(),
    )
    owner.attach(session, 5)
    service.sessions[5] = session
    return owner, session


async def optin(owner, uid=1):
    for key in PREFERENCES:
        await owner.store.preference(uid, key, True)


def test_preferences_default_off_and_migration_preserves(tmp_path):
    async def check():
        owner, _ = await setup(tmp_path)
        assert not any((await owner.store.preferences(1)).values())
        await owner.store.preference(1, PREFERENCES[0], True)
        await SocialStore(owner.mem, owner.name).init()
        assert (await owner.store.preferences(1))[PREFERENCES[0]]
        with sqlite3.connect(owner.mem.db_path) as db:
            assert (
                db.execute(
                    "SELECT voice_enabled FROM user_preferences WHERE user_id=1"
                ).fetchone()[0]
                == 1
            )

    run(check())


def test_budget_atomic_shared_and_social_isolation(tmp_path):
    async def check():
        owner, _ = await setup(tmp_path)
        other, _ = await setup(tmp_path, "wanderer")
        outcomes = await asyncio.gather(
            *(owner.store.budget(5, 1, "mock", days=7) for _ in range(8))
        )
        assert sum(outcomes) == 1
        assert not await other.store.budget(5, 2, "sound")
        await owner.store.remember(1, 5, "left_during_speech")
        assert await owner.store.recall(1, 5) == ["left_during_speech"]
        assert not await owner.store.recall(2, 5)
        assert not await other.store.recall(1, 5)
        await owner.store.preference(1, PREFERENCES[0], False)
        assert not await owner.store.recall(1, 5)

    run(check())


@pytest.mark.parametrize(
    "text",
    [
        "My password is abc",
        "my address is here",
        "I want to die",
        "we should kill the boss",
        "my boss pays money",
        "my boss gave me a diagnosis",
        "my boss says I am a criminal",
        "my boss and my sex life",
        "<@123456> game",
        "send token https://example.com",
    ],
)
def test_mock_sensitive_exclusion(text):
    assert not safe_parody(text)
    assert not parody("scaramouche", text)


def test_mock_uses_actual_text_character_voice_and_cooldown(tmp_path):
    async def check():
        owner, s = await setup(tmp_path)
        r = s.feature_router
        text = "Guys, maybe we should fight the boss first."
        assert safe_parody(text)
        await r.handle_event(VoiceEvent("utterance_completed", 1, text))
        assert not r.last and not await r.mock(1)
        await optin(owner)
        r.mock_mode = "MANUAL"
        await r.handle_event(VoiceEvent("utterance_completed", 2, text))
        assert 2 not in r.last
        await r.handle_event(VoiceEvent("utterance_completed", 1, text))
        reply = await r.mock(1)
        assert text in reply and "revolutionary" in reply
        await r.handle_event(VoiceEvent("utterance_completed", 1, text))
        assert not await r.mock(1)
        assert parody("wanderer", text) != reply
        r.revoke(1)
        assert not r.last

    run(check())


@pytest.mark.parametrize(
    "text,count,kind",
    [
        ("sorry, go ahead", 4, "accidental_overlap"),
        ("wait", 1, "normal"),
        ("haha, kidding", 1, "playful"),
        ("stop talking", 3, "repeated_deliberate"),
        ("shut up idiot", 1, "hostile"),
        ("stop this is serious", 8, "urgent"),
        ("wait I actually need help", 3, "urgent"),
    ],
)
def test_interruption_classification(text, count, kind):
    assert interruption_kind(text, count) == kind
    assert interruption_context("scaramouche", kind) != ""


def test_router_meaningful_memory_only_and_urgent(tmp_path):
    async def check():
        owner, s = await setup(tmp_path)
        await optin(owner)
        r = s.feature_router
        await r.handle_event(VoiceEvent("bot_interrupted", 1))
        result = await r.handle_event(VoiceEvent("utterance_completed", 1, "wait"))
        assert "normal" in result["context"]
        assert not await owner.store.recall(1, 5)
        await r.handle_event(VoiceEvent("bot_interrupted", 1))
        result = await r.handle_event(
            VoiceEvent("utterance_completed", 1, "Stop, this is serious")
        )
        assert "URGENT" in result["context"] and "reply" not in result
        assert not await owner.store.recall(1, 5)
        await r.handle_event(VoiceEvent("user_left", 1, data={"addressing": False}))
        assert not await owner.store.recall(1, 5)
        await r.handle_event(VoiceEvent("user_left", 1, data={"addressing": True}))
        assert "left_during_speech" in await owner.store.recall(1, 5)

    run(check())


def test_cache_ttl_and_stop(tmp_path):
    async def check():
        owner, s = await setup(tmp_path)
        r = s.feature_router
        r.last[1] = ("game", time.monotonic() - 1)
        r.arrivals = {1: time.monotonic() - 50}
        r.prune()
        assert not r.last and not r.arrivals
        await r.handle_event(VoiceEvent("session_stopped", 0))
        assert not r.interruptions

    run(check())


@pytest.mark.parametrize("allowed", [True, False])
def test_priority_is_permission_not_activation(allowed):
    value = priority_status(
        NS(permissions_for=lambda member: NS(priority_speaker=allowed)), NS()
    )
    assert value["permission"] == allowed
    assert value["activation"] == "not_implemented"
    assert priority_status(None, None)["activation"] == "unavailable"


def test_handoff_personalities_protective_override():
    assert "practical helper" in handoff_context("wanderer", Handoff.CORRECT, "game")
    assert "sharp, theatrical critic" in handoff_context(
        "scaramouche", Handoff.DISAGREE, "game"
    )
    assert "defuse" in handoff_context("scaramouche", Handoff.DISAGREE, "urgent help")


def test_duo_output_scoped_and_presence_expiry(tmp_path):
    async def check():
        owner, s = await setup(tmp_path)
        await owner.store.duo_output(10, 1, "Only what was spoken")
        assert await owner.store.duo_output(10, 1, partner="scaramouche")
        assert not await owner.store.duo_output(10, 2, partner="scaramouche")
        await owner.store.presence(10, [1])
        assert await owner.store.partner_ready("scaramouche", 10, 1)
        assert not await owner.store.partner_ready("scaramouche", 10, 2)
        await owner.store.presence(10, [])
        assert not await owner.store.partner_ready("scaramouche", 10, 1)

    run(check())


def test_game_receipts_bounds_restart(tmp_path):
    async def check():
        owner, s = await setup(tmp_path)
        game = await owner.store.create_game(
            5, {"participants": [1], "kind": "escape"}, 100
        )
        with pytest.raises(ValueError):
            await owner.store.create_game(5, {}, 100)
        restarted = SocialStore(owner.mem, owner.name)
        assert (await restarted.games())[0]["id"] == game["id"]
        game["state"] = "cancelled"
        await owner.store.save_game(game)
        with pytest.raises(ValueError):
            await owner.store.create_game(5, {}, 100)  # pending cleanup still blocks
        await owner.store.delete_game(game["id"])
        assert not await restarted.games()

    run(check())


def test_game_transcripts_not_saved_and_question_cap(tmp_path):
    async def check():
        owner, s = await setup(tmp_path)
        game = await owner.store.create_game(
            5,
            {
                "participants": [1],
                "accepted": [1],
                "kind": "interrogate",
                "channel": 10,
                "question_index": 0,
            },
            120,
        )
        game["state"] = "active"
        await owner.store.save_game(game)
        assert await owner.games.utterance(s, 2) == ""
        assert await owner.games.utterance(s, 1) == QUESTIONS[owner.name][1]
        assert await owner.games.utterance(s, 1) == QUESTIONS[owner.name][2]
        assert "adjourned" in await owner.games.utterance(s, 1)
        assert await owner.games.utterance(s, 1) == ""
        stored = (await owner.store.games())[0]
        assert stored["state"] == "finishing" and "answers" not in stored

    run(check())


def test_restore_only_if_still_in_owned_room_and_retains_failures(tmp_path):
    async def check():
        owner, s = await setup(tmp_path)
        game = await owner.store.create_game(
            5,
            {
                "participants": [1],
                "kind": "interrogate",
                "channel": 30,
                "original": 10,
                "parent": 20,
                "notified": False,
            },
            120,
        )
        original = NS(id=10)
        target = NS(id=1, bot=False, voice=NS(channel=NS(id=30)), move_to=AsyncMock())
        guild = NS(
            id=5,
            get_member=lambda uid: target,
            get_channel=lambda cid: original if cid == 10 else NS(send=AsyncMock()),
        )
        room = NS(
            id=30,
            guild=guild,
            name="vc-game-" + game["id"],
            members=[target],
            delete=AsyncMock(),
        )
        owner.service.bot.get_guild.return_value = guild
        owner.service.bot.fetch_channel.return_value = room
        await owner.games.cleanup(game)
        target.move_to.assert_awaited_once_with(
            original, reason="Restore after voluntary game"
        )
        room.delete.assert_not_awaited()
        target.voice.channel = NS(id=99)  # manual departure: never chase them
        room.members = []
        await owner.games.cleanup(game)
        assert target.move_to.await_count == 1
        room.delete.assert_awaited_once()
        assert not await owner.store.games()

    run(check())


def test_escape_answer_hint_cancel_access_boundaries(tmp_path):
    async def check():
        owner, s = await setup(tmp_path)
        game = await owner.store.create_game(
            5,
            {
                "kind": "escape",
                "participants": [1],
                "accepted": [1],
                "channel": 30,
                "parent": 20,
                "attempts": 0,
                "puzzle": PUZZLES[0],
            },
            600,
        )
        game["state"] = "active"
        await owner.store.save_game(game)
        ctx = NS(
            guild=NS(id=5),
            author=NS(id=2, guild_permissions=NS(manage_channels=False)),
            channel=NS(id=30),
        )
        with pytest.raises(ValueError):
            await owner.games.command(ctx, "answer", game["id"] + " 32")
        ctx.author.id = 1
        ctx.channel.id = 20
        with pytest.raises(ValueError):
            await owner.games.command(ctx, "answer", game["id"] + " 32")
        ctx.channel.id = 30
        await owner.games.command(ctx, "hint", game["id"])
        assert (await owner.store.games())[0]["state"] == "hint_requested"
        await owner.games.command(ctx, "answer", game["id"] + " wrong")
        assert (await owner.store.games())[0]["attempts"] == 1
        owner.games.cleanup = AsyncMock()
        await owner.games.command(ctx, "answer", game["id"] + " 32")
        assert (await owner.store.games())[0]["state"] == "solved"
        owner.games.cleanup.assert_awaited_once()
        # Exercise failure/cancel transitions without creating another Discord
        # thread: cleanup is deliberately mocked to retain this receipt.
        game["state"], game["attempts"] = "active", 0
        await owner.store.save_game(game)
        for _ in range(5):
            await owner.games.command(ctx, "answer", game["id"] + " wrong")
        assert (await owner.store.games())[0]["state"] == "failed"
        await owner.games.command(ctx, "cancel", "")
        assert (await owner.store.games())[0]["state"] == "cancelled"

    run(check())


def test_optout_works_disabled_and_forget_clears_output(tmp_path):
    async def check():
        owner, s = await setup(tmp_path)
        await optin(owner)
        await owner.store.duo_output(10, 1, "a delivered line")
        await owner.store.remember(1, 5, "left_during_speech")
        s.feature_router.last[1] = ("game", time.monotonic() + 30)
        owner.config = {}
        await owner.command(NS(guild=None, author=NS(id=1)), "off", "")
        assert not (await owner.store.preferences(1))[PREFERENCES[0]]
        assert not await owner.store.recall(1, 5)
        assert not await owner.store.duo_output(10, 1, partner=owner.name)
        assert not s.feature_router.last
        s.cancel_response.assert_awaited_once()

    run(check())


def test_accidents_do_not_build_deliberate_streak(tmp_path):
    async def check():
        owner, s = await setup(tmp_path)
        await optin(owner)
        router = s.feature_router
        for text in ["sorry, go ahead"] * 4 + ["stop talking"]:
            await router.handle_event(VoiceEvent("bot_interrupted", 1))
            await router.handle_event(VoiceEvent("utterance_completed", 1, text))
        assert not await owner.store.recall(1, 5)
        for _ in range(2):
            await router.handle_event(VoiceEvent("bot_interrupted", 1))
            await router.handle_event(
                VoiceEvent("utterance_completed", 1, "stop talking")
            )
        assert "repeated_interruptions" in await owner.store.recall(1, 5)
        assert len(router.interruptions[1]) <= 6

    run(check())


def test_real_arrival_and_focused_departure_only(tmp_path):
    async def check():
        owner, s = await setup(tmp_path)
        await optin(owner)
        member = NS(id=1, bot=False, guild=NS(id=5))
        await owner.arrival(s, 5, 1)
        s.submit.assert_not_awaited()
        await owner.voice_state(member, NS(channel=None), NS(channel=NS(id=10)))
        await owner.arrival(s, 5, 1)
        s.submit.assert_awaited_once()
        await owner.arrival(s, 5, 1)
        assert s.submit.await_count == 1
        s.state.value = "BOT_SPEAKING"
        await owner.voice_state(member, NS(channel=NS(id=10)), NS(channel=None))
        assert "left_during_speech" in await owner.store.recall(1, 5)
        await owner.store.forget(1)
        member.bot = True
        await owner.voice_state(member, NS(channel=NS(id=10)), NS(channel=None))
        assert not await owner.store.recall(1, 5)

    run(check())


def test_sound_authorized_asset_cooldown_no_overlap(tmp_path):
    async def check():
        owner, s = await setup(tmp_path)
        await optin(owner)
        owner.sound_guilds = {5}
        # This existing test source stands in for an approved byte asset; no TTS.
        owner.assets = lambda: {"scoff": __file__}
        s.busy = lambda: True
        assert not await owner.sound(s, 5, 1, "scoff")
        s.busy = lambda: False
        assert not await owner.sound(s, 5, 1, "unapproved")
        assert await owner.sound(s, 5, 1, "scoff")
        assert s.submit.call_args.kwargs["feature_kind"] == "soundboard"
        assert not await owner.sound(s, 5, 1, "scoff")

    run(check())


def test_structured_duo_claim_atomic_and_offline_fails_closed(tmp_path):
    async def check():
        owner, s = await setup(tmp_path)
        await optin(owner)
        with sqlite3.connect(owner.mem.shared_db_path) as db:
            db.execute(
                "CREATE TABLE duo_sessions(channel_id INTEGER PRIMARY KEY, mode TEXT, topic TEXT, initiator_user_id INTEGER, autoplay_remaining INTEGER, awaiting_bot TEXT, next_autoplay_ts REAL, expires_ts REAL)"
            )
            db.execute(
                "INSERT INTO duo_sessions VALUES (10, 'vc:disagree', 'game', 1, 2, 'scaramouche', 0, ?)",
                (time.time() + 120,),
            )
        claims = await asyncio.gather(*(owner.store.claim_duo(10) for _ in range(5)))
        assert sum(bool(c) for c in claims) == 1
        owner.mem.get_duo_session.return_value = dict(
            mode="vc:disagree", topic="game", initiator_user_id=1
        )
        await owner.duo_tick(s, 5)
        owner.mem.clear_duo_session.assert_awaited_once_with(10)
        s.submit.assert_not_awaited()

    run(check())


def test_duo_delivered_turn_advances_once_and_cancel_stops(tmp_path):
    async def check():
        owner, s = await setup(tmp_path)
        owner.mem.get_duo_session.return_value = dict(
            mode="vc:agree", topic="game", initiator_user_id=1
        )
        task = asyncio.create_task(asyncio.sleep(0))
        await task
        owner.duo_pending[10] = (task, 0, 0, "game")
        s.metrics["spoken_chunks"] = 1
        await owner.duo_tick(s, 5)
        owner.mem.bump_duo_session.assert_awaited_once()
        assert not owner.duo_pending
        owner.duo_pending[10] = (task, 0, 0, "game")
        s.generation = 1
        await owner.duo_tick(s, 5)
        owner.mem.clear_duo_session.assert_awaited_once_with(10)
        assert owner.mem.bump_duo_session.await_count == 1

    run(check())


def game_context(owner):
    # Hashable members are required for actual discord.PermissionOverwrite keys.
    class Member:
        def __init__(self, uid):
            self.id, self.bot = uid, False
            self.voice = NS(channel=NS(id=10))
            self.guild_permissions = NS(manage_channels=True, move_members=True)
            self.move_to = AsyncMock()

    requester, target, bot_member = Member(1), Member(2), Member(9)
    members = {1: requester, 2: target, 9: bot_member}
    parent = NS(id=20, create_thread=AsyncMock(), send=AsyncMock())
    guild = NS(
        id=5,
        voice_client=None,
        me=bot_member,
        default_role=object(),
        get_member=members.get,
        get_channel=lambda cid: parent if cid == 20 else NS(id=10),
        create_voice_channel=AsyncMock(),
        voice_channels=[],
        active_threads=AsyncMock(return_value=[]),
    )
    ctx = NS(
        guild=guild,
        author=requester,
        channel=parent,
        message=NS(mentions=[target]),
        reply=AsyncMock(),
    )
    owner.service.bot.get_guild.return_value = guild
    return ctx, target, parent


def test_interrogation_no_room_or_move_before_consent(tmp_path):
    async def check():
        owner, _ = await setup(tmp_path)
        owner.service.sessions.clear()
        ctx, target, parent = game_context(owner)
        await owner.games.command(ctx, "interrogate", "")
        ctx.guild.create_voice_channel.assert_not_awaited()
        target.move_to.assert_not_awaited()
        game = (await owner.store.games())[0]
        assert not game["accepted"]
        with pytest.raises(ValueError):
            await owner.games.command(ctx, "accept", game["id"])
        room = NS(
            id=30,
            name="vc-game-" + game["id"],
            guild=ctx.guild,
            members=[],
            delete=AsyncMock(),
        )
        ctx.guild.create_voice_channel.return_value = room
        owner.service.bot.fetch_channel.return_value = room

        async def move(channel, **kwargs):
            target.voice.channel = channel

        target.move_to.side_effect = move
        # Start fails closed (unavailable receive). Consent still precedes move;
        # durable recovery restores the original channel, then removes the room.
        ctx.author = target
        with pytest.raises(ValueError):
            await owner.games.command(ctx, "accept", game["id"])
        assert target.move_to.await_count == 2
        assert target.move_to.await_args_list[0].args[0].id == 30
        assert target.move_to.await_args_list[1].args[0].id == 10
        assert (await owner.store.games())[0]["state"] == "cancelled"
        await owner.games.tick(recovery=True)
        room.delete.assert_awaited_once()
        assert not await owner.store.games()

    run(check())


def test_escape_accept_creates_private_thread_and_restart_timeout(tmp_path):
    async def check():
        owner, _ = await setup(tmp_path)
        ctx, target, parent = game_context(owner)
        thread = NS(
            id=30,
            guild=ctx.guild,
            add_user=AsyncMock(),
            send=AsyncMock(),
            edit=AsyncMock(),
        )
        parent.create_thread.return_value = thread
        await owner.games.command(ctx, "escape", "")
        parent.create_thread.assert_not_awaited()
        game = (await owner.store.games())[0]
        thread.name = "vc-game-" + game["id"]
        ctx.author = target
        await owner.games.command(ctx, "accept", game["id"])
        assert parent.create_thread.call_args.kwargs["invitable"] is False
        assert str(parent.create_thread.call_args.kwargs["type"]) == "private_thread"
        assert thread.add_user.await_count == 2
        assert target.move_to.await_count == 0
        await owner.games.tick(recovery=True)
        game = (await owner.store.games())[0]
        assert game["state"] == "active"
        game["expires"] = time.time() - 1
        await owner.store.save_game(game)
        owner.service.bot.fetch_channel.return_value = thread
        await owner.games.tick()
        thread.edit.assert_awaited_once_with(
            archived=True, reason="Voluntary puzzle game ended"
        )
        assert not await owner.store.games()

    run(check())


def test_cleanup_permission_failure_keeps_journal_notifies_once(tmp_path):
    async def check():
        import discord

        owner, _ = await setup(tmp_path)
        ctx, target, parent = game_context(owner)
        game = await owner.store.create_game(
            5, dict(kind="escape", participants=[1], channel=30, parent=20), 100
        )
        owner.service.bot.fetch_channel.side_effect = discord.Forbidden(
            NS(status=403, reason="Forbidden"), "not permitted"
        )
        await owner.games.cleanup(game)
        await owner.games.cleanup(game)
        assert len(await owner.store.games()) == 1
        parent.send.assert_awaited_once()

    run(check())


def test_crash_between_creation_and_journal_id_recovers_exact_room(tmp_path):
    async def check():
        owner, _ = await setup(tmp_path)
        owner.service.sessions.clear()
        ctx, target, parent = game_context(owner)
        game = await owner.store.create_game(
            5,
            dict(
                kind="interrogate",
                participants=[2],
                accepted=[2],
                channel=0,
                original=10,
                parent=20,
                creation_started=True,
            ),
            100,
        )
        game["state"] = "creating"
        await owner.store.save_game(game)
        room = NS(
            id=30,
            guild=ctx.guild,
            name="vc-game-" + game["id"],
            created_at=NS(timestamp=lambda: time.time()),
            members=[],
            delete=AsyncMock(),
        )
        ctx.guild.voice_channels = [room]
        await owner.games.tick(recovery=True)
        room.delete.assert_awaited_once()
        target.move_to.assert_not_awaited()  # target was never moved before crash
        assert not await owner.store.games()

    run(check())


def test_feature_output_rechecks_consent_after_tts(tmp_path):
    async def check():
        from test_voice_conversation import setup as live_session

        owner, _ = await setup(tmp_path)
        s = live_session()
        owner.attach(s, 5)
        await optin(owner)
        s.feature_router.mock_mode = "MANUAL"

        async def synthesize(uid, text):
            await owner.store.preference(uid, "mockingbird_enabled", False)
            return b"audio"

        s.synthesize = synthesize
        assert await s.submit(
            1, "", reply="A harmless game parody.", feature_kind="mockingbird"
        )
        await s.response_task
        s.respond.assert_not_awaited()
        s.playback.play.assert_not_awaited()
        s.remember.assert_not_awaited()
        await s.stop()

    run(check())


def test_sound_playback_cancellable_in_foundation(tmp_path):
    async def check():
        from test_voice_conversation import setup as live_session

        owner, _ = await setup(tmp_path)
        s = live_session()
        owner.attach(s, 5)
        await optin(owner)
        started = asyncio.Event()

        async def play(audio):
            started.set()
            await asyncio.Event().wait()

        s.playback.play.side_effect = play
        assert await s.submit(1, "", audio=b"authorized", feature_kind="soundboard")
        await asyncio.wait_for(started.wait(), 2)
        await s.cancel_response()
        s.playback.stop.assert_awaited_once()
        s.synthesize.assert_not_awaited()
        s.remember.assert_not_awaited()
        await s.stop()

    run(check())


def test_real_coordinator_caps_two_turns_and_text_cannot_consume(tmp_path):
    async def check():
        from memory import Memory

        mem = Memory.__new__(Memory)
        mem.bot_name, mem._muted = "scaramouche", {}
        mem.db_path, mem.shared_db_path = str(tmp_path / "real.db"), str(
            tmp_path / "duo.db"
        )
        await mem.init()
        await mem.set_duo_session(
            10,
            "vc:agree",
            "game",
            "scaramouche",
            initiator_user_id=1,
            awaiting_bot="scaramouche",
            autoplay_turns=2,
            autoplay_delay=2,
            ttl_seconds=90,
        )
        await mem.bump_duo_session(10, "scaramouche", partner_bot="wanderer")
        assert (await mem.get_duo_session(10))["autoplay_remaining"] == 2
        await mem.bump_duo_session(
            10, "scaramouche", partner_bot="wanderer", voice_turn=True
        )
        turn = await mem.get_duo_session(10)
        assert turn["autoplay_remaining"] == 1 and turn["awaiting_bot"] == "wanderer"
        await mem.bump_duo_session(
            10, "wanderer", partner_bot="scaramouche", voice_turn=True
        )
        turn = await mem.get_duo_session(10)
        assert turn["autoplay_remaining"] == 0 and not turn["awaiting_bot"]
        store = SocialStore(mem, "scaramouche")
        await store.init()
        assert not await store.claim_duo(10)

    run(check())


def test_serious_game_input_ends_questions_without_parody(tmp_path):
    async def check():
        owner, s = await setup(tmp_path)
        game = await owner.store.create_game(
            5,
            dict(
                kind="interrogate",
                participants=[1],
                accepted=[1],
                channel=10,
                question_index=0,
            ),
            120,
        )
        game["state"] = "active"
        await owner.store.save_game(game)
        plan = await s.feature_router.handle_event(
            VoiceEvent("utterance_completed", 1, "Wait, I actually need help")
        )
        assert (
            plan["force_reply"] and "URGENT" in plan["context"] and "reply" not in plan
        )
        assert not await owner.games.utterance(s, 1)
        assert (await owner.store.games())[0]["state"] == "finishing"

    run(check())


def test_router_gets_complete_continuation_once(tmp_path):
    async def check():
        from test_voice_conversation import setup as live_session
        from voice_conversation.speech import Utterance

        s = live_session()
        s.stt.transcribe.side_effect = [
            "Scaramouche, maybe",
            "this is serious, I need help",
        ]
        observed = []

        async def event(kind, uid=0, text="", data=None):
            if kind == "utterance_completed":
                observed.append(text)
                s.active = False  # stop after routing, no provider work in this test
            return {}

        s.feature_event = event
        now = time.monotonic()
        # Follow-up audio is separate: each segment transcribed only once.
        s.jobs.put_nowait(Utterance(1, b"first", now - 1, now, s.epochs[1]))
        s.jobs.put_nowait(Utterance(1, b"second", now + 0.1, now + 0.2, s.epochs[1]))
        await asyncio.wait_for(s.transcribe_loop(), 2)
        assert observed == ["Scaramouche, maybe this is serious, I need help"]
        assert s.stt.transcribe.await_count == 2
        s.respond.assert_not_awaited()
        await s.stop()

    run(check())


def test_listening_optout_ends_game_even_if_member_stays(tmp_path):
    async def check():
        owner, s = await setup(tmp_path)
        ctx, target, parent = game_context(owner)
        game = await owner.store.create_game(
            5,
            dict(
                kind="interrogate",
                participants=[2],
                accepted=[2],
                channel=10,
                original=10,
                parent=20,
            ),
            120,
        )
        game["state"] = "active"
        await owner.store.save_game(game)
        owner.games.cleanup = AsyncMock()
        s.participants.clear()
        await owner.games.tick()
        owner.games.cleanup.assert_awaited_once()
        assert (await owner.store.games())[0]["state"] == "cancelled"

    run(check())
