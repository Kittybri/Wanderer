"""Mocked partner attribution and real Discord reply-routing contract."""
import asyncio
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
from partner_banter_routing import coherent_partner_reply, jealousy_context, safe_reference_name

ROOT = Path(__file__).resolve().parents[1]


def test_bystander_name_never_becomes_addressee():
    name = safe_reference_name("@deluluqueen")
    assert name == "deluluqueen"
    context = jealousy_context("Scaramouche", "deluluqueen")
    assert "PARTNER_SPEAKER: Scaramouche" in context
    assert "not the author of this message" in context
    assert coherent_partner_reply("Stop clinging to deluluqueen.", "Scaramouche", name) == "Stop clinging to deluluqueen."
    assert coherent_partner_reply("deluluqueen, be quiet.", "Scaramouche", name) == "deluluqueen, be quiet."
    assert coherent_partner_reply("Scaramouche, <@77> is listening.", "Scaramouche", name) == "Scaramouche, <@77> is listening."


def test_autoplay_uses_partner_or_human_message_reference():
    source = (ROOT / "bot.py").read_text()
    section = source.split("async def _duo_autoplay_loop():", 1)[1].split("async def _rival_event_loop():", 1)[0]
    assert "resolve_autoplay_anchor(" in section
    assert "partner_message = candidate" not in section
    assert "_guarded_message_reply(" in section
    assert "_guarded_channel_send(channel, reply)" not in section


def test_wanderer_reply_does_not_send_standalone_banter(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    import_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(import_loop)
    try:
        import bot
    finally:
        asyncio.set_event_loop(None)
        import_loop.close()

    async def run():
        user = NS(id=77, display_name="deluluqueen", mention="<@77>")
        message = NS(content="Tell me your worst opinion.", guild=NS(id=30),
                     channel=NS(id=20), author=NS(id=999, bot=True, mention="<@999>", display_name="Scaramouche"),
                     embeds=[], attachments=[], components=[], stickers=[])
        relation = {"last_exchange": 0, "stage": "competitive", "respect": 0, "tension": 0}
        monkeypatch.setattr(bot, "_observe_partner_message", AsyncMock(return_value=(relation, [], "rivalry")))
        monkeypatch.setattr(bot.mem, "get_duo_session", AsyncMock(return_value=None))
        monkeypatch.setattr(bot, "_find_romance_target", AsyncMock(return_value=user))
        monkeypatch.setattr(bot, "_contradictory_memory_context", AsyncMock(return_value=""))
        monkeypatch.setattr(bot, "detect_intervention_reason", lambda *_: None)
        monkeypatch.setattr(bot.random, "random", lambda: 0)
        ai = AsyncMock(return_value="Your worst opinion is that arrogance counts as insight.")
        monkeypatch.setattr(bot, "text_qai", ai)
        monkeypatch.setattr(bot, "_apply_phrase_policy", AsyncMock(side_effect=lambda r, *_a, **_kw: r))
        sent = AsyncMock(return_value=True)
        standalone = AsyncMock(return_value=True)
        monkeypatch.setattr(bot, "_guarded_message_reply", sent)
        monkeypatch.setattr(bot, "_guarded_channel_send", standalone)
        monkeypatch.setattr(bot.mem, "record_bot_banter", AsyncMock())
        monkeypatch.setattr(bot.mem, "update_bot_relationship", AsyncMock())
        monkeypatch.setattr(bot.mem, "note_shared_event_memory", AsyncMock())
        await bot._handle_partner_message(message, {
            "addressed_me": False, "duo_expected": False, "human_targets": [],
            "prompt_note": "Scaramouche was speaking in the channel.",
        })
        sent.assert_awaited_once()
        standalone.assert_not_awaited()
        assert sent.await_args.args[0] is message
        assert sent.await_args.args[1].startswith("<@999> Your worst opinion")
        assert sent.await_args.kwargs["mention_author"] is False
        assert [u.id for u in sent.await_args.kwargs["allowed_mentions"].users] == [999]
        prompt = ai.await_args.args[0]
        assert "PRIMARY ADDRESSEE: Scaramouche" in prompt and "deluluqueen" in prompt

    asyncio.run(run())
