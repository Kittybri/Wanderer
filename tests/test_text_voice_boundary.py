"""Lock the original voice semantics to release 537bc0d, not a new expectation.

Project explicit text-policy flags to False, then compare the ENTIRE remaining
function AST with the pre-repair release. This covers prompts, provider routes,
fallbacks, anti-repeat, memory/defer semantics and all return/error paths.
"""
import ast
import asyncio
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from test_release_hardening import load_runtime
from response_quality import FAILURE_NOTICE

ROOT = Path(__file__).parents[1]
BASELINE = json.loads((ROOT / "tests/voice_response_baseline.json").read_text())


class LegacyProjection(ast.NodeTransformer):
    FLAGS = {"_text_policy", "text_policy", "preserve_content"}

    def visit_Name(self, node):
        return ast.Constant(False) if node.id in self.FLAGS else node

    def visit_arguments(self, node):
        pairs = [(arg, default) for arg, default in zip(node.kwonlyargs, node.kw_defaults) if arg.arg not in self.FLAGS]
        node.kwonlyargs = [arg for arg, _ in pairs]
        node.kw_defaults = [default for _, default in pairs]
        return node

    def visit_Call(self, node):
        node = self.generic_visit(node)
        node.keywords = [kw for kw in node.keywords if not (kw.arg in self.FLAGS and isinstance(kw.value, ast.Constant) and kw.value.value is False)]
        return node

    def visit_UnaryOp(self, node):
        node = self.generic_visit(node)
        if isinstance(node.op, ast.Not) and isinstance(node.operand, ast.Constant):
            return ast.Constant(not node.operand.value)
        return node

    def visit_BoolOp(self, node):
        node = self.generic_visit(node)
        values = []
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, bool):
                if (isinstance(node.op, ast.And) and not value.value) or (isinstance(node.op, ast.Or) and value.value):
                    return value
                continue
            values.append(value)
        if not values:
            return ast.Constant(isinstance(node.op, ast.And))
        node.values = values
        return values[0] if len(values) == 1 else node

    def visit_If(self, node):
        node = self.generic_visit(node)
        if isinstance(node.test, ast.Constant):
            return node.body if node.test.value else node.orelse
        return node

    def visit_IfExp(self, node):
        node = self.generic_visit(node)
        if isinstance(node.test, ast.Constant):
            return node.body if node.test.value else node.orelse
        return node


@pytest.mark.parametrize("name", list(BASELINE["functions"]))
def test_full_legacy_function_semantics_match_release(name):
    node = next(n for n in ast.parse((ROOT / "bot.py").read_text()).body if getattr(n, "name", "") == name)
    projected = LegacyProjection().visit(node)
    digest = hashlib.sha256(ast.dump(projected, include_attributes=False).encode()).hexdigest()
    assert digest == BASELINE["functions"][name], f"Legacy voice dependency changed: {name}"


@pytest.mark.parametrize("path", list(BASELINE["files"]))
def test_voice_and_provider_dependency_files_unchanged(path):
    assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == BASELINE["files"][path]


def test_live_voice_and_voice_command_still_use_legacy_entry():
    source = (ROOT / "bot.py").read_text()
    assert "VoiceConversation(bot, mem, BOT_NAME, get_response, get_audio_with_mood" in source
    tree = ast.parse(source)
    callers = {}
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for call in ast.walk(node):
            if isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == "get_response":
                callers.setdefault(node.name, []).append(call)
    assert set(callers) == {"voice_cmd", "get_text_response"}
    assert not callers["voice_cmd"][0].keywords
    assert callers["get_text_response"][0].keywords[-1].arg == "_text_policy"


@pytest.mark.parametrize("failed", ["", "Say what you mean.", "Use a different opener.", RuntimeError("synthetic")])
def test_failed_text_self_edit_keeps_original(monkeypatch, tmp_path, failed):
    runtime, loop = load_runtime(monkeypatch, tmp_path)
    original = "I think your strongest traits are curiosity, humor, and persistence."
    monkeypatch.setattr(runtime.groq_client, "is_exhausted", lambda: False)
    monkeypatch.setattr(runtime, "_self_edit_issues", lambda *a, **k: ["too generic"])
    rewrite = AsyncMock(side_effect=failed) if isinstance(failed, Exception) else AsyncMock(return_value=failed)
    monkeypatch.setattr(runtime, "_text_rewrite_reply_once", rewrite)
    try:
        result = loop.run_until_complete(runtime._text_self_edit_reply(original, recent_replies=[], user_message="Analyze my personality"))
        assert result == original
        rewrite.assert_awaited_once()
    finally:
        loop.close()
        asyncio.set_event_loop(None)


def test_text_and_voice_cooldown_contracts_are_separate(monkeypatch, tmp_path):
    runtime, loop = load_runtime(monkeypatch, tmp_path)
    cooldown = AsyncMock(return_value=(False, 90))
    monkeypatch.setattr(runtime.mem, "consume_phrase_with_status", cooldown)
    try:
        assert loop.run_until_complete(runtime._provider_pause_reply("groq", user_id=1)) == ""
        for _ in range(2):
            assert loop.run_until_complete(runtime._provider_pause_reply("groq", user_id=1, text_policy=True)) == FAILURE_NOTICE
        cooldown.assert_awaited_once()  # Only the legacy call touched the voice cooldown.
    finally:
        loop.close()
        asyncio.set_event_loop(None)


def test_boundary_passes_all_arguments_and_propagates_cancellation(monkeypatch, tmp_path):
    runtime, loop = load_runtime(monkeypatch, tmp_path)
    core = AsyncMock(return_value="synthetic answer")
    monkeypatch.setattr(runtime, "get_response", core)
    args = (1, 2, "Why?", {}, "tester", "<@1>")
    try:
        assert loop.run_until_complete(runtime.get_text_response(*args, defer_delivery=True)) == "synthetic answer"
        core.assert_awaited_once_with(*args, defer_delivery=True, _text_policy=True)
        core.side_effect = asyncio.CancelledError()
        with pytest.raises(asyncio.CancelledError):
            loop.run_until_complete(runtime.get_text_response(*args))
    finally:
        loop.close()
        asyncio.set_event_loop(None)
