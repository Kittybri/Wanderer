import asyncio
from pathlib import Path
import sqlite3
from unittest.mock import AsyncMock

from awareness_features import credential_disclosure
from anti_repeat import is_fallback_reply
import memory as memory_module
from memory import Memory
from privacy_deletion import PrivacyDeletionCoordinator
from provider_config import resolve_groq_model


def run(coro):
    return asyncio.run(coro)


def test_credential_guard_is_narrow_and_catches_obvious_disclosures():
    assert credential_disclosure("password: hunter22")
    assert credential_disclosure("API key is gsk_123456789012345678901234")
    assert credential_disclosure("-----BEGIN PRIVATE KEY-----")
    assert not credential_disclosure("Should I use a password manager?")
    assert not credential_disclosure("The word token appears in this sentence.")


def test_retired_groq_models_resolve_before_any_provider_call():
    assert resolve_groq_model("llama-3.3-70b-versatile") == "openai/gpt-oss-120b"
    assert resolve_groq_model("llama-3.1-8b-instant") == "openai/gpt-oss-20b"
    assert resolve_groq_model("llama-3.2-90b-vision-preview") == "qwen/qwen3.8-27b"
    assert resolve_groq_model("custom/account-model") == "custom/account-model"

    source = (Path(__file__).parents[1] / "bot.py").read_text()
    assert 'model="llama-3.2-90b-vision-preview"' not in source
    assert "GROQ_MODEL_PRIMARY = GROQ_TEXT_MODEL" in source


def test_internal_fallbacks_are_detectable_and_protective_path_bypasses_self_edit():
    assert is_fallback_reply("wanderer", "Try that again without the recycled opener.")
    assert not is_fallback_reply("wanderer", "Take one slow breath, then choose one task.")

    source = (Path(__file__).parents[1] / "bot.py").read_text()
    response = source[source.index("async def get_response"):source.index("async def _web_search_groq")]
    assert "protective_input = safety.protective" in response
    assert "if not protective_input and not rate_limited" in response
    assert "is_fallback_reply(BOT_NAME, reply)" in response


def test_proactive_rivalry_rejects_sensitive_channel_topics():
    source = (Path(__file__).parents[1] / "bot.py").read_text()
    topic_picker = source[
        source.index("async def _recent_rival_topic"):
        source.index("def _is_in_quiet_hours")
    ]
    assert "credential_disclosure(content)" in topic_picker
    assert "classify_safety(content).protective" in topic_picker
    assert "is_sensitive_memory(content)" in topic_picker


def test_release_pipeline_guards_credentials_and_distress_before_optional_bits():
    source = (Path(__file__).parents[1] / "bot.py").read_text()
    handler = source[source.index("async def _handle_message_pipeline"):]
    assert handler.index("credential_disclosure(raw_stripped)") < handler.index(
        "await bot.process_commands(message)"
    )
    assert handler.index("command_name in PROTECTIVE_BLOCKED_COMMANDS") < handler.index(
        "await bot.process_commands(message)"
    )
    assert handler.index("if safety.protective:") < handler.index(
        "increment_message_count(message.author.id)"
    )
    protective = handler[handler.index("if safety.protective:"):]
    assert protective.index("if await _guarded_message_reply(") < protective.index(
        'await mem.add_message(\n                    message.author.id, dm_channel_id, "assistant"'
    )


def test_partner_command_output_cannot_trigger_unsolicited_banter():
    source = (Path(__file__).parents[1] / "bot.py").read_text()
    handler = source[
        source.index("async def _handle_partner_message"):
        source.index("async def _partner_message_target_info")
    ]
    ownership_gate = handler.index('if not target_info.get("addressed_me") and not target_info.get("duo_expected")')
    observation = handler.index("await _observe_partner_message(message.content)")
    assert ownership_gate < observation
    assert 'if target_info.get("human_targets"):' in handler
    assert 'getattr(message, "embeds", None)' in handler


