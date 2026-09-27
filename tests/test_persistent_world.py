"""Persistent-world regressions: pure helpers, scoped storage and durable receipts."""
import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from grudge_system import GrudgeJournal
from world_store import WorldStore
from dream_coordinator import dream_tick
from birthday_event import birthday_window, restore_decorations
from code_awareness import compact_diff

def run(coro):
    return asyncio.run(coro)

def test_grudge_lifecycle(tmp_path):
    async def check():
        g=GrudgeJournal(tmp_path/"shared.db")
        await g.init(); await g.init()
        a,new=await g.create(1,2,"Repeated insults",severity=3,now=100)
        b,duplicate=await g.create(1,2,"Repeated insults!",severity=3,now=100)
        assert new and not duplicate and a["id"]==b["id"]
        assert not await g.active(2,2,now=101)
        assert not await g.active(1,3,now=101)
        assert await g.atone(1,2,"no",now=101)=="petition_rejected"
        assert await g.atone(1,2,"sorry",now=102)=="reduced"
        assert await g.atone(1,2,"truce",now=103)=="reduced"
        assert await g.atone(1,2,"sorry",now=104)=="resolved"
        assert not await g.active(1,2,now=105)
        await g.create(1,2,"Another offense",now=100)
        assert await g.maintain(now=100+8*86400)==1
    run(check())

def test_grudge_concurrency_clemency_restart(tmp_path):
    async def check():
        g=GrudgeJournal(tmp_path/"shared.db"); await g.init()
        outcomes=await asyncio.gather(*[g.create(1,2,"Petty remark") for _ in range(8)])
        assert sum(new for _,new in outcomes)==1
        second=GrudgeJournal(g.path); await second.init()
        assert len(await second.active(1,2))==1
        assert not await second.request_clemency(2,2)
        assert await second.request_clemency(1,2)
        assert not await second.request_clemency(1,2)
        await g.maintain()
        assert not await g.active(1,2)
        async with g.connect() as db:
            row=await (await db.execute("SELECT resolved_by FROM character_grudges")).fetchone()
            assert row[0]=="wanderer_petition"
    run(check())

def test_dream_pair_dedup_failure(tmp_path):
    async def check():
        store=WorldStore(tmp_path/"world.db"); await store.init()
        mem=SimpleNamespace(get_bot_relationship=AsyncMock(return_value={"tension":80,"respect":60,"stage":"enemy"}),
                            adjust_bot_relationship=AsyncMock())
        gen=AsyncMock(return_value="The wind carried a voice I almost recognized.")
        now=datetime(2026,1,3,3,tzinfo=timezone.utc)
        for name in ("scaramouche","wanderer","scaramouche"):
            await dream_tick(name,store,mem,gen,{"enabled":True},now)
        records=[v for _,v in await store.recent("dream_attempt")]
        assert len(records)==2 and gen.await_count==2
        assert len({r["shared_dream_id"] for r in records})==1
        assert all(r["emotional_effect"]=={"curiosity":1} for r in records)
        assert mem.adjust_bot_relationship.call_args.kwargs["respect_delta"]==1
        fail=AsyncMock(side_effect=RuntimeError("offline"))
        later=datetime(2026,2,3,3,tzinfo=timezone.utc)
        await dream_tick("wanderer",store,mem,fail,{"enabled":True},later)
        await dream_tick("wanderer",store,mem,fail,{"enabled":True},later)
        assert fail.await_count==1
    run(check())

def test_dream_low_significance(tmp_path):
    async def check():
        s=WorldStore(tmp_path/"world.db"); await s.init()
        m=SimpleNamespace(get_bot_relationship=AsyncMock(return_value={"tension":10,"respect":10}))
        gen=AsyncMock()
        await dream_tick("wanderer",s,m,gen,{"enabled":True},datetime(2026,1,3,3,tzinfo=timezone.utc))
        gen.assert_not_called()
    run(check())

def test_birthday_restart_restore(tmp_path):
    async def check():
        s=WorldStore(tmp_path/"world.db"); await s.init()
        await s.claim("restore:1","birthday_restore",{"guild_id":1,"object_id":2,"type":"channel","original":"general","temporary":"birthday","restore_at":1})
        obj=SimpleNamespace(name="birthday",edit=AsyncMock())
        guild=SimpleNamespace(get_channel=lambda _:obj)
        bot=SimpleNamespace(get_guild=lambda _:guild)
        s=WorldStore(s.path)
        await restore_decorations(bot,s,datetime.now(timezone.utc))
        obj.edit.assert_awaited_once_with(name="general",reason="Restore temporary birthday decoration")
        await restore_decorations(bot,s,datetime.now(timezone.utc))
        assert obj.edit.await_count==1
    run(check())
    assert birthday_window(datetime(2026,1,3,tzinfo=timezone.utc),"UTC")[0]
    assert not birthday_window(datetime(2026,1,4,tzinfo=timezone.utc),"UTC")[0]

def test_code_bounds_secrets():
    diff=compact_diff([{"filename":".env","patch":"+PASSWORD=hunter2"},
         {"filename":"face_memory.py","patch":"+private"},
         {"filename":"bot.py","patch":"+password='bad'\n+return 42\n"+"+safe\n"*200}])
    assert "bad" not in diff and ".env" not in diff and "face_memory" not in diff
    assert "return <number>" in diff and len(diff)<6001 and len(diff.splitlines())<=101
