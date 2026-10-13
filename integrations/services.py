from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import time
from typing import Any
from urllib.parse import quote, urlencode

import aiohttp


class IntegrationError(RuntimeError): pass
class IntegrationAuthError(IntegrationError): pass


@dataclass(frozen=True)
class IntegrationConfig:
    values: dict[str, Any]
    def __repr__(self): return "IntegrationConfig(<redacted>)"
    def section(self, name: str) -> dict[str, Any]:
        value = self.values.get(name, {})
        return dict(value) if isinstance(value, dict) else {}
    def google_account(self, user_id: int) -> dict[str, Any]:
        accounts = self.section("google").get("accounts", {})
        value = accounts.get(str(int(user_id)), {}) if isinstance(accounts, dict) else {}
        return dict(value) if isinstance(value, dict) else {}


def load_integration_config() -> IntegrationConfig:
    raw = (os.getenv("BOT_INTEGRATIONS_JSON") or "").strip()
    path = (os.getenv("BOT_INTEGRATIONS_CONFIG") or "").strip()
    try:
        raw = Path(path).expanduser().read_text(encoding="utf-8") if path else raw
        values = json.loads(raw) if raw else {}
    except (OSError, json.JSONDecodeError):
        values = {}
    return IntegrationConfig(values if isinstance(values, dict) else {})


class AsyncJSONClient:
    def __init__(self, timeout_seconds: float = 12.0, *, session_factory=None, sleep=None):
        self.timeout = aiohttp.ClientTimeout(total=max(2.0, min(30.0, timeout_seconds)))
        self.session_factory = session_factory or aiohttp.ClientSession
        self.sleep = sleep or asyncio.sleep
    async def request(self, method: str, url: str, *, headers=None, json=None, data=None, expected=(200, 201)):
        for attempt in range(2):
            try:
                async with self.session_factory(timeout=self.timeout) as session:
                    async with session.request(method, url, headers=headers, json=json, data=data) as response:
                        if response.status in expected:
                            return None if response.status == 204 else await response.json(content_type=None)
                        if response.status in {401, 403}:
                            raise IntegrationAuthError(f"authentication rejected ({response.status})")
                        if (response.status == 429 or response.status >= 500) and attempt == 0:
                            try: delay = max(.25, min(3.0, float(response.headers.get("Retry-After", "1"))))
                            except ValueError: delay = 1.0
                            await self.sleep(delay); continue
                        raise IntegrationError(f"service request failed ({response.status})")
            except asyncio.TimeoutError as exc:
                if attempt == 0: continue
                raise IntegrationError("service request timed out") from exc
            except aiohttp.ClientError as exc:
                if attempt == 0: await self.sleep(.25); continue
                raise IntegrationError("service connection failed") from exc
        raise IntegrationError("service request failed")


class GitHubIssueService:
    def __init__(self, config: dict, client=None):
        self.token = str(config.get("token") or "").strip()
        self.allowed = {str(repo).lower() for repo in config.get("allowed_repositories", []) if repo}
        self.dry_run = bool(config.get("dry_run", True)); self.client = client or AsyncJSONClient()
    @property
    def ready(self): return bool(self.token and self.allowed)
    async def create_issue(self, repository: str, title: str, body: str, *, confirmed=False):
        repository = (repository or "").strip().lower()
        if repository not in self.allowed: raise PermissionError("repository is not allowlisted")
        payload = {"title":(title or "").strip()[:180], "body":(body or "").strip()[:5000]}
        if not payload["title"]: raise ValueError("issue title is required")
        if self.dry_run or not confirmed: return {"dry_run":True, "repository":repository, **payload}
        if not self.token: raise IntegrationAuthError("GitHub token is not configured")
        result = await self.client.request("POST", f"https://api.github.com/repos/{repository}/issues",
            headers={"Authorization":f"Bearer {self.token}", "Accept":"application/vnd.github+json", "X-GitHub-Api-Version":"2022-11-28"}, json=payload)
        return {"dry_run":False, "number":int(result.get("number", 0)), "url":str(result.get("html_url", ""))}


