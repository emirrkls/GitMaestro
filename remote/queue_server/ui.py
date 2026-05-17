from __future__ import annotations

import html
import json
from typing import Any

_AGENT_COLORS: dict[str, str] = {
    "Maestro": "#8b5cf6",
    "Analyst": "#3b82f6",
    "Scout": "#06b6d4",
    "Surgeon": "#22c55e",
    "Critic": "#f97316",
    "Tester": "#eab308",
    "Scribe": "#6366f1",
    "SafetyGate": "#64748b",
    "TesterPolicy": "#94a3b8",
    "System": "#475569",
}

_TYPE_COLORS: dict[str, str] = {
    "task": "#2563eb",
    "result": "#16a34a",
    "feedback": "#d97706",
    "decision": "#7c3aed",
}

_STYLES = """
:root {
  --bg: #0f1419;
  --surface: #1a2332;
  --surface2: #243044;
  --border: #2d3a4f;
  --text: #e7ecf3;
  --muted: #8b9cb3;
  --accent: #3b82f6;
  --accent-hover: #60a5fa;
  --ok: #22c55e;
  --warn: #eab308;
  --err: #ef4444;
  --radius: 10px;
  font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  min-height: 100vh;
  background: var(--bg);
  color: var(--text);
  line-height: 1.5;
}
.wrap { max-width: 920px; margin: 0 auto; padding: 1.5rem 1.25rem 3rem; }
.wrap-wide { max-width: 1100px; }
a { color: var(--accent-hover); text-decoration: none; }
a:hover { text-decoration: underline; }
.topbar {
  display: flex; align-items: center; gap: 1rem; margin-bottom: 1.75rem;
}
.logo { font-weight: 700; font-size: 1.15rem; letter-spacing: -0.02em; }
.logo span { color: var(--accent-hover); }
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 1.25rem 1.35rem;
  margin-bottom: 1.25rem;
}
.card h2 { margin: 0 0 1rem; font-size: 1rem; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.04em; }
label { display: block; font-size: 0.85rem; color: var(--muted); margin-bottom: 0.35rem; }
input[type=text] {
  width: 100%; max-width: 100%;
  padding: 0.65rem 0.75rem;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface2);
  color: var(--text);
  font-size: 0.95rem;
}
input:focus { outline: 2px solid var(--accent); border-color: transparent; }
.field { margin-bottom: 1rem; }
.btn {
  display: inline-block;
  padding: 0.65rem 1.25rem;
  background: var(--accent);
  color: #fff;
  border: none;
  border-radius: 8px;
  font-weight: 600;
  font-size: 0.95rem;
  cursor: pointer;
}
.btn:hover { background: var(--accent-hover); }
.form-error { color: var(--err); font-size: 0.9rem; margin-bottom: 0.75rem; display: none; }
table.jobs { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
table.jobs th, table.jobs td { padding: 0.6rem 0.5rem; text-align: left; border-bottom: 1px solid var(--border); }
table.jobs th { color: var(--muted); font-weight: 500; font-size: 0.75rem; text-transform: uppercase; }
table.jobs tr:hover td { background: var(--surface2); }
.badge {
  display: inline-block;
  padding: 0.15rem 0.5rem;
  border-radius: 999px;
  font-size: 0.72rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}
.badge-pending { background: #422006; color: #fcd34d; }
.badge-running { background: #1e3a5f; color: #93c5fd; }
.badge-done { background: #14532d; color: #86efac; }
.badge-failed { background: #450a0a; color: #fca5a5; }
.agent {
  display: inline-block;
  padding: 0.12rem 0.45rem;
  border-radius: 6px;
  font-size: 0.78rem;
  font-weight: 600;
  color: #fff;
}
.meta-row { display: flex; flex-wrap: wrap; gap: 0.75rem 1.25rem; margin-bottom: 1rem; font-size: 0.9rem; }
.meta-row dt { color: var(--muted); margin: 0; }
.meta-row dd { margin: 0; font-weight: 500; }
.timeline { display: flex; flex-direction: column; gap: 0.75rem; }
.event {
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 0.85rem 1rem;
  border-left: 4px solid var(--border);
}
.event-type-task { border-left-color: #3b82f6; }
.event-type-result { border-left-color: #22c55e; }
.event-type-feedback { border-left-color: #f59e0b; }
.event-type-decision { border-left-color: #a855f7; }
.event-head {
  display: flex; flex-wrap: wrap; align-items: center; gap: 0.4rem 0.6rem;
  margin-bottom: 0.5rem;
}
.event-arrow { color: var(--muted); font-size: 0.85rem; }
.event-type-tag {
  font-size: 0.7rem;
  text-transform: uppercase;
  padding: 0.1rem 0.4rem;
  border-radius: 4px;
  background: var(--surface);
  color: var(--muted);
}
.event-time { margin-left: auto; font-size: 0.75rem; color: var(--muted); font-variant-numeric: tabular-nums; }
.event-summary {
  font-size: 0.88rem;
  color: var(--text);
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.45;
}
.event details { margin-top: 0.6rem; }
.event summary {
  cursor: pointer;
  font-size: 0.78rem;
  color: var(--muted);
  user-select: none;
}
.event pre {
  margin: 0.5rem 0 0;
  padding: 0.75rem;
  background: var(--bg);
  border-radius: 6px;
  font-size: 0.75rem;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 280px;
  overflow-y: auto;
}
.log-block {
  font-family: ui-monospace, "Cascadia Code", Consolas, monospace;
  font-size: 0.78rem;
  background: var(--bg);
  border-radius: 8px;
  padding: 0.75rem;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 200px;
  overflow: auto;
  color: var(--muted);
}
.empty { color: var(--muted); font-style: italic; font-size: 0.9rem; }
.pulse { animation: pulse 2s ease-in-out infinite; }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.55} }
"""


