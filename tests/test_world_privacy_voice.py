import asyncio
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock
import pytest
import face_memory as fm
from face_controls import FaceProfiles
from world_store import WorldStore
from persistent_world import PersistentWorld
from birthday_event import run_birthday, restore_decorations
from lullaby import eligible, playback, lullaby_tick
from code_awareness import compact_diff

def run(coro): return asyncio.run(coro)

def test_birthday_restoration_retries_missing_cache_and_permissions(tmp_path):
    async def check():
        import discord
        store=WorldStore(tmp_path/"world.db"); await store.init()
        record={"guild_id":1,"object_id":2,"type":"channel","original":"general","temporary":"birthday","restore_at":1}
        await store.claim("restore:test","birthday_restore",record)
        guild=NS(get_channel=lambda _:None)
        bot=NS(get_guild=lambda _:guild)
        now=datetime.now(timezone.utc)
        await restore_decorations(bot,store,now)
        assert await store.get("restore:test")==record
        denied=discord.Forbidden(NS(status=403,reason="Forbidden"),"permission removed")
        obj=NS(name="birthday",edit=AsyncMock(side_effect=denied))
        guild.get_channel=lambda _:obj
        await restore_decorations(bot,store,now)
        assert await store.get("restore:test")==record
        obj.edit=AsyncMock()
        await restore_decorations(bot,store,now)
        assert await store.get("restore:test") is None
        obj.edit.assert_awaited_once_with(name="general",reason="Restore temporary birthday decoration")
    run(check())


def vector(n):
    return [1.0 if i==n else 0.0 for i in range(128)]

def profile(n=0):
    return {"backend":fm.BACKEND,"model":"test-v1","templates":[vector(n)],"sample_count":1}

def test_face_match_threshold_ambiguity_corruption():
    assert fm.match_candidates(vector(0),{1:profile()},"test-v1")["matched"]
    assert fm.match_candidates(vector(1),{1:profile()},"test-v1")["status"]=="unknown"
    assert fm.match_candidates(vector(0),{1:profile(),2:profile()},"test-v1")["status"]=="ambiguous"
    assert not fm.match_candidates([float("nan")]*128,{1:profile()},"test-v1")["ok"]
    assert not fm.match_candidates(vector(0),{1:{"templates":[vector(0)]}},"test-v1")["ok"]
    assert not fm.match_candidates(vector(0),{1:dict(profile(),model="changed")},"test-v1")["ok"]

def test_face_enrollment_bounds_legacy_and_unavailable(monkeypatch):
    monkeypatch.setattr(fm,"extract_face_template",lambda data:{"ok":True,"template":vector(0),"model":"test-v1"})
    p={"templates":[[1]*256]}
    for _ in range(12):
        result=fm.enroll_face_profile(p,b"image"); p=result["profile"]
    assert len(p["templates"])==8 and p["backend"]==fm.BACKEND
    assert fm.match_face(b"image",p)["matched"]
    assert fm.match_face(b"image",{"templates":[[1]*256]})["reason"]=="legacy_reenroll"
    assert not fm.is_face_enroll_request("this is me")
    assert not fm.is_face_check_request("do you recognize me")

def test_face_backend_unavailable(monkeypatch):
    monkeypatch.delenv("FACE_YUNET_MODEL",raising=False)
    monkeypatch.delenv("FACE_SFACE_MODEL",raising=False)
    assert fm.extract_face_template(b"image")["reason"]=="unavailable"

def test_face_delete_isolation_race_restart(tmp_path):
    async def check():
        store=FaceProfiles(tmp_path/"faces.db"); await store.init(); await store.init()
        gen,_=await store.snapshot(1)
        assert await store.save(1,gen,profile())
        gen,p=await store.snapshot(1)
        assert p["templates"]==[vector(0)]
        assert (await store.snapshot(2))[1] is None
        await store.delete(2)
        assert (await store.snapshot(1))[1] is not None
        await store.delete(1)
        assert not await store.save(1,gen,p)
        assert (await FaceProfiles(store.path).snapshot(1))[1] is None
    run(check())


