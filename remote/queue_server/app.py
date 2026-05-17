from __future__ import annotations

import html
import logging
import os
import re
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, Field

from db import JobStore, default_db_path

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
        st = html.escape(j.status)
        rid = html.escape(j.id[:8])
        repo = html.escape(j.repo)
        iss = html.escape(j.issue_ref[:80])
        link = f'<a href="/jobs/{html.escape(j.id)}">detay</a>'
        rows.append(f"<tr><td>{rid}</td><td>{st}</td><td>{repo}</td><td>{iss}</td><td>{link}</td></tr>")
    table = "\n".join(rows) if rows else "<tr><td colspan=5>Henüz iş yok</td></tr>"
    body = f"""<!DOCTYPE html>
<html lang="tr"><head><meta charset="utf-8"/><title>GitMaestro queue</title>
<style>body{{font-family:system-ui,sans-serif;max-width:960px;margin:2rem auto;}}
table{{border-collapse:collapse;width:100%;}}td,th{{border:1px solid #ccc;padding:6px;text-align:left;}}
code{{background:#f4f4f4;padding:2px 4px;}}</style></head><body>
<h1>GitMaestro — uzaktan kuyruk</h1>
<p>Yeni çalıştırma (evdeki worker işi alır):</p>
<p id="form-error" style="color:#b00020;display:none;"></p>
<form id="enqueue-form">
  <label>repo <code>owner/name</code><br/><input name="repo" id="repo" size="40" required placeholder="emirrkls/GitMaestroRemoteTest"/></label><br/><br/>
  <label>issue (numara veya URL)<br/><input name="issue" id="issue" size="60" required placeholder="1"/></label><br/><br/>
  <button type="submit">Kuyruğa ekle</button>
</form>
<script>
document.getElementById("enqueue-form").addEventListener("submit", async (e) => {{
  e.preventDefault();
  const err = document.getElementById("form-error");
  err.style.display = "none";
  const repo = document.getElementById("repo").value.trim();
  const issue = document.getElementById("issue").value.trim();
  try {{
    const res = await fetch("/api/jobs", {{
      method: "POST",
      credentials: "same-origin",
      headers: {{ "Content-Type": "application/json" }},
      body: JSON.stringify({{ repo, issue }}),
    }});
    const data = await res.json().catch(() => ({{}}));
    if (!res.ok) {{
      err.textContent = data.detail || ("HTTP " + res.status);
      err.style.display = "block";
      return;
    }}
    window.location.href = "/jobs/" + data.job_id;
  }} catch (ex) {{
    err.textContent = String(ex);
    err.style.display = "block";
  }}
}});
</script>
<h2>Son işler</h2>
<table><thead><tr><th>id</th><th>durum</th><th>repo</th><th>issue</th><th></th></tr></thead>
<tbody>{table}</tbody></table>
</body></html>"""
    return HTMLResponse(body)


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
    ev = job.events_jsonl or ""
    ev_preview = html.escape(ev[:120_000]) if ev else "(henüz yok veya worker yüklemedi)"
    out = html.escape((job.stdout_text or "")[:50_000])
    err = html.escape(job.error or "")
    body = f"""<!DOCTYPE html>
<html lang="tr"><head><meta charset="utf-8"/><title>Job {html.escape(job.id[:8])}</title>
<style>body{{font-family:monospace;max-width:1100px;margin:1rem auto;white-space:pre-wrap;}}
nav a{{font-family:system-ui;}}</style></head><body>
<nav><a href="/">← Ana sayfa</a></nav>
<h1>Job <code>{html.escape(job.id)}</code></h1>
<p>durum: <strong>{html.escape(job.status)}</strong> repo={html.escape(job.repo)} issue={html.escape(job.issue_ref)}</p>
<p>task_id: {html.escape(job.task_id or "")}</p>
<h2>events.jsonl (kısaltılmış)</h2>
{ev_preview}
<h2>stdout (kısaltılmış)</h2>
{out}
<h2>error</h2>
{err}
<script>setTimeout(() => location.reload(), 8000);</script>
</body></html>"""
    return HTMLResponse(body)


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
