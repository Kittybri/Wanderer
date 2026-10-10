import os
from pathlib import Path
import tempfile
import unittest
import asyncio
from datetime import datetime, timezone, timedelta

import memory as memory_module
from awareness_features import activity_snapshot, classify_safety, choose_duo_advice_mode, resolve_voice_state, select_relevant_recall, style_voice_text
from integrations import AsyncJSONClient, GitHubIssueService, GoogleCalendarService, GoogleSheetsService, GoogleTasksService, IntegrationAuthError, IntegrationConfig, IntegrationError, LetterboxdService, SpotifyService
from memory import Memory

ROOT = Path(__file__).resolve().parent
BOT_SOURCE = ROOT.joinpath("bot.py").read_text(encoding="utf-8")
VOICE_SOURCE = ROOT.joinpath("voice_handler.py").read_text(encoding="utf-8")


class FeatureTests(unittest.TestCase):
    def test_cross_bot_and_safety(self):
        self.assertEqual(choose_duo_advice_mode("How do I fix this assignment?", .01), "goodcop")
        self.assertEqual(choose_duo_advice_mode("What is 2 plus 2?", .01), "")
        self.assertEqual(choose_duo_advice_mode("How do I calculate 18 percent of 40?", .01), "")
        self.assertTrue(classify_safety("I can't breathe").protective)
        self.assertFalse(classify_safety("Scaramouche is annoyingly dramatic").protective)
        self.assertIn('"goodcop": 1', BOT_SOURCE)
        self.assertIn('"interview": 2', BOT_SOURCE)
        self.assertIn("constructive good cop", BOT_SOURCE)
        self.assertIn("if is_dm or not PARTNER_BOT_ID or not message.guild.get_member(PARTNER_BOT_ID)", BOT_SOURCE)

    def test_exact_recall_and_sensitive_filter(self):
        match = select_relevant_recall("I never said I hated green apples", [{"id":4,"channel_id":2,"content":"I always said I hated green apples","ts":1}])
        self.assertEqual(match.message_id, 4)
        self.assertIsNone(select_relevant_recall("my password is apples", []))

    def test_voice_and_platform_guards(self):
        old = resolve_voice_state({"conflict_open":True}, -8)
        new = resolve_voice_state({}, 0, delivery_intent="protective concern", previous=old)
        self.assertEqual(new.category, "concerned")
        self.assertNotIn("speed", style_voice_text("[speed=9] Stay.", new))
        self.assertIn("chunk = 220", VOICE_SOURCE)
        self.assertIn("intents.presences = True", BOT_SOURCE)
        self.assertIn("fetch_message(event[\"message_id\"])", BOT_SOURCE)
        self.assertIn("if joined_here and voice and voice.is_connected()", BOT_SOURCE)
        self.assertIn("candidate.author.id != participant_id", BOT_SOURCE)
        self.assertIn("PARTICIPANT_LATEST_ANSWER", BOT_SOURCE)
        self.assertNotIn("qai", ROOT.joinpath("awareness_features.py").read_text(encoding="utf-8"))

    def test_presence_skips_custom_status_and_handles_disappearance(self):
        class CustomActivity: name="custom"; type="custom"
        class Spotify: title="Song"; artist="Artist"; album="Album"; timestamps=None
        class Member: activities=[CustomActivity(),Spotify()]
        self.assertEqual(activity_snapshot(Member())["kind"],"spotify")
        Member.activities=[]
        self.assertIsNone(activity_snapshot(Member()))


class MemoryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        memory_module._data_dir = self.tmp.name
        memory_module.DB_PATH = os.path.join(self.tmp.name, "wanderer.db")
        memory_module.SHARED_DB_PATH = os.path.join(self.tmp.name, "shared.db")
        self.memory = Memory("wanderer")
        self.memory.shared_db_path = memory_module.SHARED_DB_PATH
        await self.memory.init()
        await self.memory.upsert_user(8, "u", "U")
    async def asyncTearDown(self): self.tmp.cleanup()
    async def test_provenance(self):
        await self.memory.record_tattletale_event(8, "scaramouche", "wanderer", 3, 88, "Scaramouche was annoying")
        event = await self.memory.get_tattletale_event(8, "scaramouche", 3)
        self.assertEqual(event["message_id"], 88)
        self.assertIsNone(await self.memory.get_tattletale_event(8, "scaramouche", 4))
        await self.memory.add_message(8, 3, "user", "I always hated green apples")
        rows = await self.memory.get_user_message_candidates(8, 3)
        self.assertGreater(rows[0]["id"], 0)
        results=await asyncio.gather(
            self.memory.consume_shared_cooldown("one-winner",60),
            self.memory.consume_shared_cooldown("one-winner",60),
        )
        self.assertEqual(sum(1 for allowed,_ in results if allowed),1)
