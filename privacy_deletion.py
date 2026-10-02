"""Resumable, idempotent privacy deletion for Wanderer's independent stores."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import logging
import time
import uuid

import aiosqlite


log = logging.getLogger(__name__)
ACTIVE = {"PENDING", "IN_PROGRESS", "RETRYABLE"}


@dataclass(frozen=True)
class DeletionResult:
    request_id: str
    user_id: int
    status: str
    completed_stages: tuple[str, ...]
    pending_stage: str = ""
    error_category: str = ""

    @property
    def complete(self) -> bool:
        return self.status == "COMPLETE"


class PrivacyDeletionCoordinator:
    """Checkpoint each idempotent deletion stage so an offline relay can retry."""

    def __init__(self, db_path: str, stages: dict[str, object], *, retention_days=30):
        self.db_path = db_path
        self.stages = stages
        self.retention_seconds = max(86400, retention_days * 86400)

    async def _connect(self):
        db = await aiosqlite.connect(self.db_path, timeout=15)
        await db.execute("PRAGMA busy_timeout=15000")
        return db

    async def is_pending(self, user_id: int) -> bool:
        db = await self._connect()
        try:
            exists = await (await db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' "
                "AND name='privacy_deletion_jobs'"
            )).fetchone()
            if not exists:
                return False
            row = await (await db.execute(
                "SELECT 1 FROM privacy_deletion_jobs WHERE user_id=? "
                "AND status IN ('PENDING','IN_PROGRESS','RETRYABLE') LIMIT 1",
                (user_id,),
            )).fetchone()
            return bool(row)
        finally:
            await db.close()

    async def pending_count(self) -> int:
        db = await self._connect()
        try:
            exists = await (await db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' "
                "AND name='privacy_deletion_jobs'"
            )).fetchone()
            if not exists:
                return 0
            row = await (await db.execute(
                "SELECT COUNT(*) FROM privacy_deletion_jobs "
                "WHERE status IN ('PENDING','IN_PROGRESS','RETRYABLE')"
            )).fetchone()
            return int(row[0] or 0)
        finally:
            await db.close()

    async def _load_or_create(self, user_id: int) -> tuple[str, dict]:
        db = await self._connect()
        try:
            await db.execute("BEGIN IMMEDIATE")
            row = await (await db.execute(
                "SELECT request_id,stages_json FROM privacy_deletion_jobs "
                "WHERE user_id=? AND status IN ('PENDING','IN_PROGRESS','RETRYABLE') "
                "ORDER BY created_at DESC LIMIT 1", (user_id,),
            )).fetchone()
            now = time.time()
            if row:
                request_id, stages = row[0], json.loads(row[1] or "{}")
            else:
                request_id, stages = uuid.uuid4().hex, {}
                await db.execute(
                    "INSERT INTO privacy_deletion_jobs VALUES(?,?,?,?,?,?,?,?,?)",
                    (request_id, user_id, "PENDING", "{}", now, now, 0, None, None),
                )
            await db.execute(
                "UPDATE privacy_deletion_jobs SET status='IN_PROGRESS',updated_at=?,"
                "last_error_category=NULL,last_error_stage=NULL WHERE request_id=?",
                (now, request_id),
            )
            await db.commit()
            return request_id, stages
        except BaseException:
            await db.rollback()
            raise
        finally:
            await db.close()

    async def _checkpoint(self, request_id, stages, *, status, error="", stage=""):
        db = await self._connect()
        try:
            now = time.time()
            await db.execute(
                "UPDATE privacy_deletion_jobs SET status=?,stages_json=?,updated_at=?,"
                "completed_at=?,last_error_category=?,last_error_stage=? WHERE request_id=?",
                (status, json.dumps(stages, separators=(",", ":")), now,
                 now if status == "COMPLETE" else 0, error or None, stage or None,
                 request_id),
            )
            await db.commit()
        finally:
            await db.close()

    async def run(self, user_id: int) -> DeletionResult:
        request_id, completed = await self._load_or_create(user_id)
        for stage_name, operation in self.stages.items():
            if completed.get(stage_name) == "COMPLETE":
                continue
            try:
                await operation(user_id)
            except asyncio.CancelledError:
                await self._checkpoint(request_id, completed, status="RETRYABLE",
                                       error="cancelled", stage=stage_name)
                raise
            except Exception as exc:
                category = type(exc).__name__
                await self._checkpoint(request_id, completed, status="RETRYABLE",
                                       error=category, stage=stage_name)
                log.error("privacy deletion stage failed", extra={
                    "request_id": request_id, "user_id": user_id,
                    "subsystem": stage_name, "error_category": category,
                })
                return DeletionResult(request_id, user_id, "RETRYABLE",
                                      tuple(completed), stage_name, category)
            completed[stage_name] = "COMPLETE"
            await self._checkpoint(request_id, completed, status="IN_PROGRESS")
        await self._checkpoint(request_id, completed, status="COMPLETE")
        await self.prune()
        return DeletionResult(request_id, user_id, "COMPLETE", tuple(completed))

    async def prune(self) -> int:
        db = await self._connect()
        try:
            cursor = await db.execute(
                "DELETE FROM privacy_deletion_jobs WHERE status='COMPLETE' "
                "AND completed_at<?", (time.time() - self.retention_seconds,),
            )
            await db.commit()
            return max(0, cursor.rowcount)
        finally:
            await db.close()