def test_grudge_escalation_forgetting(tmp_path):
    async def check():
        world=fake_world(tmp_path); await world.init()
        row,_=await world.journal.create(1,2,"Repeated insults",severity=2)
        raised,changed=await world.journal.create(1,2,"Repeated insults!",severity=3)
        assert changed and raised["id"]==row["id"] and raised["severity"]==3
        await world.journal.create(2,2,"Repeated insults",severity=2)
        assert await world.forget(1,"insults")==1
        assert not await world.journal.active(1,2)
        assert len(await world.journal.active(2,2))==1
    run(check())

def test_reconnect_tick_is_serial_and_no_default_llm(tmp_path):
    async def check():
        world=fake_world(tmp_path)
        gen=AsyncMock()
        bot=NS()
        await asyncio.gather(*(world.tick(bot,gen) for _ in range(5)))
        gen.assert_not_called()
        assert world.ready
    run(check())

def test_source_provider_failure_is_not_retried(tmp_path,monkeypatch):
    async def check():
        world=fake_world(tmp_path,config={"code_awareness":{"enabled":True,"channel_id":2,"repository":"Kittybri/scaramouche"}})
        world.github=object(); await world.init()
        channel=NS(guild=NS(default_role=object()),permissions_for=lambda _:NS(view_channel=False),send=AsyncMock())
        bot=NS(get_channel=lambda _:channel)
        monkeypatch.setattr("persistent_world.latest_commit",AsyncMock(return_value={"sha":"b"*40,"diff":"+return 42","own_behavior":False}))
        gen=AsyncMock(side_effect=RuntimeError("offline"))
        now=datetime.now(timezone.utc)
        with pytest.raises(RuntimeError):
            await world.code_tick(bot,gen,now)
        await world.code_tick(bot,gen,now+timedelta(days=1))
        assert gen.await_count==1
        channel.send.assert_not_called()
    run(check())

def test_lullaby_cooldown(tmp_path,monkeypatch):
    async def check():
        user,member,channel,now=fixture_voice()
        channel.id=2
        class FakeVoiceChannel: pass
        monkeypatch.setattr("lullaby.discord.VoiceChannel",FakeVoiceChannel)
        vc=FakeVoiceChannel()
        vc.__dict__.update(channel.__dict__)
        mem=NS(get_user=AsyncMock(return_value=user),get_duo_session=AsyncMock(return_value=None))
        store=WorldStore(tmp_path/"world.db"); await store.init()
        play=AsyncMock()
        monkeypatch.setattr("lullaby.playback",play)
        monkeypatch.setattr("lullaby.os.path.isfile",lambda _:True)
        cfg={"enabled":True,"ambient_path":"authorized.wav","channel_ids":[2]}
        bot=NS(get_channel=lambda _:vc)
        await lullaby_tick(bot,mem,store,cfg,now)
        await lullaby_tick(bot,mem,store,cfg,now)
        assert play.await_count==1
    run(check())

def test_birthday_no_permission_no_rename(tmp_path):
    async def check():
        store=WorldStore(tmp_path/"world.db"); await store.init()
        channel=NS(id=2,name="general",send=AsyncMock(),edit=AsyncMock())
        guild=NS(id=1,get_channel=lambda _:channel,me=NS(guild_permissions=NS(manage_channels=False,manage_roles=False)))
        cfg={"guilds":{"1":{"enabled":True,"channel_id":2,"decorations_enabled":True,"channels":{"2":"birthday"}}}}
        await run_birthday(NS(get_guild=lambda _:guild),store,cfg,datetime(2026,1,3,tzinfo=timezone.utc))
        channel.edit.assert_not_called()
        assert not await store.recent("birthday_restore")
    run(check())

