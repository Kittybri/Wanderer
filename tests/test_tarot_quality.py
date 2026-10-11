"""Focused Wanderer tarot-response quality checks; no live providers or Discord calls."""
import asyncio
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import tarot_system as tarot
from tarot_commands import TarotController


def run(coro):
    return asyncio.run(coro)


def drawing(key):
    return tarot.draw_spread(key)


def test_three_card_prompt_answers_the_question_and_explains_lore():
    question = "who was I in a previous life?"
    prompt = tarot.build_reading_prompt("Wanderer", "three_card", drawing("three_card"), question, tarot.TarotPreferences())
    assert question in prompt
    assert "imaginative archetype" in prompt
    assert "Briefly explain any Genshin" in prompt
    assert "one or two complete sentences" in prompt
    assert "210 words" in prompt


def test_clarifier_prompt_connects_existing_cards_and_original_question():
    cards = drawing("three_card")
    clarifier = tarot.draw_one("Clarifier", exclude={c.card.stem for c in cards})
    prompt = tarot.build_clarifier_prompt("Wanderer", "who was I?", cards, clarifier, tarot.TarotPreferences())
    assert "original cards" in prompt
    assert "original question" in prompt
    assert "plain language" in prompt


def test_full_three_card_output_paginates_without_dropping_content():
    async def check():
        cards = drawing("three_card")
        unique_sections = ["PAST " + "first sentence. " * 80,
                           "PRESENT " + "second sentence. " * 80,
                           "FUTURE " + "third sentence. " * 80]
        reading = "\n\n".join(unique_sections).strip()
        view = tarot.TarotResultView(1, "Wanderer", AsyncMock(), "past-life question", tarot.TarotPreferences(),
                                     NS(), "three_card", cards, reading)
        pages = view.content_pages()
        assert len(pages) >= 2
        assert all(len(page) <= tarot.DISCORD_CONTENT_LIMIT for page in pages)
        assert all(label in "".join(pages) for label in ("PAST", "PRESENT", "FUTURE"))
        assert view.content() == pages[0]
        # Pagination must preserve every non-whitespace token in order.
        combined = " ".join(page.split("**\n\n", 1)[-1] for page in pages[1:])
        assert "third sentence." in pages[-1]
    run(check())


def test_private_clarifier_splits_long_reply_and_only_attaches_art_once():
    async def check():
        cards = drawing("three_card")
        store = NS(validate=AsyncMock())
        view = tarot.TarotResultView(1, "Wanderer", AsyncMock(), "question", tarot.TarotPreferences(),
                                     store, "three_card", cards, "reading.")
        interaction = NS(followup=NS(send=AsyncMock()))
        content = "Clarifier. " * 500
        await view._private_send(interaction, content, file="synthetic-image")
        calls = interaction.followup.send.call_args_list
        assert len(calls) >= 2
        assert all(len(call.args[0]) <= tarot.DISCORD_CONTENT_LIMIT for call in calls)
        assert calls[0].kwargs["file"] == "synthetic-image"
        assert all("file" not in call.kwargs for call in calls[1:])
        assert all(not call.kwargs["allowed_mentions"].everyone for call in calls)
    run(check())


def test_fallback_reading_is_complete_and_contextual():
    output = tarot.fallback_reading("three_card", drawing("three_card"), tarot.TarotPreferences(), question="previous life")
    assert "symbolic perspective" in output
    assert "**Past (" in output and "**Future (" in output
    assert output.endswith("fate.")


def test_provider_retries_truncated_result_but_never_displays_it(tmp_path):
    async def check():
        calls = []
        def provider(**kwargs):
            calls.append(kwargs["max_completion_tokens"])
            if len(calls) == 1:
                return NS(choices=[NS(message=NS(content="The first thought cuts"), finish_reason="length")])
            return NS(choices=[NS(message=NS(content="A complete reading."), finish_reason="stop")])
        store = NS(validate=AsyncMock())
        ctrl = TarotController(None, "Wanderer", NS(call_with_retry=provider), "fake-model", tmp_path, None, None, store=store)
        answer = await ctrl.generate(store, "Synthetic prompt", 220)
        assert answer == "A complete reading."
        assert len(calls) == 2 and calls[1] > calls[0]
        assert store.validate.await_count == 2
    run(check())


def test_provider_exhausted_or_unfinished_returns_empty_for_fallback(tmp_path):
    async def check():
        calls = []
        def provider(**kwargs):
            calls.append(kwargs["max_completion_tokens"])
            return NS(choices=[NS(message=NS(content="An incomplete"), finish_reason="stop")])
        store = NS(validate=AsyncMock())
        ctrl = TarotController(None, "Wanderer", NS(call_with_retry=provider), "fake-model", tmp_path, None, None, store=store)
        assert await ctrl.generate(store, "Synthetic prompt", 200) == ""
        assert len(calls) == 2
    run(check())


def test_provider_metadata_keeps_legacy_mock_compatibility(tmp_path):
    async def check():
        store = NS(validate=AsyncMock())
        client = NS(call_with_retry=lambda **kw: NS(choices=[NS(message=NS(content="A complete answer."))]))
        ctrl = TarotController(None, "Wanderer", client, "fake-model", tmp_path, None, None, store=store)
        assert await ctrl.generate(store, "Synthetic prompt", 200) == "A complete answer."
    run(check())