def _esc(s: str) -> str:
    return html.escape(s, quote=True)


def _agent_badge(name: str) -> str:
    color = _AGENT_COLORS.get(name, "#64748b")
    return f'<span class="agent" style="background:{_esc(color)}">{_esc(name)}</span>'


def _status_badge(status: str) -> str:
    s = status.lower()
    cls = f"badge badge-{s}" if s in ("pending", "running", "done", "failed") else "badge"
    return f'<span class="{cls}">{_esc(status)}</span>'


def _format_time(ts: str | None) -> str:
    if not ts:
        return "—"
    # 2026-05-17T21:34:33.386219+00:00 -> 21:34:33
    if "T" in ts:
        part = ts.split("T", 1)[1]
        return part[:8] if len(part) >= 8 else part
    return ts[:19]


def _summarize_content(ev: dict[str, Any]) -> str:
    content = ev.get("content")
    if not isinstance(content, dict):
        return ""
    ev_type = str(ev.get("type", ""))
    parts: list[str] = []

    if ev_type == "task":
        task = content.get("task")
        if task:
            parts.append(f"Görev: {task}")
        if content.get("retry") is not None:
            parts.append(f"retry={content.get('retry')}")

    elif ev_type == "feedback":
        decision = content.get("decision")
        if decision:
            parts.append(f"Karar: {decision}")
        fb = content.get("feedback")
        if isinstance(fb, list) and fb:
            parts.append("Geri bildirim: " + "; ".join(str(x) for x in fb[:3]))
        model = content.get("critic_model")
        if model:
            parts.append(f"model={model}")

    elif ev_type == "decision":
        for key in ("final_decision", "passed", "next", "reason"):
            if key in content and content[key] is not None:
                parts.append(f"{key}={content[key]}")

    elif ev_type == "result":
        if "triage_decision" in content:
            parts.append(
                f"Triage: {content.get('triage_decision')} "
                f"(risk={content.get('risk')}, complexity={content.get('complexity_hint')})"
            )
            rat = content.get("maestro_rationale")
            if rat:
                parts.append(str(rat)[:400])
        if "analysis" in content:
            parts.append(str(content["analysis"])[:500])
        if "scout_notes" in content:
            parts.append(str(content["scout_notes"])[:400])
        if "command" in content:
            passed = content.get("passed")
            parts.append(f"Test: {content['command']} → {'PASS' if passed else 'FAIL'}")
        if "patch_diff" in content and content["patch_diff"]:
            diff = str(content["patch_diff"])
            lines = diff.strip().splitlines()
            preview = "\n".join(lines[:12])
            if len(lines) > 12:
                preview += f"\n… (+{len(lines) - 12} satır)"
            parts.append(preview)
        if "commit_message" in content:
            parts.append(f"Commit: {content['commit_message']}")
        if "surgeon_status" in content:
            parts.append(
                f"Surgeon: {content.get('surgeon_status')} "
                f"strategy={content.get('strategy_used')} file={content.get('touched_file')}"
            )
        if "test_comparison" in content:
            tc = content["test_comparison"]
            if isinstance(tc, dict):
                parts.append(tc.get("summary", str(tc)[:300]))

    if not parts:
        # fallback: first few keys
        for k, v in list(content.items())[:4]:
            if isinstance(v, (str, int, float, bool)):
                parts.append(f"{k}: {v}")
            elif isinstance(v, list) and len(v) <= 3:
                parts.append(f"{k}: {v}")
    return "\n".join(parts)