def test_memory_fresh_and_atomic_relationship(tmp_path,monkeypatch):
    import memory
    monkeypatch.setattr(memory,"_data_dir",str(tmp_path))
    monkeypatch.setattr(memory,"SHARED_DB_PATH",str(tmp_path/"shared.db"))
    mem=memory.Memory("fresh")
    async def check():
        await mem.init()
        before=await mem.get_bot_relationship("scaramouche::wanderer")
        await asyncio.gather(*[mem.adjust_bot_relationship("scaramouche::wanderer",respect_delta=1,tension_delta=-1) for _ in range(4)])
        after=await mem.get_bot_relationship("scaramouche::wanderer")
        assert after["respect"]==min(100,before["respect"]+4)
        assert after["tension"]==max(0,before["tension"]-4)
        assert (await mem.get_user_preferences(999))["lullaby_enabled"] is False
    run(check())


def test_face_legacy_owned_only(tmp_path):
    async def check():
        store=FaceProfiles(tmp_path/"faces.db"); await store.init()
        async with store.connect() as db:
            await db.execute("INSERT INTO face_profiles VALUES('owner_face',1,'','{}',0)")
            await db.commit()
        assert (await store.snapshot(1))[1]=={}
        assert (await store.snapshot(2))[1] is None
        await store.delete(1)
        assert (await store.snapshot(1))[1] is None
    run(check())

def fake_world(tmp_path,name="scaramouche",config=None):
    mem=NS(shared_db_path=tmp_path/"world.db",
        get_user_preferences=AsyncMock(return_value={"grudge_enabled":True}))
    return PersistentWorld(name,mem,config or {})

def test_ledger_never_crosses_channel_or_dm(tmp_path):
    async def check():
        world=fake_world(tmp_path,config={"grudge_ledger_channels":{"1":99}})
        channel=NS(id=2,send=AsyncMock())
        message=NS(id=5,channel=channel,guild=NS(id=1))
        await world.record(message,1,"A playful hat remark",1,"test")
        channel.send.assert_not_called()
        message.guild=None; message.id=6
        await world.record(message,1,"A private hat remark",1,"test")
        channel.send.assert_not_called()
        world.config["grudge_ledger_channels"]["1"]=2; message.guild=NS(id=1)
        await world.record(message,1,"A public hat remark",1,"test")
        channel.send.assert_awaited_once()
        await world.record(message,1,"A public hat remark",1,"test")
        assert channel.send.await_count==1
    run(check())

def test_grudge_context_scoped_and_distress(tmp_path):
    async def check():
        world=fake_world(tmp_path); await world.init()
        await world.journal.create(1,2,"Unresolved direct insult",severity=3)
        user={"mood":0}
        adjusted,context=await world.response_context(1,2,"hello",user)
        assert adjusted["mood"]==-3 and user["mood"]==0 and "VENDETTA" in context
        assert (await world.response_context(1,3,"hello",user))[1]==""
        assert (await world.response_context(1,2,"I'm scared",user))[1]==""
        assert (await world.response_context(1,2,"hello",{"grudge_enabled":False}))[1]==""
    run(check())

def test_birthday_once_allowlist_restart_admin_edit(tmp_path):
    async def check():
        store=WorldStore(tmp_path/"world.db"); await store.init()
        channel=NS(id=2,name="general",send=AsyncMock(),edit=AsyncMock())
        other=NS(id=3,name="other",edit=AsyncMock())
        guild=NS(id=1,get_channel=lambda i:{2:channel,3:other}.get(i),
            me=NS(guild_permissions=NS(manage_channels=True,manage_roles=False)))
        bot=NS(get_guild=lambda i:guild)
        cfg={"guilds":{"1":{"enabled":True,"channel_id":2,"timezone":"UTC",
            "decorations_enabled":True,"channels":{"2":"birthday"}}}}
        now=datetime(2026,1,3,10,tzinfo=timezone.utc)
        await run_birthday(bot,store,cfg,now); await run_birthday(bot,store,cfg,now)
        assert channel.send.await_count==1 and channel.edit.await_count==1
        other.edit.assert_not_called()
        pending=await store.recent("birthday_restore")
        assert pending[0][1]["original"]=="general"
        # Admin edit wins over automatic restoration.
        channel.name="administrator-chose-this"
        await restore_decorations(bot,WorldStore(store.path),now+timedelta(days=1))
        assert channel.edit.await_count==1
        assert not await store.recent("birthday_restore")
    run(check())

