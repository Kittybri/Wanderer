import queue
import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
import sys
import types

import video_render_worker as worker
vision_stub = types.ModuleType("character_vision")
vision_stub.ask_character_bot = lambda *args, **kwargs: ""
sys.modules.setdefault("character_vision", vision_stub)
import video_reports


class RenderQueueTests(unittest.TestCase):
    def setUp(self):
        worker.JOB_QUEUE = queue.Queue()
        worker.JOBS.clear()
        worker.ACTIVE_FINGERPRINTS.clear()
        worker.SUCCESS_DURATIONS.clear()
        worker.ACTIVE_JOB_ID = None

    def _add(self, job_id, created):
        job = {
            "job_id": job_id, "job_type": "teaching", "bot_name": "wanderer",
            "title": "Title", "notes_text": "notes", "status": "queued",
            "created_at": created, "updated_at": created, "summary": {}, "error": "",
            "env_overrides": {}, "fingerprint": job_id,
        }
        worker.JOBS[job_id] = job
        worker.ACTIVE_FINGERPRINTS[job_id] = job_id
        worker.JOB_QUEUE.put(job_id)
        return job

    def test_fifo_position_and_duplicate_fingerprint(self):
        first = self._add("first", 1)
        second = self._add("second", 2)
        self.assertEqual(worker._queue_position_locked(first), 1)
        self.assertEqual(worker._queue_position_locked(second), 2)
        self.assertEqual(
            worker._job_fingerprint("teaching", "wanderer", "x", "y"),
            worker._job_fingerprint("teaching", "wanderer", "x", "y"),
        )

    def test_failure_does_not_block_next_fifo_job(self):
        self._add("bad", 1)
        self._add("good", 2)
        with patch.object(worker, "_make_job_dir"), patch.object(worker, "_script_for_job"), \
             patch.object(worker, "_run_render_script", side_effect=[RuntimeError("boom"), {"final_video": ""}]):
            self.assertEqual(worker._process_next_job(), "bad")
            self.assertEqual(worker.JOBS["bad"]["status"], "failed")
            self.assertEqual(worker._process_next_job(), "good")
            self.assertEqual(worker.JOBS["good"]["status"], "done")
            self.assertEqual(worker.JOB_QUEUE.unfinished_tasks, 0)

    def test_cancelled_job_is_skipped_and_cleaned(self):
        job = self._add("cancel", 1)
        job["status"] = "cancelled"
        self.assertEqual(worker._process_next_job(), "cancel")
        self.assertNotIn("cancel", worker.ACTIVE_FINGERPRINTS)

    def test_restart_recovery_marks_incomplete_work_failed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / "knownjob"
            folder.mkdir()
            (folder / "job_payload.json").write_text(json.dumps({"script": "notes_to_wanderer_video.py", "title": "Recovered"}))
            with patch.object(worker, "_video_root", return_value=root):
                self.assertEqual(worker._recover_job_state(), 1)
            self.assertEqual(worker.JOBS["knownjob"]["status"], "failed")

    def test_duo_features_have_bounded_handoffs(self):
        source = Path("bot.py").read_text(encoding="utf-8")
        self.assertIn('channel_id, "finish", topic', source)
        self.assertIn("autoplay_turns=2", source)
        self.assertIn('"intervention"', source)
        self.assertIn("autoplay_turns=1", source)


class RenderProgressTests(unittest.IsolatedAsyncioTestCase):
    async def test_async_progress_callback_is_awaited(self):
        seen = []

        async def callback(payload):
            seen.append(payload["queue_position"])

        await video_reports._notify_render_progress(callback, {"queue_position": 3})
        self.assertEqual(seen, [3])

    async def test_progress_notice_failure_does_not_fail_render_transport(self):
        async def callback(_payload):
            raise RuntimeError("discord unavailable")

        self.assertIsNone(await video_reports._notify_render_progress(callback, {"queue_position": 1}))


if __name__ == "__main__":
    unittest.main()
