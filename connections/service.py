"""User-owned connections, explicit bot grants, one-use OAuth, and durable refresh."""
from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
import time

from .providers import GoogleProvider, MODULE_SCOPES, masked_email
from .security import Cipher, ConnectionError, Settings
from .store import Store, one

BOTS = ("scaramouche", "wanderer")
TTL = 600


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def envelope_context(row, *, session=False):
    return f"{row['user_id']}:{row['provider']}:" + (
        f"session:{row['bot_name']}:{row['id']}" if session else f"account:{row['revision']}")


class ConnectedAccountService:
    def __init__(self, path, settings=None, *, providers=None, clock=time.time):
        self.store = Store(path)
        self.settings = settings or Settings.from_env()
        self.providers = providers or {"google": GoogleProvider(self.settings)}
        self.clock = clock

    def _provider(self, provider):
        if provider not in self.providers:
            raise ConnectionError("INVALID_PROVIDER")
        return self.providers[provider]

    def _cipher(self):
        self.settings.validate()
        return Cipher(self.settings.master_key)

    @property
    def configured(self):
        try:
            self._cipher()
            return True
        except ConnectionError:
            return False

    async def create_session(self, user_id, bot_name, provider="google"):
        self._provider(provider)
        self._cipher()
        if bot_name not in BOTS or int(user_id) <= 0:
            raise ConnectionError("INVALID_REQUEST")
        now, link, sid = self.clock(), secrets.token_urlsafe(32), secrets.token_hex(16)
        bucket = int(now // 900)
        async with self.store.transaction() as db:
            await db.execute("DELETE FROM connection_sessions WHERE expires_at<=?", (now,))
            await db.execute("DELETE FROM connection_attempts WHERE bucket<?", (bucket,))
            await db.execute("DELETE FROM connection_admission WHERE bucket<?", (bucket,))
            attempt = await one(db, "SELECT count FROM connection_attempts WHERE user_id=?", (user_id,))
            total = await one(db, "SELECT count FROM connection_admission WHERE bucket=?", (bucket,))
            count = await one(db, "SELECT count(*) AS n FROM connection_sessions")
            if (attempt and attempt["count"] >= 3) or (total and total["count"] >= 100) or count["n"] >= 256:
                raise ConnectionError("RATE_LIMITED")
            await db.execute("INSERT INTO connection_attempts VALUES (?,?,1) ON CONFLICT(user_id) DO UPDATE SET count=count+1", (user_id, bucket))
            await db.execute("INSERT INTO connection_admission VALUES (?,1) ON CONFLICT(bucket) DO UPDATE SET count=count+1", (bucket,))
            await db.execute("DELETE FROM connection_sessions WHERE user_id=? AND provider=? AND bot_name=?", (user_id, provider, bot_name))
            await db.execute("""INSERT INTO connection_sessions
                (id,user_id,provider,bot_name,link_hash,redirect_uri,stage,created_at,expires_at)
                VALUES (?,?,?,?,?,?,'NEW',?,?)""",
                (sid, user_id, provider, bot_name, digest(link), self.settings.redirect_uri, now, now + TTL))
        return self.settings.origin + f"/oauth/{provider}/start/" + link

    async def begin(self, link, browser, provider="google"):
        adapter, cipher = self._provider(provider), self._cipher()
        if not 32 <= len(link) <= 128 or not 32 <= len(browser) <= 128:
            raise ConnectionError("INVALID_SESSION")
        state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
        async with self.store.transaction() as db:
            row = await one(db, "SELECT * FROM connection_sessions WHERE link_hash=? AND provider=? AND stage='NEW' AND expires_at>?",
                            (digest(link), provider, self.clock()))
            if not row or row["redirect_uri"] != self.settings.redirect_uri:
                raise ConnectionError("INVALID_SESSION")
            await db.execute("UPDATE connection_sessions SET stage='STARTED',state_hash=?,browser_hash=?,sealed=? WHERE id=?",
                             (digest(state), digest(browser), cipher.seal(verifier, envelope_context(row, session=True)), row["id"]))
        return adapter.authorization_url(state, verifier)

    async def callback(self, *, state, browser, code="", error="", provider="google"):
        adapter, cipher = self._provider(provider), self._cipher()
        if not 32 <= len(state) <= 128 or not 32 <= len(browser) <= 128 or len(code) > 4096:
            raise ConnectionError("INVALID_SESSION")
        async with self.store.transaction() as db:
            row = await one(db, "SELECT * FROM connection_sessions WHERE state_hash=? AND provider=? AND stage='STARTED' AND expires_at>?",
                            (digest(state), provider, self.clock()))
            if (not row or row["redirect_uri"] != self.settings.redirect_uri or
                    not secrets.compare_digest(row["browser_hash"], digest(browser))):
                raise ConnectionError("INVALID_SESSION")
            # Commit consumption even when the provider denied authorization.
            await db.execute("UPDATE connection_sessions SET stage='EXCHANGING',state_hash=NULL,browser_hash=NULL WHERE id=?", (row["id"],))
        try:
            if error:
                raise ConnectionError("CANCELLED")
            if not code:
                raise ConnectionError("MISSING_CODE")
            result = await adapter.exchange(code, cipher.open(row["sealed"], envelope_context(row, session=True)))
            credentials, scopes, expiry = self._tokens(result, require_refresh=True, provider=provider)
            identity = await adapter.identity(credentials["access_token"])
            masked = masked_email(identity)
            credentials["provider_account_id"] = str(identity["sub"])
            async with self.store.transaction() as db:
                cursor = await db.execute("""UPDATE connection_sessions SET stage='CONFIRM',sealed=?,masked_identity=?,scopes=?,expiry=?
                    WHERE id=? AND stage='EXCHANGING' AND expires_at>?""",
                    (cipher.seal(credentials, envelope_context(row, session=True)), masked, json.dumps(scopes), expiry, row["id"], self.clock()))
                if cursor.rowcount != 1:
                    raise ConnectionError("INVALID_SESSION")
            return "AWAITING_DISCORD_CONFIRMATION"
        except BaseException:
            async with self.store.transaction() as db:
                await db.execute("DELETE FROM connection_sessions WHERE id=?", (row["id"],))
            raise

    def _tokens(self, result, *, require_refresh=False, previous=None, previous_scopes=None, provider="google"):
        previous = previous or {}
        if not isinstance(result, dict):
            raise ConnectionError("PROVIDER_UNAVAILABLE")
        access = result.get("access_token")
        refresh = result.get("refresh_token") or previous.get("refresh_token")
        if not isinstance(access, str) or not access or len(access) > 16384:
            raise ConnectionError("PROVIDER_UNAVAILABLE")
        if (require_refresh or previous) and (not isinstance(refresh, str) or not refresh or len(refresh) > 16384):
            raise ConnectionError("MISSING_REFRESH_TOKEN")
        try:
            seconds = int(result["expires_in"])
            if not 0 < seconds <= 86400 or str(result.get("token_type", "Bearer")).lower() != "bearer":
                raise ValueError()
            scopes = sorted(set(str(result["scope"]).split())) if "scope" in result else previous_scopes
            if not scopes or not any(s in scopes for s in self._provider(provider).module_scopes.values()):
                raise ConnectionError("SCOPES_MISSING")
        except (ValueError, TypeError, KeyError, OverflowError):
            raise ConnectionError("PROVIDER_UNAVAILABLE") from None
        return {**previous, "access_token": access, "refresh_token": refresh}, scopes, self.clock() + seconds

    async def pending(self, user_id, bot_name):
        async with self.store.transaction() as db:
            return await one(db, "SELECT id,masked_identity,scopes FROM connection_sessions WHERE user_id=? AND bot_name=? AND stage='CONFIRM' AND expires_at>?",
                             (user_id, bot_name, self.clock()))

    async def confirm_link(self, user_id, bot_name, session_id):
        cipher = self._cipher()
        revision, now = secrets.token_hex(16), self.clock()
        async with self.store.transaction() as db:
            row = await one(db, "SELECT * FROM connection_sessions WHERE id=? AND user_id=? AND bot_name=? AND stage='CONFIRM' AND expires_at>?",
                            (session_id, user_id, bot_name, now))
            if not row:
                raise ConnectionError("INVALID_SESSION")
            credentials = cipher.open(row["sealed"], envelope_context(row, session=True))
            # Replacing a Google account deliberately resets ALL grants, including a partner bot.
            await db.execute("DELETE FROM connected_accounts WHERE user_id=? AND provider=?", (user_id, row["provider"]))
            await db.execute("""INSERT INTO connected_accounts
                (user_id,provider,revision,masked_identity,credentials,scopes,status,expiry,connected_at,updated_at)
                VALUES (?,?,?,?,?,?,'CONNECTED',?,?,?)""",
                (user_id, row["provider"], revision, row["masked_identity"], cipher.seal(credentials, envelope_context({**row, "revision": revision})),
                 row["scopes"], row["expiry"], now, now))
            await db.execute("INSERT INTO connected_account_bot_grants VALUES (?,?,?,1)", (user_id, row["provider"], bot_name))
            await db.execute("DELETE FROM connection_sessions WHERE user_id=? AND provider=?", (user_id, row["provider"]))

    async def status(self, user_id, provider="google"):
        self._provider(provider)
        async with self.store.transaction() as db:
            row = await one(db, "SELECT revision,masked_identity,scopes,status FROM connected_accounts WHERE user_id=? AND provider=?", (user_id, provider))
            if not row:
                return {"status": "NOT_CONNECTED", "grants": {}, "modules": []}
            async with db.execute("SELECT bot_name,enabled FROM connected_account_bot_grants WHERE user_id=? AND provider=?", (user_id, provider)) as cursor:
                grants = {r["bot_name"]: bool(r["enabled"]) for r in await cursor.fetchall()}
        return {"status": row["status"], "revision": row["revision"], "masked_identity": row["masked_identity"], "grants": grants,
                "modules": [name for name, scope in self._provider(provider).module_scopes.items() if scope in json.loads(row["scopes"])]}

    async def grant(self, user_id, bot_name, enabled, provider="google", *, expected_revision=None):
        self._provider(provider)
        if bot_name not in BOTS:
            raise ConnectionError("INVALID_REQUEST")
        async with self.store.transaction() as db:
            row = await one(db, "SELECT status,revision FROM connected_accounts WHERE user_id=? AND provider=?", (user_id, provider))
            if not row or row["status"] != "CONNECTED":
                raise ConnectionError("NOT_CONNECTED")
            if expected_revision is not None and row["revision"] != expected_revision:
                raise ConnectionError("ACCOUNT_CHANGED")
            await db.execute("INSERT INTO connected_account_bot_grants VALUES (?,?,?,?) ON CONFLICT(user_id,provider,bot_name) DO UPDATE SET enabled=excluded.enabled",
                             (user_id, provider, bot_name, int(bool(enabled))))

    async def _authorized(self, db, user_id, bot_name, provider, module):
        module_scopes = self._provider(provider).module_scopes
        if bot_name not in BOTS or module not in module_scopes:
            raise ConnectionError("FORBIDDEN")
        row = await one(db, "SELECT * FROM connected_accounts WHERE user_id=? AND provider=?", (user_id, provider))
        if not row or row["status"] != "CONNECTED":
            raise ConnectionError(row["status"] if row else "NOT_CONNECTED")
        grant = await one(db, "SELECT enabled FROM connected_account_bot_grants WHERE user_id=? AND provider=? AND bot_name=?", (user_id, provider, bot_name))
        if not grant or not grant["enabled"]:
            raise ConnectionError("BOT_DISABLED")
        if module_scopes[module] not in json.loads(row["scopes"]):
            raise ConnectionError("SCOPES_MISSING")
        return row

    async def authorize(self, user_id, bot_name, module, provider="google"):
        self._provider(provider)
        self._cipher()
        async with self.store.transaction() as db:
            row = await self._authorized(db, user_id, bot_name, provider, module)
            return row["revision"]

    async def get_google(self, user_id, bot_name, module="calendar"):
        return await self.access_token(user_id, bot_name, module, "google")

    async def access_token(self, user_id, bot_name, module, provider="google"):
        cipher, adapter = self._cipher(), self._provider(provider)
        owner = secrets.token_hex(16)
        for _ in range(10):
            async with self.store.transaction() as db:
                row = await self._authorized(db, user_id, bot_name, provider, module)
                credentials = cipher.open(row["credentials"], envelope_context(row))
                now = self.clock()
                if row["expiry"] > now + 60:
                    return credentials["access_token"]
                if row["retry_after"] > now:
                    raise ConnectionError("REFRESH_BACKOFF")
                acquired = row["refresh_until"] <= now
                if acquired:
                    await db.execute("UPDATE connected_accounts SET refresh_owner=?,refresh_until=? WHERE revision=?",
                                     (owner, now + 40, row["revision"]))
            if acquired:
                break
            await asyncio.sleep(0.2)
        else:
            raise ConnectionError("REFRESH_BUSY")
        try:
            result = await adapter.refresh(credentials["refresh_token"])
            fresh, scopes, expiry = self._tokens(result, previous=credentials, previous_scopes=json.loads(row["scopes"]), provider=provider)
            async with self.store.transaction() as db:
                # Persist rotation for the canonical account even if this bot's grant was
                # disabled during HTTP. Never recreate a deleted/replaced connection.
                current = await one(db, "SELECT revision,refresh_owner FROM connected_accounts WHERE user_id=? AND provider=?", (user_id, provider))
                if not current or current["revision"] != row["revision"] or current["refresh_owner"] != owner:
                    raise ConnectionError("NOT_CONNECTED")
                await db.execute("""UPDATE connected_accounts SET credentials=?,scopes=?,expiry=?,last_refresh_at=?,
                    updated_at=?,refresh_owner=NULL,refresh_until=0,retry_after=0 WHERE revision=? AND refresh_owner=?""",
                    (cipher.seal(fresh, envelope_context(row)), json.dumps(scopes), expiry, self.clock(), self.clock(), row["revision"], owner))
            if await self.authorize(user_id, bot_name, module, provider) != row["revision"]:
                raise ConnectionError("ACCOUNT_CHANGED")
            if self._provider(provider).module_scopes[module] not in scopes:
                raise ConnectionError("SCOPES_MISSING")
            return fresh["access_token"]
        except BaseException as exc:
            revoked = isinstance(exc, ConnectionError) and exc.code == "REAUTH_REQUIRED"
            async with self.store.transaction() as db:
                if revoked:
                    await db.execute("UPDATE connected_accounts SET status='REAUTH_REQUIRED',credentials=NULL,refresh_owner=NULL,refresh_until=0 WHERE revision=? AND refresh_owner=?", (row["revision"], owner))
                else:
                    await db.execute("UPDATE connected_accounts SET refresh_owner=NULL,refresh_until=0,retry_after=? WHERE revision=? AND refresh_owner=?", (self.clock() + 30, row["revision"], owner))
            raise

    async def disconnect(self, user_id, provider="google", *, expected_revision=None):
        adapter = self._provider(provider)
        token = None
        async with self.store.transaction() as db:
            row = await one(db, "SELECT user_id,provider,revision,credentials FROM connected_accounts WHERE user_id=? AND provider=?", (user_id, provider))
            if expected_revision is not None and (not row or row["revision"] != expected_revision):
                raise ConnectionError("ACCOUNT_CHANGED")
            if row and row["credentials"]:
                try:
                    token = self._cipher().open(row["credentials"], envelope_context(row))["refresh_token"]
                except ConnectionError:
                    pass  # Local erasure must also work with a missing/wrong key.
            await db.execute("DELETE FROM connection_sessions WHERE user_id=? AND provider=?", (user_id, provider))
            await db.execute("DELETE FROM connected_accounts WHERE user_id=? AND provider=?", (user_id, provider))
        if not token:
            return "LOCAL_DELETED_REMOTE_UNVERIFIED" if row else "DISCONNECTED"
        try:
            return "DISCONNECTED" if await adapter.revoke(token) else "LOCAL_DELETED_REMOTE_UNVERIFIED"
        except Exception:
            return "LOCAL_DELETED_REMOTE_UNVERIFIED"

    async def forget(self, user_id):
        # Idempotent saga stage. Local erasure is authoritative, remote revoke best effort.
        for provider in self.providers:
            await self.disconnect(user_id, provider)
        async with self.store.transaction() as db:
            await db.execute("DELETE FROM connection_attempts WHERE user_id=?", (user_id,))

    async def notification_candidates(self, bot_name):
        async with self.store.transaction() as db:
            await db.execute("DELETE FROM connection_sessions WHERE expires_at<=?", (self.clock(),))
            async with db.execute("SELECT id,user_id FROM connection_sessions WHERE bot_name=? AND stage='CONFIRM' AND notified=0 LIMIT 20", (bot_name,)) as cursor:
                rows = [dict(row) for row in await cursor.fetchall()]
            for row in rows:
                await db.execute("UPDATE connection_sessions SET notified=1 WHERE id=?", (row["id"],))
            return rows
