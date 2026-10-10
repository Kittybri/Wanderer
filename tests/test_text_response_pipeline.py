"""Exercise actual runtime entry points with isolated SQLite and fake providers."""
import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import pytest
from test_release_hardening import load_runtime
from response_quality import FAILURE_NOTICE


@pytest.mark.parametrize("direct", [True, False])
def test_quick_text_keeps_technical_vocabulary(runtime, monkeypatch, direct):
    mod, loop, _ = runtime
    answer = "Retry the request after a short delay."
    monkeypatch.setattr(mod, "_text_quick_blocking", lambda *args: answer)
    assert loop.run_until_complete(mod.text_qai("Explain retrying", direct=direct)) == answer


def test_successful_technical_rewrite_is_kept(runtime, monkeypatch):
    mod, loop, user = runtime
    answer = "Retry transient failures with exponential backoff."
    monkeypatch.setattr(mod, "_self_edit_issues", lambda *a, **k: ["too generic"])
    monkeypatch.setattr(mod, "_text_rewrite_reply_once", AsyncMock(return_value=answer))
    result = loop.run_until_complete(mod._text_self_edit_reply(
        "Try once more.", recent_replies=[], user_message="Explain retries", user=user))
    assert result == answer


@pytest.mark.parametrize("direct,expected", [(False, ""), (True, FAILURE_NOTICE)])
def test_quick_text_failure_distinguishes_ambient_from_direct(runtime, monkeypatch, direct, expected):
    mod, loop, _ = runtime
    monkeypatch.setattr(mod, "_text_quick_blocking", lambda *args: "Try that again without the recycled opener.")
    assert loop.run_until_complete(mod.text_qai("Explain why ice floats", direct=direct)) == expected


def test_unsent_failure_does_not_post_or_keep_pending_state(runtime, monkeypatch):
    mod, loop, _ = runtime
    monkeypatch.setattr(mod.asyncio, "sleep", AsyncMock())
    generate = AsyncMock(return_value="")
    monkeypatch.setattr(mod, "text_qai", generate)
    send = AsyncMock()
    monkeypatch.setattr(mod, "_guarded_channel_send", send)
    mod._pending_unsent.add(202)
    loop.run_until_complete(mod._unsent_simulation(NS(id=202), 202))
    assert generate.call_args.kwargs["direct"] is False
    send.assert_not_awaited()
    assert 202 not in mod._pending_unsent


def test_background_and_partner_text_routes_use_checked_recovery():
    import ast
    from pathlib import Path
    tree = ast.parse((Path(__file__).parents[1] / "bot.py").read_text())
    names = {"_handle_partner_message", "_unsent_simulation", "_proactive_loop", "_voluntary_dm_loop", "_rival_event_loop"}
    checked = set()
    for function in tree.body:
        if not isinstance(function, ast.AsyncFunctionDef) or function.name not in names:
            continue
        calls = [node for node in ast.walk(function) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)]
        assert not any(node.func.id == "qai" for node in calls)
        generated = [node for node in calls if node.func.id == "text_qai"]
        assert generated
        assert all(any(kw.arg == "direct" and isinstance(kw.value, ast.Constant) and kw.value.value is False for kw in node.keywords) for node in generated)
        for node in calls:
            if node.func.id == "_apply_phrase_policy":
                assert any(kw.arg == "preserve_content" and isinstance(kw.value, ast.Constant) and kw.value.value is True for kw in node.keywords)
        checked.add(function.name)
    assert checked == names


@pytest.fixture
def runtime(monkeypatch, tmp_path):
    mod, loop = load_runtime(monkeypatch, tmp_path)
    import memory
    store = memory.Memory("wanderer")
    store.db_path = str(tmp_path / "wanderer.db")
    store.shared_db_path = str(tmp_path / "shared.db")
    monkeypatch.setattr(mod, "mem", store)
    loop.run_until_complete(store.init())
    loop.run_until_complete(store.upsert_user(101, "synthetic", "Synthetic"))
    monkeypatch.setattr(mod.WORLD, "response_context", AsyncMock(side_effect=lambda uid, cid, text, user: (user, "")))
    monkeypatch.setattr(mod.WORLD, "observe", AsyncMock())
    monkeypatch.setattr(mod, "_grounded_search_bundle", AsyncMock(return_value=("", "")))
    monkeypatch.setattr(mod, "_recent_reply_samples", AsyncMock(return_value=[]))
    monkeypatch.setattr(mod, "_recent_text_pressure", AsyncMock(return_value={}))
    monkeypatch.setattr(mod, "_current_time_context", lambda *a: "Synthetic time")
    monkeypatch.setattr(mod, "_text_rewrite_reply_once", AsyncMock(return_value=""))
    monkeypatch.setattr(mod.groq_client, "is_exhausted", lambda: False)
    monkeypatch.setattr(mod, "remember_output", lambda *a: None)
    monkeypatch.setattr(mod.random, "random", lambda: .99)
    yield mod, loop, loop.run_until_complete(store.get_user(101))
    loop.close()
    asyncio.set_event_loop(None)


