"""Sensitive administrative commands must fail closed."""
from pathlib import Path
from types import SimpleNamespace as NS

from memory_rebuild import user_can_manage_rebuild

ROOT = Path(__file__).resolve().parents[1]


def ctx(uid, *, administrator=False, manage_guild=False, manage_messages=False):
    return NS(author=NS(
        id=uid,
        guild_permissions=NS(administrator=administrator, manage_guild=manage_guild,
                             manage_messages=manage_messages),
    ))


def test_rebuild_permission_requires_explicit_owner_even_for_guild_admins():
    assert not user_can_manage_rebuild(ctx(1, administrator=True), 0)
    assert not user_can_manage_rebuild(ctx(2, administrator=True), 1)
    assert not user_can_manage_rebuild(ctx(2, manage_guild=True), 1)
    assert not user_can_manage_rebuild(ctx(2, manage_messages=True), 1)
    assert user_can_manage_rebuild(ctx(1), 1)


def test_owner_diagnostics_and_backup_deny_unconfigured_owner():
    code = (ROOT / "bot.py").read_text()
    for command in ("bothealth_cmd", "backupmemory_cmd"):
        at = code.index("async def " + command + "(ctx):")
        assert "if not OWNER_ID or ctx.author.id != OWNER_ID:" in code[at:at + 125]
    assert "def user_can_manage_rebuild" in (ROOT / "memory_rebuild.py").read_text()