def test_birthday_optout_eligibility(tmp_path):
    async def check():
        world=fake_world(tmp_path); await world.init()
        for uid,eligible_value,wished in ((1,True,False),(2,False,False),(3,True,True)):
            await world.store.put(f"b:{uid}","birthday_pending",{
                "user_id":uid,"channel_id":2,"guild_id":1,"year":2026,
                "eligible":eligible_value,"wished":wished,"ends_at":1})
        await world.finish_birthdays(datetime.now(timezone.utc))
        assert len(await world.journal.active(1,2))==1
        assert not await world.journal.active(2,2) and not await world.journal.active(3,2)
        assert not await world.store.recent("birthday_pending")
    run(check())

def test_source_review_dedup_cooldown_and_reflection(tmp_path,monkeypatch):
    async def check():
        world=fake_world(tmp_path,config={"code_awareness":{"enabled":True,"channel_id":2,
             "repository":"Kittybri/scaramouche","reflection":True}})
        world.github=object(); await world.init()
        world.self_store=NS(add_reflection=AsyncMock())
        channel=NS(guild=NS(default_role=object()),permissions_for=lambda _:NS(view_channel=False),send=AsyncMock())
        bot=NS(get_channel=lambda _:channel)
        fetch=AsyncMock(return_value={"sha":"a"*40,"diff":"+return 42","own_behavior":True})
        monkeypatch.setattr("persistent_world.latest_commit",fetch)
        gen=AsyncMock(return_value="Framing: Fine. Technical finding: this returns a constant.")
        now=datetime.now(timezone.utc)
        await world.code_tick(bot,gen,now); await world.code_tick(bot,gen,now)
        await world.code_tick(bot,gen,now+timedelta(days=1))
        assert gen.await_count==1 and channel.send.await_count==1
        assert world.self_store.add_reflection.await_count==1
    run(check())

def test_diff_literals_generated_and_bounds():
    result=compact_diff([{"filename":"bot.py","patch":"+value='an unlabelled credential'\n+return 42 # private comment\n+key='sk-abcdefghijk'"},
                         {"filename":"generated/model.py","patch":"+return private"},
                         {"filename":"requirements.lock","patch":"+return private"}])
    assert "unlabelled credential" not in result and "private" not in result and "sk-" not in result
    assert "return <number>" in result

def test_preference_migration_existing_and_fresh(tmp_path,monkeypatch):
    import memory
    monkeypatch.setattr(memory,"_data_dir",str(tmp_path))
    monkeypatch.setattr(memory,"DB_PATH",str(tmp_path/"bot.db"))
    monkeypatch.setattr(memory,"SHARED_DB_PATH",str(tmp_path/"shared.db"))
    mem=memory.Memory("test")
    async def check():
        import aiosqlite
        async with aiosqlite.connect(mem.db_path) as db:
            await db.execute("CREATE TABLE user_preferences(user_id INTEGER PRIMARY KEY,voice_enabled INTEGER DEFAULT 1,utility_mode INTEGER DEFAULT 1,duo_autoplay INTEGER DEFAULT 1,rp_depth TEXT DEFAULT 'medium')")
            await db.execute("INSERT INTO user_preferences(user_id,voice_enabled) VALUES(1,0)")
            await db.commit()
        await mem.init(); await mem.init()
        prefs=await mem.get_user_preferences(1)
        assert not prefs["voice_enabled"] and not prefs["lullaby_enabled"] and prefs["grudge_enabled"]
        assert (await mem.get_user_preferences(2))["lullaby_start_hour"]==23
        await mem.set_user_preference(1,"lullaby_enabled",1)
        assert (await mem.get_user_preferences(1))["lullaby_enabled"]
    run(check())


