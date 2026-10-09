"""Text policy tests: synthetic inputs, no provider/Discord network calls."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from response_quality import (
    FAILURE_NOTICE, ReplyKind, allows_short_reply, classify_reply, final_response,
    human_mentions_bot, internal_instruction, recover_response, repeated_answer,
    trim_repeated_opener,
)


@pytest.mark.parametrize("prompt", [
    "Explain photosynthesis", "Translate hello to French", "Why?", "What is 2+2?",
    "I feel overwhelmed and need advice", "Compare our personality traits",
    "<@1> <@2> define my personality traits and compare which animation character fits me most",
])
def test_substantive_prompts_reject_empty_acknowledgments(prompt):
    assert not allows_short_reply(prompt)
    for bad in ("...", "Fine.", "Tch.", "Honestly.", ""):
        assert final_response(bad, prompt) == FAILURE_NOTICE


@pytest.mark.parametrize("prompt", ["Hello", "Wanderer, thanks!", "<@1> nice hat", "go on", "one-word answer please"])
def test_contextual_short_replies(prompt):
    assert allows_short_reply(prompt)
    assert classify_reply("Fine.", prompt) == ReplyKind.SHORT_REPLY


@pytest.mark.parametrize("line", [
    "Start where you actually mean to start.", "Say what you mean.",
    "Try that again without the recycled opener.", "I am listening. Briefly.",
    "Use a different opening and cadence.", "Please revise your response.",
    "INTERNAL REVISION: return only the answer.", "Avoid the stale opener.",
])
def test_internal_language_never_substitutes_for_an_answer(line):
    assert internal_instruction(line)
    assert final_response(line, "Translate hello") == FAILURE_NOTICE


def test_shared_opening_is_not_a_repeated_answer():
    old = "I think your strongest traits are creativity and patience."
    new = "I think your strongest traits are curiosity, humor, and persistence; you keep asking useful questions."
    assert not repeated_answer(new, [old])
    assert repeated_answer(old + "!", [old])


def test_stale_interjection_keeps_substance_without_inventing_an_opener():
    assert trim_repeated_opener("Hmph. Paris is the capital of France.", ["Hmph. Fine."]) == "Paris is the capital of France."
    assert trim_repeated_opener("Hmph.", ["Hmph. Fine."]) == "Hmph."
    assert final_response("Hmph.", "What is the capital of France?") == FAILURE_NOTICE
    assert final_response("Paris.", "What is the capital of France?") == "Paris."


@pytest.mark.parametrize("drafts,recent,expected,calls", [
    (["Paris."], [], "Paris.", 1),
    (["", "Paris."], [], "Paris.", 2),
    ([RuntimeError("synthetic"), "Paris."], [], "Paris.", 2),
    (["Paris is the capital.", ""], ["Paris is the capital."], "Paris is the capital.", 2),
    (["Paris is the capital.", "Paris is the capital."], ["Paris is the capital."], "Paris is the capital.", 2),
    (["Say what you mean.", ""], [], FAILURE_NOTICE, 2),
    ([RuntimeError("synthetic"), RuntimeError("synthetic")], [], FAILURE_NOTICE, 2),
])
def test_bounded_recovery_preserves_a_valid_answer(drafts, recent, expected, calls):
    generate = AsyncMock(side_effect=drafts)
    result = asyncio.run(recover_response(generate, "What is the capital of France?", recent))
    assert result.text == expected
    assert generate.await_count == calls == result.attempts
    if calls == 2:
        assert "original request" in generate.call_args.args[0]


def test_exhausted_direct_requests_get_notice_without_provider_calls():
    generate = AsyncMock()
    for _ in range(3):
        result = asyncio.run(recover_response(generate, "Why?", [], exhausted=lambda: True))
        assert result.kind == ReplyKind.FAILURE
        assert result.text == FAILURE_NOTICE
    generate.assert_not_called()
    ambient = asyncio.run(recover_response(generate, "background", [], exhausted=lambda: True, direct=False))
    assert ambient.kind == ReplyKind.SILENCE and not ambient.text


def test_both_mentions_belong_to_the_human_event_not_partner_reply():
    message = SimpleNamespace(author=SimpleNamespace(bot=False), mentions=[SimpleNamespace(id=1), SimpleNamespace(id=2)])
    assert human_mentions_bot(message, 1)
    assert human_mentions_bot(message, 2)
    partner = SimpleNamespace(author=SimpleNamespace(bot=True), mentions=[SimpleNamespace(id=1)])
    assert not human_mentions_bot(partner, 1)
    message.mentions = [SimpleNamespace(id=2)]
    assert not human_mentions_bot(message, 1)