@pytest.mark.parametrize("prompt,answer", [
    ("What is the capital of France?", "Paris."),
    ("Translate hello to French", "Bonjour."),
    ("Why does that happen?", "Water vapor cools and condenses into droplets."),
    ("I'm overwhelmed and need help planning one task", "Pick one small task and put the rest aside for now."),
    ("Hi", "Hello. What brings you here?"),
    ("How do I recover from a network timeout?", "Retry the request after a short delay."),
    ("What is a system prompt?", "A system prompt provides instructions to the assistant."),
])
def test_actual_text_generation_keeps_question_and_answer(runtime, monkeypatch, prompt, answer):
    mod, loop, user = runtime
    generate = AsyncMock(return_value=answer)
    monkeypatch.setattr(mod, "_text_groq_call", generate)
    reply = loop.run_until_complete(mod.get_text_response(101, 202, prompt, user, "Synthetic", "<@101>", defer_delivery=True))
    assert reply == answer
    generate.assert_awaited_once()
    assert prompt in generate.call_args.args[0][-1]["content"]
    assert generate.call_args.kwargs["route"] in {"primary", "light"}
    assert not loop.run_until_complete(mod.mem.get_history(101, 202))[-1]["role"] == "assistant"


@pytest.mark.parametrize("drafts,expected", [
    (["", "Paris."], "Paris."),
    (["Say what you mean.", "Paris."], "Paris."),
    ([RuntimeError("synthetic"), RuntimeError("synthetic")], FAILURE_NOTICE),
    (["", ""], FAILURE_NOTICE),
])
def test_actual_pipeline_retries_bounded_and_never_leaks(runtime, monkeypatch, drafts, expected):
    mod, loop, user = runtime
    generate = AsyncMock(side_effect=drafts)
    monkeypatch.setattr(mod, "_text_groq_call", generate)
    reply = loop.run_until_complete(mod.get_text_response(101, 202, "What is the capital of France?", user, "Synthetic", "<@101>"))
    assert reply == expected
    assert generate.await_count == 2
    assert mod._text_rewrite_reply_once.await_count == 0
    assert "What is the capital of France?" in generate.call_args.args[0][-1]["content"]


def test_actual_pipeline_exhaustion_and_search_failure(runtime, monkeypatch):
    mod, loop, user = runtime
    generate = AsyncMock()
    monkeypatch.setattr(mod, "_text_groq_call", generate)
    monkeypatch.setattr(mod.groq_client, "is_exhausted", lambda: True)
    for _ in range(2):
        assert loop.run_until_complete(mod.get_text_response(101, 202, "Explain rain", user, "Synthetic", "<@101>")) == FAILURE_NOTICE
    generate.assert_not_awaited()
    monkeypatch.setattr(mod.groq_client, "is_exhausted", lambda: False)
    monkeypatch.setattr(mod, "_grounded_search_bundle", AsyncMock(side_effect=RuntimeError("synthetic search unavailable")))
    assert loop.run_until_complete(mod.get_text_response(101, 202, "What is today's news?", user, "Synthetic", "<@101>", use_search=True)) == FAILURE_NOTICE
    generate.assert_not_awaited()


def test_actual_pipeline_keeps_repeated_draft_when_second_is_empty(runtime, monkeypatch):
    mod, loop, user = runtime
    answer = "Paris is the capital of France."
    monkeypatch.setattr(mod, "_recent_reply_samples", AsyncMock(return_value=[answer]))
    generate = AsyncMock(side_effect=[answer, ""])
    monkeypatch.setattr(mod, "_text_groq_call", generate)
    assert loop.run_until_complete(mod.get_text_response(101, 202, "What is the capital of France?", user, "Synthetic", "<@101>")) == answer
    assert generate.await_count == 2


