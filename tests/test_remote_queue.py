from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

try:
    import fastapi  # noqa: F401
except ImportError:
    fastapi = None

ROOT = Path(__file__).resolve().parents[1]
QUEUE_SERVER_DIR = ROOT / "remote" / "queue_server"


@unittest.skipUnless(fastapi is not None, 'install with: pip install -e ".[remote]"')
class RemoteQueueApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._td = tempfile.TemporaryDirectory()
        td = Path(cls._td.name)
        os.environ["REMOTE_UI_USERNAME"] = "u"
        os.environ["REMOTE_UI_PASSWORD"] = "p"
        os.environ["WORKER_TOKEN"] = "tok"
        os.environ["QUEUE_DB_PATH"] = str(td / "queue.db")
        for mod in ("app", "db"):
            sys.modules.pop(mod, None)
        sys.path.insert(0, str(QUEUE_SERVER_DIR))
        import app as queue_app  # noqa: E402

        cls._queue_app = queue_app
        from fastapi.testclient import TestClient  # noqa: E402

        cls._TestClient = TestClient

    @classmethod
    def tearDownClass(cls) -> None:
        p = str(QUEUE_SERVER_DIR)
        while p in sys.path:
            sys.path.remove(p)
        for mod in ("app", "db"):
            sys.modules.pop(mod, None)
        cls._td.cleanup()

    def test_create_claim_finish(self) -> None:
        c = self._TestClient(self._queue_app.app)
        self.assertEqual(c.get("/health").status_code, 200)
        r = c.post("/api/jobs", auth=("u", "p"), json={"repo": "o/r", "issue": "99"})
        self.assertEqual(r.status_code, 200, r.text)
        jid = r.json()["job_id"]
        r = c.post("/worker/claim", headers={"Authorization": "Bearer tok"})
        self.assertEqual(r.status_code, 200)
        job = r.json()["job"]
        self.assertIsNotNone(job)
        self.assertEqual(job["id"], jid)
        r = c.post(
            "/worker/finish",
            headers={"Authorization": "Bearer tok"},
            json={
                "job_id": jid,
                "exit_code": 0,
                "stdout": "[maestro] task_id=t1\n[maestro] run_dir=/tmp\n",
                "stderr": "",
                "task_id": "t1",
                "events_jsonl": "{}\n",
                "error": None,
            },
        )
        self.assertEqual(r.status_code, 200)
        r = c.get(f"/api/jobs/{jid}", auth=("u", "p"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "done")
        self.assertEqual(r.json()["task_id"], "t1")