def test_assistant_state_is_committed_only_after_successful_delivery():
    source = (Path(__file__).parents[1] / "bot.py").read_text()

    reply_helper = source[
        source.index("async def _reply_and_store(ctx"):
        source.index("async def _reply_and_store_interaction")
    ]
    assert "if not await safe_reply(ctx, text):" in reply_helper
    assert reply_helper.index("if not await safe_reply(ctx, text):") < reply_helper.index(
        'await mem.add_message(ctx.author.id, ctx.channel.id, "assistant", text)'
    )

    interaction_helper = source[
        source.index("async def _reply_and_store_interaction"):
        source.index("def _format_memory_snapshot")
    ]
    assert "if not await _interaction_reply(interaction, text, thinking=False):" in interaction_helper
    assert interaction_helper.index("if not await _interaction_reply") < interaction_helper.index(
        'await mem.add_message(interaction.user.id, interaction.channel_id, "assistant", text)'
    )

    handler = source[source.index("async def _handle_message_pipeline"):]
    video = handler[handler.index("if reply:\n                            reply = strip_narration(reply)"):]
    assert video.index("if not await _guarded_message_reply(message, reply):") < video.index(
        '"user", f"[video]'
    )
    image = handler[handler.index("# ── Image handling"):]
    assert image.index("if not await _guarded_message_reply(message, reply):") < image.index(
        '"user", f"[image]'
    )
    invite = handler[handler.index("if direct_to_me and _is_partner_invite_request(content):"):]
    assert invite.index("if not await _guarded_message_reply(message, reply, view=invite_view):") < invite.index(
        'await mem.add_message(message.author.id, dm_channel_id, "assistant", reply)'
    )


def test_background_replies_do_not_advance_memory_or_cooldowns_on_send_failure():
    source = (Path(__file__).parents[1] / "bot.py").read_text()
    assert "if await _guarded_message_reply(message, line):\n            await mem.add_message" in source
    assert "if not await _guarded_channel_send(message.channel, line):\n                return" in source
    assert "if await _guarded_channel_send(ch, f\"{m.mention} {msg}\"):\n                                    await mem.add_message" in source
    assert "if await _guarded_channel_send(ch, msg):\n                            await mem.set_proactive_sent(cid)" in source
    assert "if await safe_reply(ctx, text_reply):\n                await mem.add_message" in source


def test_full_memory_reset_removes_user_scopes_and_preserves_other_user(tmp_path):
    memory = Memory("wanderer")
    memory.db_path = str(tmp_path / "wanderer.db")
    memory.shared_db_path = str(tmp_path / "shared.db")
    memory_module.DB_PATH = memory.db_path
    run(memory.init())

    with sqlite3.connect(memory.db_path) as db:
        for uid in (1, 10):
            db.execute("INSERT INTO users(user_id) VALUES(?)", (uid,))
            db.execute("INSERT INTO reminders(user_id,reminder) VALUES(?,?)", (uid, f"r{uid}"))
            db.execute("INSERT INTO consequence_marks(user_id,summary) VALUES(?,?)", (uid, f"c{uid}"))
            db.execute("INSERT INTO user_preferences(user_id) VALUES(?)", (uid,))
            db.execute("INSERT INTO rpg_state(user_id) VALUES(?)", (uid,))
            db.execute("INSERT INTO blocked_dm_users(user_id) VALUES(?)", (uid,))
            db.execute(
                "INSERT INTO relationship_milestones(scope,marker) VALUES(?,?)",
                (f"wanderer:user:{uid}", f"m{uid}"),
            )
            db.execute(
                "INSERT INTO phrase_cooldowns(scope,phrase_key) VALUES(?,?)",
                (f"wanderer:soft:user:{uid}", f"p{uid}"),
            )
    with sqlite3.connect(memory.shared_db_path) as db:
        for uid in (1, 10):
            db.execute("INSERT INTO shared_users(user_id) VALUES(?)", (uid,))
            db.execute("INSERT INTO user_bot_attention(user_id,bot_name) VALUES(?,'wanderer')", (uid,))
            db.execute("INSERT INTO duo_sessions(channel_id,initiator_user_id) VALUES(?,?)", (uid + 100, uid))
            db.execute("INSERT INTO face_profiles(profile_key,owner_user_id) VALUES(?,?)", (f"f{uid}", uid))
            db.execute("INSERT INTO shared_evidence_locker(evidence_key,owner_user_id) VALUES(?,?)", (f"e{uid}", uid))
            db.execute(
                "INSERT INTO hidden_achievements(scope,achievement_key) VALUES(?,?)",
                (f"user:{uid}", f"a{uid}"),
            )
            db.execute(
                "INSERT INTO relationship_milestones(scope,marker) VALUES(?,?)",
                (f"shared:user:{uid}", f"s{uid}"),
            )
            db.execute(
                "INSERT INTO interbot_private_opinions(scope,bot_name,subject_type,subject_key) "
                "VALUES(?,'wanderer','user',?)", (f"user:{uid}", str(uid)),
            )

    run(memory.reset_user(1))
    with sqlite3.connect(memory.db_path) as db:
        for table in (
            "users", "reminders", "consequence_marks", "user_preferences",
            "rpg_state", "blocked_dm_users",
        ):
            assert db.execute(
                f"SELECT COUNT(*) FROM {table} WHERE user_id=1"
            ).fetchone()[0] == 0
            assert db.execute(
                f"SELECT COUNT(*) FROM {table} WHERE user_id=10"
            ).fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM relationship_milestones WHERE scope='wanderer:user:10'").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM phrase_cooldowns WHERE scope='wanderer:soft:user:10'").fetchone()[0] == 1
    with sqlite3.connect(memory.shared_db_path) as db:
        assert db.execute("SELECT COUNT(*) FROM shared_users WHERE user_id=1").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM shared_users WHERE user_id=10").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM duo_sessions WHERE initiator_user_id=1").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM duo_sessions WHERE initiator_user_id=10").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM face_profiles WHERE owner_user_id=1").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM face_profiles WHERE owner_user_id=10").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM hidden_achievements WHERE scope='user:10'").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM relationship_milestones WHERE scope='shared:user:10'").fetchone()[0] == 1