@pytest.mark.parametrize("allowed,raises", [(True, False), (False, False), (True, True)])
def test_send_outcome_distinguishes_policy_denial_and_discord_failure(runtime, monkeypatch, allowed, raises):
    mod, loop, _ = runtime
    reply = AsyncMock(side_effect=RuntimeError("synthetic send failure") if raises else None)
    message = NS(reply=reply)
    monkeypatch.setattr(mod, "_is_banned_channel_target", lambda _: not allowed)
    monkeypatch.setattr(mod, "_pace_discord_send", AsyncMock())
    monkeypatch.setattr(mod, "_remember_recent_message", lambda _: None)
    assert loop.run_until_complete(mod._guarded_message_reply(message, "Paris.")) is (allowed and not raises)
    assert reply.await_count == int(allowed)


@pytest.mark.parametrize("both,partner_first,send_fails", [(False, False, False), (True, False, False), (True, True, False), (True, True, True)])
def test_human_message_pipeline_keeps_independent_ownership(runtime, monkeypatch, both, partner_first, send_fails):
    mod, loop, user = runtime
    me = NS(id=301, bot=True)
    partner = NS(id=302, bot=True)
    monkeypatch.setattr(mod.bot._connection, "user", me)
    monkeypatch.setattr(mod, "PARTNER_BOT_ID", partner.id)
    monkeypatch.setattr(mod, "_owner_only_mode", False)
    monkeypatch.setattr(mod, "_dm_blocked_users", set())
    monkeypatch.setattr(mod, "_banned_channels", set())
    monkeypatch.setattr(mod, "_processed_msgs", set())
    monkeypatch.setattr(mod, "FISH_AUDIO_API_KEY", "")
    monkeypatch.setattr(mod.bot, "get_context", AsyncMock(return_value=NS(valid=False, command=None)))
    monkeypatch.setattr(mod.bot, "process_commands", AsyncMock())
    monkeypatch.setattr(mod.PRIVACY_DELETION, "is_pending", AsyncMock(return_value=False))
    for name in ("_pace_discord_send", "typing_delay", "_record_tattletale_if_eligible", "_maybe_refresh_dynamic_nicknames", "_maybe_schedule_private_confession_scene", "maybe_react"):
        monkeypatch.setattr(mod, name, AsyncMock())
    monkeypatch.setattr(mod, "_remember_recent_message", lambda _: None)
    monkeypatch.setattr(mod, "_load_face_attachment", AsyncMock(return_value=(None, None)))
    monkeypatch.setattr(mod, "_medium_awareness_context", AsyncMock(return_value=[]))
    monkeypatch.setattr(mod, "_attachment_context_for_message", AsyncMock(return_value=""))
    monkeypatch.setattr(mod, "_maybe_handle_silence_behavior", AsyncMock(return_value=False))
    monkeypatch.setattr(mod, "_status_check_reply", lambda *a, **k: "")
    monkeypatch.setattr(mod, "_prefer_voice_for_reply", lambda *a, **k: False)
    generate = AsyncMock(return_value="Curiosity and persistence show in those questions.")
    monkeypatch.setattr(mod, "get_text_response", generate)

    @asynccontextmanager
    async def typing():
        yield

    async def history(**kwargs):
        if partner_first:
            yield NS(author=partner, embeds=[], content="A prior partner answer.")

    guild = NS(id=404, members=[], get_member=lambda uid: partner if uid == partner.id else None)
    channel = NS(id=202, guild=guild, history=history, typing=typing)
    author = NS(id=101, name="synthetic", display_name="Synthetic", mention="<@101>", bot=False)
    reply = AsyncMock(side_effect=RuntimeError("synthetic send error") if send_fails else None)
    message = NS(id=505, author=author, guild=guild, channel=channel,
                 content="<@301> " + ("<@302> " if both else "") + "define my personality traits and compare which animation character fits me most",
                 mentions=[me, partner] if both else [me], reference=None, attachments=[], embeds=[], reply=reply)
    loop.run_until_complete(mod._handle_message_pipeline(message))
    generate.assert_awaited_once()
    assert generate.call_args.kwargs["direct_to_me"] is True
    reply.assert_awaited_once()
    history_rows = loop.run_until_complete(mod.mem.get_history(101, 202))
    assert any(row["role"] == "assistant" for row in history_rows) is not send_fails
