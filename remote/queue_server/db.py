from __future__ import annotations

import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Job:
    id: str
    status: str
    repo: str
    issue_ref: str
    created_at: str
    started_at: str | None
    finished_at: str | None
    error: str | None
    stdout_text: str | None
    events_jsonl: str | None
    task_id: str | None


class JobStore:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._lock = threading.Lock()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_schema(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    repo TEXT NOT NULL,
                    issue_ref TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    error TEXT,
                    stdout_text TEXT,
                    events_jsonl TEXT,
                    task_id TEXT
                )
                """
            )
            conn.commit()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            conn = self._connect()
            try:
                yield conn
            finally:
                conn.close()

    def create_job(self, repo: str, issue_ref: str) -> Job:
        job_id = str(uuid.uuid4())
        created = _utc_now()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO jobs (id, status, repo, issue_ref, created_at)
                VALUES (?, 'pending', ?, ?, ?)
                """,
                (job_id, repo, issue_ref, created),
            )
            conn.commit()
        return self.get_job(job_id)

    def get_job(self, job_id: str) -> Job | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return _row_to_job(row) if row else None

    def list_jobs(self, limit: int = 50) -> list[Job]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [_row_to_job(r) for r in rows]

    def claim_next_pending(self) -> Job | None:
        """Atomically move one pending job to running; return it or None."""
        with self._conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """
                SELECT id FROM jobs
                WHERE status = 'pending'
                ORDER BY created_at ASC
                LIMIT 1
                """
            ).fetchone()
            if not row:
                conn.rollback()
                return None
            job_id = row["id"]
            started = _utc_now()
            conn.execute(
                """
                UPDATE jobs SET status = 'running', started_at = ?
                WHERE id = ? AND status = 'pending'
                """,
                (started, job_id),
            )
            if conn.total_changes != 1:
                conn.rollback()
                return None
            conn.commit()
            row2 = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return _row_to_job(row2) if row2 else None

    def finish_job(
        self,
        job_id: str,
        *,
        status: str,
        error: str | None,
        stdout_text: str | None,
        events_jsonl: str | None,
        task_id: str | None,
    ) -> None:
        finished = _utc_now()
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE jobs
                SET status = ?, finished_at = ?, error = ?,
                    stdout_text = ?, events_jsonl = ?, task_id = ?
                WHERE id = ?
                """,
                (status, finished, error, stdout_text, events_jsonl, task_id, job_id),
            )
            conn.commit()


def _row_to_job(row: sqlite3.Row) -> Job:
    return Job(
        id=row["id"],
        status=row["status"],
        repo=row["repo"],
        issue_ref=row["issue_ref"],
        created_at=row["created_at"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        error=row["error"],
        stdout_text=row["stdout_text"],
        events_jsonl=row["events_jsonl"],
        task_id=row["task_id"],
    )


def default_db_path() -> Path:
    raw = os.environ.get("QUEUE_DB_PATH", "").strip()
    if raw:
        return Path(raw)
    return Path(__file__).resolve().parent / "queue.db"