def test_privacy_deletion_retries_only_the_unfinished_stage(tmp_path):
    memory = Memory("wanderer")
    memory.db_path = str(tmp_path / "wanderer.db")
    memory.shared_db_path = str(tmp_path / "shared.db")
    memory_module.DB_PATH = memory.db_path
    run(memory.init())
    first_stage = AsyncMock()
    offline = AsyncMock(side_effect=RuntimeError("offline"))
    coordinator = PrivacyDeletionCoordinator(
        memory.db_path, {"local": first_stage, "companion": offline}
    )

    first = run(coordinator.run(42))
    assert first.status == "RETRYABLE"
    assert first.pending_stage == "companion"
    assert run(coordinator.is_pending(42)) is True

    resumed = AsyncMock()
    restarted = PrivacyDeletionCoordinator(
        memory.db_path, {"local": AsyncMock(), "companion": resumed}
    )
    second = run(restarted.run(42))
    assert second.complete
    restarted.stages["local"].assert_not_awaited()
    resumed.assert_awaited_once_with(42)
    assert run(restarted.is_pending(42)) is False


def test_rebuild_reset_does_not_delete_prefix_neighbor_scope(tmp_path):
    memory = Memory("wanderer")
    memory.db_path = str(tmp_path / "wanderer.db")
    memory.shared_db_path = str(tmp_path / "shared.db")
    memory_module.DB_PATH = memory.db_path
    run(memory.init())
    with sqlite3.connect(memory.db_path) as db:
        for uid in (1, 10):
            db.execute("INSERT INTO users(user_id) VALUES(?)", (uid,))
            db.execute(
                "INSERT INTO relationship_milestones(scope,marker) VALUES(?,?)",
                (f"wanderer:user:{uid}", f"m{uid}"),
            )
    with sqlite3.connect(memory.shared_db_path) as db:
        for uid in (1, 10):
            db.execute(
                "INSERT INTO relationship_milestones(scope,marker) VALUES(?,?)",
                (f"shared:user:{uid}", f"m{uid}"),
            )

    run(memory.reset_user_for_rebuild(1))

    with sqlite3.connect(memory.db_path) as db:
        assert db.execute("SELECT COUNT(*) FROM relationship_milestones WHERE scope='wanderer:user:1'").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM relationship_milestones WHERE scope='wanderer:user:10'").fetchone()[0] == 1
    with sqlite3.connect(memory.shared_db_path) as db:
        assert db.execute("SELECT COUNT(*) FROM relationship_milestones WHERE scope='shared:user:1'").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM relationship_milestones WHERE scope='shared:user:10'").fetchone()[0] == 1
