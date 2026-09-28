"""Write-ahead cosmetic edits; never delete objects or change permissions."""

from __future__ import annotations
from .errors import ChaosError
import time
import uuid
import asyncio
import discord

FIELDS = {
    "channel": {"name", "topic", "slowmode_delay"},
    "role": {"name"},
    "member": {"nick"},
}


class Restoration:
    def __init__(self, owner):
        self.owner, self.store = owner, owner.store

    async def object(self, guild, kind, oid):
        if kind == "channel":
            obj = await self.owner.bot.fetch_channel(oid)
            if obj.guild.id != guild.id:
                raise ChaosError("Wrong guild")
            return obj
        if kind == "role":
            return next((r for r in await guild.fetch_roles() if r.id == oid), None)
        return await guild.fetch_member(oid)

    async def apply(
        self,
        guild,
        kind,
        oid,
        field,
        value,
        actor,
        duration,
        feature="sovereign",
        explicit_slowmode=False,
    ):
        if kind not in FIELDS or field not in FIELDS[kind]:
            raise ChaosError("Not a cosmetic field")
        cfg = self.owner.cfg(guild.id)
        explicit = (
            explicit_slowmode
            and kind == "channel"
            and field == "slowmode_delay"
            and feature == "legacy_slowmode"
        )
        if (
            kind == "channel"
            and oid not in cfg.get("allowed_channels", [])
            and not explicit
        ):
            raise ChaosError("Channel not allowed")
        if kind == "role" and oid not in cfg.get("allowed_roles", []):
            raise ChaosError("Role not allowed")
        if kind == "member" and oid != self.owner.bot.user.id:
            raise ChaosError("Only own nickname")
        obj = await self.object(guild, kind, oid)
        if not obj:
            raise ChaosError("Object missing")
        if kind == "role" and (
            obj.managed
            or obj.is_default()
            or obj >= guild.me.top_role
            or obj.permissions.value
        ):
            raise ChaosError("Only powerless cosmetic roles below bot")
        if field == "slowmode_delay":
            value = max(0, min(10, int(value)))
        elif value is not None:
            value = str(value)[
                : 32 if field == "nick" else 90 if field == "name" else 200
            ]
            if "@" in value or "http" in value:
                raise ChaosError("No mentions/links in cosmetics")
        old = getattr(obj, field)
        if old == value:
            return None
        birthday_cfg = (
            getattr(self.owner.world, "config", {})
            .get("birthday", {})
            .get("guilds", {})
            .get(str(guild.id), {})
        )
        if (
            field == "name"
            and birthday_cfg.get("decorations_enabled")
            and str(oid)
            in birthday_cfg.get("channels" if kind == "channel" else "roles", {})
        ):
            raise ChaosError(
                "This name is configured for the existing birthday manager; use nonoverlapping cosmetic targets"
            )
        key = f"chaos:mutation:{guild.id}:{kind}:{oid}:{field}"
        now = time.time()
        for _, birthday in await self.store.recent("birthday_restore", 100):
            if (
                birthday["guild_id"] == guild.id
                and birthday["object_id"] == oid
                and birthday["type"] == kind
                and field == "name"
            ):
                raise ChaosError("A birthday restoration already owns this name")
        record = dict(
            session_id=uuid.uuid4().hex[:16],
            guild_id=guild.id,
            bot=self.owner.name,
            actor=actor,
            feature=feature,
            object_type=kind,
            object_id=oid,
            field=field,
            before=old,
            after=value,
            state="intent",
            changed_at=now,
            restore_at=now + max(10, min(900, int(duration))),
            restored_at=None,
            lease_until=now + 60,
            result="pending",
        )
        async with self.store.connect() as db:
            await db.execute("BEGIN IMMEDIATE")
            prior = await self.store.read(db, key)
            if prior and prior["state"] in {"intent", "applied"}:
                raise ChaosError("Tracked mutation already pending")
            count = await (
                await db.execute(
                    "SELECT count(*) FROM persistent_world_events WHERE kind='chaos_mutation' AND json_extract(payload,'$.state') IN ('intent','applied')"
                )
            ).fetchone()
            if count[0] >= 100:
                raise ChaosError("Restoration capacity reached")
            await self.store.write(db, key, "chaos_mutation", record)
            await self.store.write(
                db,
                "chaos:audit:" + record["session_id"],
                "chaos_audit",
                dict(record, state="audit"),
            )
            await db.commit()
        try:
            await asyncio.wait_for(
                obj.edit(**{field: value}, reason="Opt-in temporary server game"), 20
            )
        except (discord.HTTPException, asyncio.TimeoutError):
            # Ambiguous edit failure: keep original and reconcile, never assume.
            record["result"] = "apply_uncertain"
        else:
            record.update(state="applied", result="applied")
        record["lease_until"] = 0
        await self.store.put(key, "chaos_mutation", record)
        await self.store.put(
            "chaos:audit:" + record["session_id"],
            "chaos_audit",
            dict(record, state="audit"),
        )
        return record

    async def restore(self, gid=None, force=False):
        for key, rec in await self.store.recent("chaos_mutation", 100, oldest=True):
            if rec["state"] not in {"intent", "applied"} or (
                gid and rec["guild_id"] != gid
            ):
                continue
            if not force and rec["bot"] != self.owner.name:
                continue  # A disabled/less-privileged partner must not starve the owner.
            if not force and rec["restore_at"] > time.time():
                continue
            # Cross-bot restoration lease, including an ambiguous in-flight apply.
            async with self.store.connect() as db:
                await db.execute("BEGIN IMMEDIATE")
                r = await self.store.read(db, key)
                if (
                    r["state"] not in {"intent", "applied"}
                    or r.get("lease_until", 0) > time.time()
                ):
                    continue
                r["lease_until"] = time.time() + 60
                await self.store.write(db, key, "chaos_mutation", r)
                await db.commit()
            guild = self.owner.bot.get_guild(r["guild_id"])
            if not guild:
                continue
            try:
                obj = await self.object(guild, r["object_type"], r["object_id"])
                if obj is None:
                    r.update(state="gone", result="object_deleted")
                elif getattr(obj, r["field"]) == r["after"]:
                    await asyncio.wait_for(
                        obj.edit(
                            **{r["field"]: r["before"]},
                            reason="Restore tracked server game cosmetic",
                        ),
                        20,
                    )
                    r.update(
                        state="restored", result="restored", restored_at=time.time()
                    )
                elif getattr(obj, r["field"]) == r["before"]:
                    r.update(
                        state="restored",
                        result="already_original",
                        restored_at=time.time(),
                    )
                else:
                    r.update(state="superseded", result="manual_change_preserved")
            except discord.NotFound:
                r.update(state="gone", result="object_deleted")
            except (discord.HTTPException, AttributeError, asyncio.TimeoutError):
                r["result"] = "retry_permission_or_network"
            r["lease_until"] = (
                time.time() + 30 if r["state"] in {"intent", "applied"} else 0
            )
            await self.store.put(key, "chaos_mutation", r)
            await self.store.put(
                "chaos:audit:" + r["session_id"], "chaos_audit", dict(r, state="audit")
            )