class SpotifyService:
    def __init__(self, config: dict, client=None): self.config=dict(config); self.client=client or AsyncJSONClient()
    @property
    def ready(self): return bool(self.config.get("access_token") or self.config.get("refresh_token"))
    async def _token(self):
        token=str(self.config.get("access_token") or "")
        if token and float(self.config.get("expires_at") or 0)>time.time()+30: return token
        refresh=str(self.config.get("refresh_token") or "")
        if not refresh:
            if token: return token
            raise IntegrationAuthError("Spotify authorization is not configured")
        basic=base64.b64encode(f"{self.config.get('client_id','')}:{self.config.get('client_secret','')}".encode()).decode()
        result=await self.client.request("POST", "https://accounts.spotify.com/api/token", headers={"Authorization":f"Basic {basic}"},
            data={"grant_type":"refresh_token", "refresh_token":refresh})
        self.config.update(access_token=result.get("access_token", ""), expires_at=time.time()+int(result.get("expires_in",3600)))
        return str(self.config["access_token"])
    async def _headers(self): return {"Authorization":f"Bearer {await self._token()}"}
    async def currently_playing(self): return await self.client.request("GET", "https://api.spotify.com/v1/me/player/currently-playing", headers=await self._headers(), expected=(200,204))
    async def get_playlist(self, playlist_id): return await self.client.request("GET", f"https://api.spotify.com/v1/playlists/{playlist_id}", headers=await self._headers())
    async def create_playlist(self, name, *, description="Created by the Discord bot"):
        uid=str(self.config.get("user_id") or "").strip()
        if not uid: raise ValueError("Spotify user_id is not configured")
        return await self.client.request("POST", f"https://api.spotify.com/v1/users/{uid}/playlists", headers=await self._headers(), json={"name":name[:100],"description":description[:300],"public":False})
    async def add_tracks(self, playlist_id, uris):
        clean=[uri for uri in uris[:100] if str(uri).startswith("spotify:track:")]
        if not clean: raise ValueError("no valid Spotify track URIs")
        return await self.client.request("POST", f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks", headers=await self._headers(), json={"uris":clean})


class _GoogleBase:
    def __init__(self, account: dict, client=None): self.account=dict(account); self.client=client or AsyncJSONClient()
    @property
    def ready(self): return bool(self.account.get("access_token") or self.account.get("refresh_token"))
    async def _token(self):
        token=str(self.account.get("access_token") or "")
        if token and float(self.account.get("expires_at") or 0)>time.time()+30: return token
        refresh=str(self.account.get("refresh_token") or "")
        if not refresh:
            if token: return token
            raise IntegrationAuthError("Google account is not authorized")
        result=await self.client.request("POST", "https://oauth2.googleapis.com/token", data={"client_id":self.account.get("client_id",""),"client_secret":self.account.get("client_secret",""),"refresh_token":refresh,"grant_type":"refresh_token"})
        self.account.update(access_token=result.get("access_token",""), expires_at=time.time()+int(result.get("expires_in",3600)))
        return str(self.account["access_token"])
    async def _headers(self): return {"Authorization":f"Bearer {await self._token()}","Content-Type":"application/json"}


class GoogleTasksService(_GoogleBase):
    async def list_tasks(self, tasklist="@default"): return await self.client.request("GET", f"https://tasks.googleapis.com/tasks/v1/lists/{tasklist}/tasks", headers=await self._headers())
    async def create_task(self, title, *, notes="", due:datetime|None=None, tasklist="@default"):
        payload={"title":title[:250],"notes":notes[:2000]}
        if due:
            if due.tzinfo is None: raise ValueError("due datetime must include a timezone")
            payload["due"]=due.isoformat()
        return await self.client.request("POST", f"https://tasks.googleapis.com/tasks/v1/lists/{tasklist}/tasks", headers=await self._headers(), json=payload)
    async def update_task(self, task_id, changes, tasklist="@default"):
        allowed={k:v for k,v in changes.items() if k in {"title","notes","due","status"}}
        if "due" in allowed:
            due=allowed["due"]
            if isinstance(due,datetime):
                if due.tzinfo is None: raise ValueError("due datetime must include a timezone")
                allowed["due"]=due.isoformat()
            elif isinstance(due,str):
                parsed=datetime.fromisoformat(due.replace("Z","+00:00"))
                if parsed.tzinfo is None: raise ValueError("due datetime must include a timezone")
            else: raise ValueError("due must be a timezone-aware datetime or ISO string")
        return await self.client.request("PATCH", f"https://tasks.googleapis.com/tasks/v1/lists/{tasklist}/tasks/{task_id}", headers=await self._headers(), json=allowed)


class GoogleCalendarService(_GoogleBase):
    async def upcoming(self, *, calendar_id="primary", time_min:datetime):
        if time_min.tzinfo is None: raise ValueError("time_min must include a timezone")
        query=urlencode({"timeMin":time_min.isoformat(),"singleEvents":"true","orderBy":"startTime","maxResults":"20"})
        return await self.client.request("GET", f"https://www.googleapis.com/calendar/v3/calendars/{quote(calendar_id,safe='')}/events?{query}", headers=await self._headers())
    async def create_event(self, summary, start:datetime, end:datetime, *, calendar_id="primary", description="", confirmed=False):
        if start.tzinfo is None or end.tzinfo is None: raise ValueError("calendar datetimes must include a timezone")
        payload={"summary":summary[:250],"description":description[:2000],"start":{"dateTime":start.isoformat()},"end":{"dateTime":end.isoformat()},"extendedProperties":{"private":{"created_by":"scara-wanderer-bots"}}}
        if not confirmed: return {"dry_run":True,"operation":"create_event","payload":payload}
        return await self.client.request("POST", f"https://www.googleapis.com/calendar/v3/calendars/{quote(calendar_id,safe='')}/events", headers=await self._headers(), json=payload)
    async def update_bot_event(self, event_id, existing_event, changes, *, calendar_id="primary", confirmed=False):
        if existing_event.get("extendedProperties",{}).get("private",{}).get("created_by")!="scara-wanderer-bots": raise PermissionError("only bot-created events may be updated")
        allowed={k:v for k,v in changes.items() if k in {"summary","description","start","end"}}
        for key in ("start","end"):
            value=allowed.get(key)
            if value and isinstance(value,dict) and value.get("dateTime"):
                parsed=datetime.fromisoformat(str(value["dateTime"]).replace("Z","+00:00"))
                if parsed.tzinfo is None: raise ValueError("calendar datetimes must include a timezone")
        if not confirmed: return {"dry_run":True,"operation":"update_event","event_id":event_id,"changes":allowed}
        return await self.client.request("PATCH", f"https://www.googleapis.com/calendar/v3/calendars/{quote(calendar_id,safe='')}/events/{event_id}", headers=await self._headers(), json=allowed)


class GoogleSheetsService(_GoogleBase):
    async def append_score_rows(self, spreadsheet_id, rows, *, range_name="Scores!A:D"):
        if not spreadsheet_id or not rows: raise ValueError("spreadsheet and rows are required")
        allowed_ids={str(item) for item in self.account.get("allowed_spreadsheets",[]) if item}
        if spreadsheet_id not in allowed_ids: raise PermissionError("spreadsheet is not allowlisted for scoreboard writes")
        query=urlencode({"valueInputOption":"USER_ENTERED","insertDataOption":"INSERT_ROWS"})
        url=f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/{quote(range_name,safe='')}:append?{query}"
        return await self.client.request("POST", url, headers=await self._headers(), json={"values":rows[:100]})


class SteamService:
    def __init__(self, config, client=None): self.api_key=str(config.get("api_key") or ""); self.client=client or AsyncJSONClient(); self._cache={}
    @property
    def ready(self): return bool(self.api_key)
    async def recently_played(self, steam_id):
        if not self.ready or not str(steam_id).isdigit(): raise ValueError("Steam API key and explicit numeric steam_id are required")
        cached=self._cache.get(str(steam_id))
        if cached and time.time()-cached[0]<900: return cached[1]
        result=await self.client.request("GET", "https://api.steampowered.com/IPlayerService/GetRecentlyPlayedGames/v1/?"+urlencode({"key":self.api_key,"steamid":steam_id,"format":"json"}))
        self._cache[str(steam_id)]=(time.time(),result); return result


class MyAnimeListService:
    def __init__(self, config, client=None): self.client_id=str(config.get("client_id") or ""); self.client=client or AsyncJSONClient(); self._cache={}
    @property
    def ready(self): return bool(self.client_id)
    async def anime_list(self, username):
        if not self.ready or not username.strip(): raise ValueError("MyAnimeList client_id and explicit username are required")
        key=username.strip().lower(); cached=self._cache.get(key)
        if cached and time.time()-cached[0]<900: return cached[1]
        result=await self.client.request("GET", f"https://api.myanimelist.net/v2/users/{username.strip()}/animelist?"+urlencode({"limit":"20","fields":"list_status"}), headers={"X-MAL-CLIENT-ID":self.client_id})
        self._cache[key]=(time.time(),result); return result


class LetterboxdService:
    ready=False
    limitation="No generally available supported API is configured; scraping is intentionally disabled."
    async def activity(self, username): raise IntegrationError(self.limitation)
