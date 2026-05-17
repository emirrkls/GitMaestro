from __future__ import annotations

import logging
import os
import re
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, Field

from db import JobStore, default_db_path
from ui import _esc, _status_badge, render_events_timeline, render_index, render_job_detail

_REPO_RE = re.compile(r"^[\w.-]+/[\w.-]+$")

security = HTTPBasic(auto_error=False)


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _verify_ui(creds: HTTPBasicCredentials | None) -> str:
    user = _env("REMOTE_UI_USERNAME")
    password = _env("REMOTE_UI_PASSWORD")
    if not user or not password:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="REMOTE_UI_USERNAME and REMOTE_UI_PASSWORD must be set",
        )
    if creds is None or creds.username != user or creds.password != password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return creds.username


def _verify_worker_token(request: Request) -> None:
    expected = _env("WORKER_TOKEN")
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="WORKER_TOKEN must be set on the server",
        )
    auth = request.headers.get("Authorization", "")
    if auth != f"Bearer {expected}":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid worker token")


logger = logging.getLogger("gitmaestro.queue")
logging.basicConfig(level=logging.INFO)

store = JobStore(default_db_path())
app = FastAPI(title="GitMaestro remote queue", version="0.1.0")


class CreateJobBody(BaseModel):
    repo: str = Field(..., min_length=3, max_length=200)
    issue: str = Field(..., min_length=1, max_length=2000)


class FinishJobBody(BaseModel):
    job_id: str
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    task_id: str | None = None
    events_jsonl: str | None = None
    error: str | None = None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    creds: Annotated[HTTPBasicCredentials | None, Depends(security)],
) -> HTMLResponse:
    _verify_ui(creds)
    jobs = store.list_jobs(30)
    rows = []
    for j in jobs:
        rid = _esc(j.id[:8])
        repo = _esc(j.repo)
        iss = _esc(j.issue_ref[:80])
        link = f'<a href="/jobs/{_esc(j.id)}">Detay →</a>'
        rows.append(
            f"<tr><td><code>{rid}</code></td><td>{_status_badge(j.status)}</td>"
            f"<td>{repo}</td><td>{iss}</td><td>{link}</td></tr>"
        )
    table = "\n".join(rows) if rows else '<tr><td colspan="5" class="empty">Henüz iş yok</td></tr>'
    return HTMLResponse(render_index(table))


@app.post("/jobs", response_model=None)
async def create_job_form(
    request: Request,
    creds: Annotated[HTTPBasicCredentials | None, Depends(security)],
) -> Response:
    """HTML form fallback (tarayıcılar POST'ta Basic Auth göndermeyebilir)."""
    _verify_ui(creds)
    form = await request.form()
    repo = str(form.get("repo", "")).strip()
    issue = str(form.get("issue", "")).strip()
    if not _REPO_RE.match(repo):
        raise HTTPException(status_code=400, detail="repo must look like owner/name")
    try:
        job = store.create_job(repo, issue)
    except Exception as exc:
        logger.exception("create_job failed")
        raise HTTPException(status_code=500, detail=f"queue_error: {exc}") from exc
    if not job:
        raise HTTPException(status_code=500, detail="job_not_persisted")
    if form.get("redirect"):
        base = str(request.base_url).rstrip("/")
        return RedirectResponse(url=f"{base}/jobs/{job.id}", status_code=303)
    return JSONResponse({"job_id": job.id, "status": job.status})


@app.post("/api/jobs")
def create_job_api(
    body: CreateJobBody,
    creds: Annotated[HTTPBasicCredentials | None, Depends(security)],
) -> JSONResponse:
    _verify_ui(creds)
    repo = body.repo.strip()
    if not _REPO_RE.match(repo):
        raise HTTPException(status_code=400, detail="repo must look like owner/name")
    try:
        job = store.create_job(repo, body.issue.strip())
    except Exception as exc:
        logger.exception("create_job failed")
        raise HTTPException(status_code=500, detail=f"queue_error: {exc}") from exc
    if not job:
        raise HTTPException(status_code=500, detail="job_not_persisted")
    return JSONResponse({"job_id": job.id, "status": job.status})


@app.get("/jobs/{job_id}", response_class=HTMLResponse)
def job_detail_html(
    job_id: str,
    creds: Annotated[HTTPBasicCredentials | None, Depends(security)],
) -> HTMLResponse:
    _verify_ui(creds)
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    try:
        events_html = render_events_timeline(job.events_jsonl)
        page = render_job_detail(
            job_id=job.id,
            status=job.status,
            repo=job.repo,
            issue_ref=job.issue_ref,
            task_id=job.task_id,
            error=job.error,
            stdout_text=job.stdout_text,
            events_html=events_html,
        )
    except Exception as exc:
        logger.exception("job_detail render failed job_id=%s", job_id)
        page = (
            f"<html><body><p>Job {_esc(job.id)} — render hatası: {_esc(str(exc))}</p>"
            f'<p><a href="/">Ana sayfa</a></p></body></html>'
        )
    return HTMLResponse(page)


@app.get("/api/jobs/{job_id}")
def job_detail_api(
    job_id: str,
    creds: Annotated[HTTPBasicCredentials | None, Depends(security)],
) -> JSONResponse:
    _verify_ui(creds)
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return JSONResponse(
        {
            "id": job.id,
            "status": job.status,
            "repo": job.repo,
            "issue_ref": job.issue_ref,
            "created_at": job.created_at,
            "started_at": job.started_at,
            "finished_at": job.finished_at,
            "task_id": job.task_id,
            "error": job.error,
            "stdout_text": job.stdout_text,
            "events_jsonl": job.events_jsonl,
        }
    )


@app.post("/worker/claim")
def worker_claim(request: Request) -> JSONResponse:
    _verify_worker_token(request)
    job = store.claim_next_pending()
    if not job:
        return JSONResponse({"job": None})
    return JSONResponse(
        {
            "job": {
                "id": job.id,
                "repo": job.repo,
                "issue_ref": job.issue_ref,
            }
        }
    )


@app.post("/worker/finish")
def worker_finish(request: Request, body: FinishJobBody) -> JSONResponse:
    _verify_worker_token(request)
    job = store.get_job(body.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    if job.status not in ("running", "pending"):
        return JSONResponse({"ok": True, "note": "job already finished"})
    final_status = "done" if body.exit_code == 0 and not body.error else "failed"
    err = body.error
    if body.exit_code != 0 and not err:
        err = f"exit_code={body.exit_code}"
    combined_out = body.stdout
    if body.stderr:
        combined_out += "\n--- stderr ---\n" + body.stderr
    store.finish_job(
        body.job_id,
        status=final_status,
        error=err,
        stdout_text=combined_out,
        events_jsonl=body.events_jsonl,
        task_id=body.task_id,
    )
    return JSONResponse({"ok": True, "status": final_status})


if __name__ == "__main__":
    import uvicorn

    port = int(_env("PORT", "8000"))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False)