def render_events_timeline(events_jsonl: str | None) -> str:
    if not events_jsonl or not events_jsonl.strip():
        return '<p class="empty">Henüz olay yok — worker çalışınca veya iş bitince burada görünür.</p>'

    items: list[str] = []
    for i, line in enumerate(events_jsonl.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            items.append(
                f'<article class="event"><p class="event-summary">Satır {i}: geçersiz JSON</p>'
                f"<pre>{_esc(line[:500])}</pre></article>"
            )
            continue

        sender = str(ev.get("sender", "?"))
        receiver = str(ev.get("receiver", "?"))
        ev_type = str(ev.get("type", "event"))
        ts = _format_time(ev.get("timestamp"))
        conf = ev.get("confidence")
        conf_s = f' <span class="event-type-tag">conf {conf:.2f}</span>' if isinstance(conf, (int, float)) else ""

        summary = _summarize_content(ev)
        if not summary:
            summary = "(özet yok)"
        raw = _esc(json.dumps(ev, indent=2, ensure_ascii=False)[:8000])

        items.append(
            f'<article class="event event-type-{_esc(ev_type)}">'
            f'<div class="event-head">'
            f"{_agent_badge(sender)}"
            f'<span class="event-arrow">→</span>'
            f"{_agent_badge(receiver)}"
            f'<span class="event-type-tag">{_esc(ev_type)}</span>{conf_s}'
            f'<span class="event-time">{_esc(ts)}</span>'
            f"</div>"
            f'<div class="event-summary">{_esc(summary)}</div>'
            f"<details><summary>Ham JSON</summary><pre>{raw}</pre></details>"
            f"</article>"
        )

    if not items:
        return '<p class="empty">Olay dosyası boş.</p>'
    return '<div class="timeline">' + "".join(items) + "</div>"


def page_shell(title: str, body: str, *, wide: bool = False) -> str:
    wrap = "wrap wrap-wide" if wide else "wrap"
    return f"""<!DOCTYPE html>
<html lang="tr">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{_esc(title)}</title>
  <style>{_STYLES}</style>
</head>
<body>
  <div class="{wrap}">
    {body}
  </div>
</body>
</html>"""


def render_index(jobs_rows_html: str) -> str:
    body = f"""
    <header class="topbar">
      <div class="logo">Git<span>Maestro</span> Remote</div>
    </header>
    <section class="card">
      <h2>Yeni çalıştırma</h2>
      <p style="margin:0 0 1rem;color:var(--muted);font-size:0.9rem;">
        İş evdeki bilgisayardaki worker tarafından alınır (Ollama + maestro).
      </p>
      <p id="form-error" class="form-error"></p>
      <form id="enqueue-form">
        <div class="field">
          <label for="repo">Repository <code>owner/name</code></label>
          <input type="text" id="repo" name="repo" required placeholder="emirrkls/GitMaestroRemoteTest"/>
        </div>
        <div class="field">
          <label for="issue">Issue (numara veya GitHub URL)</label>
          <input type="text" id="issue" name="issue" required placeholder="1"/>
        </div>
        <button type="submit" class="btn">Kuyruğa ekle</button>
      </form>
    </section>
    <section class="card">
      <h2>Son işler</h2>
      <table class="jobs">
        <thead><tr><th>ID</th><th>Durum</th><th>Repo</th><th>Issue</th><th></th></tr></thead>
        <tbody>{jobs_rows_html}</tbody>
      </table>
    </section>
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
    """
    return page_shell("GitMaestro Remote", body)


def render_job_detail(
    *,
    job_id: str,
    status: str,
    repo: str,
    issue_ref: str,
    task_id: str | None,
    error: str | None,
    stdout_text: str | None,
    events_html: str,
) -> str:
    pulse = ' class="pulse"' if status in ("pending", "running") else ""
    reload_script = ""
    if status in ("pending", "running"):
        reload_script = "<script>setTimeout(() => location.reload(), 8000);</script>"

    stdout_block = ""
    if stdout_text and stdout_text.strip():
        stdout_block = f"""
        <section class="card">
          <h2>Maestro stdout</h2>
          <div class="log-block">{_esc(stdout_text[:50000])}</div>
        </section>
        """

    err_block = ""
    if error:
        err_block = f"""
        <section class="card">
          <h2>Hata</h2>
          <div class="log-block" style="color:var(--err)">{_esc(error)}</div>
        </section>
        """

    body = f"""
    <header class="topbar">
      <a href="/">← Ana sayfa</a>
    </header>
    <section class="card">
      <h2>İş özeti</h2>
      <dl class="meta-row">
        <div><dt>Job ID</dt><dd><code>{_esc(job_id)}</code></dd></div>
        <div><dt>Durum</dt><dd{_pulse}>{_status_badge(status)}</dd></div>
        <div><dt>Repo</dt><dd>{_esc(repo)}</dd></div>
        <div><dt>Issue</dt><dd>{_esc(issue_ref)}</dd></div>
        <div><dt>task_id</dt><dd><code>{_esc(task_id or "—")}</code></dd></div>
      </dl>
    </section>
    <section class="card">
      <h2>Olay akışı (agent mesajları)</h2>
      {events_html}
    </section>
    {stdout_block}
    {err_block}
    {reload_script}
    """
    return page_shell(f"Job {job_id[:8]}", body, wide=True)