class FakeClient:
    def __init__(self, result=None): self.result=result or {}; self.calls=[]
    async def request(self, *args, **kwargs): self.calls.append((args,kwargs)); return self.result

class FakeResponse:
    def __init__(self,status,payload=None,headers=None): self.status=status; self.payload=payload or {}; self.headers=headers or {}
    async def __aenter__(self): return self
    async def __aexit__(self,*args): return False
    async def json(self,**kwargs): return self.payload
class FakeSession:
    def __init__(self,factory): self.factory=factory
    async def __aenter__(self): return self
    async def __aexit__(self,*args): return False
    def request(self,*args,**kwargs):
        item=self.factory.items.pop(0)
        if isinstance(item,BaseException): raise item
        return item
class SessionFactory:
    def __init__(self,items): self.items=list(items)
    def __call__(self,**kwargs): return FakeSession(self)
async def no_sleep(_): pass


class IntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_disabled_and_redacted(self):
        self.assertFalse(SpotifyService({}).ready)
        self.assertFalse(LetterboxdService.ready)
        self.assertNotIn("secret", repr(IntegrationConfig({"token":"secret"})))
    async def test_github_and_calendar_guards(self):
        fake=FakeClient({"number":2,"html_url":"https://example.test/2"})
        gh=GitHubIssueService({"token":"x","allowed_repositories":["o/r"],"dry_run":False}, fake)
        self.assertTrue((await gh.create_issue("o/r","t","b"))["dry_run"])
        self.assertEqual((await gh.create_issue("o/r","t","b",confirmed=True))["number"],2)
        fake_cal=FakeClient({})
        cal=GoogleCalendarService({"access_token":"x","expires_at":99999999999},fake_cal)
        with self.assertRaises(ValueError): await cal.create_event("e",datetime.now(),datetime.now())
        with self.assertRaises(PermissionError): await cal.update_bot_event("id",{}, {"summary":"x"})
        aware=datetime.now(timezone.utc)
        with self.assertRaises(ValueError):
            await cal.create_event("e", aware, aware)
        self.assertTrue((await cal.create_event("e",aware,aware + timedelta(hours=1)))["dry_run"])
        self.assertEqual(fake_cal.calls, [])
        await cal.create_event("e",aware,aware + timedelta(hours=1),confirmed=True)
    async def test_google_account_separation_tasks_and_sheet_allowlist(self):
        config=IntegrationConfig({"google":{"accounts":{"7":{"access_token":"a"},"8":{"access_token":"b"}}}})
        self.assertEqual(config.google_account(7)["access_token"],"a")
        self.assertEqual(config.google_account(8)["access_token"],"b")
        self.assertEqual(config.google_account(9),{})
        tasks=GoogleTasksService({"access_token":"a","expires_at":99999999999},FakeClient({}))
        with self.assertRaises(ValueError): await tasks.update_task("id",{"due":"2026-09-26T12:00:00"})
        sheets=GoogleSheetsService({"access_token":"a","expires_at":99999999999,"allowed_spreadsheets":["approved"]},FakeClient({}))
        with self.assertRaises(PermissionError): await sheets.append_score_rows("other",[["score"]])
        await sheets.append_score_rows("approved",[["score"]])
    async def test_http_failures_and_retry(self):
        with self.assertRaises(IntegrationAuthError):
            await AsyncJSONClient(session_factory=SessionFactory([FakeResponse(401)]),sleep=no_sleep).request("GET","https://example.test")
        with self.assertRaisesRegex(IntegrationError,"timed out"):
            await AsyncJSONClient(session_factory=SessionFactory([asyncio.TimeoutError(),asyncio.TimeoutError()]),sleep=no_sleep).request("GET","https://example.test")
        client=AsyncJSONClient(session_factory=SessionFactory([FakeResponse(429,headers={"Retry-After":"0"}),FakeResponse(200,{"ok":True})]),sleep=no_sleep)
        self.assertEqual(await client.request("GET","https://example.test"),{"ok":True})


if __name__ == "__main__": unittest.main()