def test_legacy_mature_mode_is_preserved_under_unrestricted_name(tmp_path, monkeypatch):
    import memory
    monkeypatch.setattr(memory, "_data_dir", str(tmp_path))
    monkeypatch.setattr(memory, "DB_PATH", str(tmp_path / "bot.db"))
    monkeypatch.setattr(memory, "SHARED_DB_PATH", str(tmp_path / "shared.db"))
    mem = memory.Memory("test")
    legacy_column = "ns" + "fw_mode"

    async def check():
        import aiosqlite
        async with aiosqlite.connect(mem.db_path) as db:
            await db.execute(
                f"CREATE TABLE users(user_id INTEGER PRIMARY KEY,username TEXT,display_name TEXT,"
                f"romance_mode INTEGER DEFAULT 0,{legacy_column} INTEGER DEFAULT 0,"
                "proactive INTEGER DEFAULT 1,last_seen REAL DEFAULT 0)"
            )
            await db.execute(
                f"INSERT INTO users(user_id,username,display_name,{legacy_column}) "
                "VALUES(71,'legacy','Legacy',1)"
            )
            await db.commit()
        await mem.init()
        assert (await mem.get_user(71))["unrestricted_mode"] is True
        async with aiosqlite.connect(mem.db_path) as db:
            columns = {
                row[1]
                for row in await (await db.execute("PRAGMA table_info(users)")).fetchall()
            }
        assert legacy_column not in columns

    run(check())

def fixture_voice():
    member=NS(id=1,status="online",bot=False)
    guild=NS(voice_client=None,me=object())
    channel=NS(members=[member],guild=guild,permissions_for=lambda _:NS(view_channel=True,connect=True,speak=True))
    now=datetime(2026,1,1,23,tzinfo=timezone.utc)
    user={"lullaby_enabled":True,"voice_enabled":True,"proactive":True,"affection":90,
          "timezone_name":"UTC","last_active":now.timestamp()}
    return user,member,channel,now

@pytest.mark.parametrize("field,value",[
    ("lullaby_enabled",False),("voice_enabled",False),("proactive",False),
    ("affection",10),("last_active",0)])
def test_lullaby_optin_relationship_activity(field,value):
    user,member,channel,now=fixture_voice()
    assert eligible(user,member,channel,now,{})
    user[field]=value
    assert not eligible(user,member,channel,now,{})

def test_lullaby_time_permission_busy_group():
    user,member,channel,now=fixture_voice()
    assert not eligible(user,member,channel,now.replace(hour=12),{})
    channel.guild.voice_client=object()
    assert not eligible(user,member,channel,now,{})
    channel.guild.voice_client=None
    channel.permissions_for=lambda _:NS(view_channel=True,connect=False,speak=True)
    assert not eligible(user,member,channel,now,{})
    channel.permissions_for=lambda _:NS(view_channel=True,connect=True,speak=True)
    channel.members.append(NS(id=2))
    assert not eligible(user,member,channel,now,{})

def test_lullaby_playback_cleanup_and_tts_failure(monkeypatch):
    async def check():
        voice=NS(play=Mock(),stop=Mock(),disconnect=AsyncMock(),is_playing=lambda:False)
        source=NS(cleanup=Mock())
        monkeypatch.setattr("lullaby.discord.FFmpegPCMAudio",lambda *a,**kw:source)
        channel=NS(connect=AsyncMock(return_value=voice),members=[NS(bot=False),NS(bot=True)])
        await playback(channel,"ambient.wav",1)
        voice.disconnect.assert_awaited_once_with(force=True); source.cleanup.assert_called_once()
        with pytest.raises(RuntimeError):
            await playback(channel,"ambient.wav",1,AsyncMock(side_effect=RuntimeError("TTS unavailable")))
        assert voice.disconnect.await_count==2
    run(check())

def test_lullaby_cancellation_cleans_up(monkeypatch):
    async def check():
        started=asyncio.Event()
        voice=NS(play=lambda _:started.set(),stop=Mock(),disconnect=AsyncMock(),is_playing=lambda:True)
        source=NS(cleanup=Mock())
        monkeypatch.setattr("lullaby.discord.FFmpegPCMAudio",lambda *a,**kw:source)
        channel=NS(connect=AsyncMock(return_value=voice),members=[NS(bot=False),NS(bot=True)])
        task=asyncio.create_task(playback(channel,"ambient.wav",180))
        await started.wait(); task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
        voice.disconnect.assert_awaited_once(); source.cleanup.assert_called_once()
    run(check())
