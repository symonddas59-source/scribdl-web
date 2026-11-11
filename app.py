"""Local Flask web UI for scribdl.py.

    pip install -r requirements.txt
    playwright install chromium
    python app.py
    -> open http://127.0.0.1:5000

Environment variables (all optional):
    SCRIBDL_HOST      default 127.0.0.1 (local only)
    SCRIBDL_PORT      default 5000
    SCRIBDL_MAX_JOBS  how many documents download at the same time, default 2
"""
import os
import threading
import uuid
from datetime import datetime

from flask import Flask, Response, abort, jsonify, request, send_file

import scribdl

app = Flask(__name__)

MAX_PARALLEL_JOBS = max(1, int(os.environ.get("SCRIBDL_MAX_JOBS", "2")))
_slots = threading.BoundedSemaphore(MAX_PARALLEL_JOBS)

_jobs = {}
_jobs_lock = threading.Lock()


def _update(job_id, **fields):
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is not None:
            job.update({k: v for k, v in fields.items() if v is not None})


def _public(job):
    """Job info safe to send to the browser (no server file paths)."""
    data = {k: v for k, v in job.items() if k != "output"}
    data["has_file"] = job["status"] == "done" and bool(job.get("output"))
    data["filename"] = os.path.basename(job["output"]) if job.get("output") else None
    return data


def _run_job(job_id, url, pages, scale, delay):
    with _slots:
        _update(job_id, status="running", message="Starting...")
        try:
            result = scribdl.process_download(
                url, None, pages, delay, scale,
                quiet=True, is_batch=True,
                progress_cb=lambda evt: _update(job_id, **evt),
            )
        except Exception as e:  # anything unexpected from Playwright etc.
            _update(job_id, status="error", message=f"{type(e).__name__}: {e}")
            return

    with _jobs_lock:
        job = _jobs[job_id]
        if result:
            job.update(status="done", output=result, message="Done")
        elif job["status"] != "error":
            job.update(status="error", message="Download failed.")


INDEX_HTML = r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Scribd to PDF</title>
<style>
  :root { --bg:#f6f7f9; --card:#fff; --text:#1d2433; --muted:#6b7385; --line:#e3e6ec;
          --accent:#2f6fed; --ok:#1f9d55; --err:#d64545; }
  * { box-sizing: border-box; }
  body { margin:0; font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
         background:var(--bg); color:var(--text); }
  main { max-width:860px; margin:40px auto; padding:0 20px; }
  h1 { font-size:22px; margin:0 0 20px; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:20px; margin-bottom:20px; }
  label { display:block; font-weight:600; font-size:13px; margin-bottom:6px; }
  textarea, input, select { width:100%; padding:9px 10px; border:1px solid var(--line); border-radius:7px;
                            font:inherit; background:#fff; }
  textarea { min-height:90px; resize:vertical; font-family:ui-monospace,Menlo,Consolas,monospace; font-size:13px; }
  .row { display:grid; grid-template-columns:2fr 1fr 1fr; gap:12px; margin-top:14px; }
  .hint { color:var(--muted); font-size:12px; margin-top:4px; }
  .actions { display:flex; gap:10px; align-items:center; margin-top:16px; }
  button { border:0; border-radius:7px; padding:10px 18px; font:inherit; font-weight:600; cursor:pointer;
           background:var(--accent); color:#fff; }
  button.secondary { background:transparent; color:var(--muted); border:1px solid var(--line); }
  button:disabled { opacity:.6; cursor:default; }
  #error { color:var(--err); font-size:13px; }
  .jobs-head { display:flex; justify-content:space-between; align-items:center; margin-bottom:10px; }
  .jobs-head h2 { font-size:16px; margin:0; }
  .job { border-top:1px solid var(--line); padding:12px 0; }
  .job:first-child { border-top:0; }
  .job-top { display:flex; justify-content:space-between; gap:12px; align-items:baseline; }
  .job-title { font-weight:600; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .job-msg { color:var(--muted); font-size:13px; }
  .job.error .job-msg { color:var(--err); }
  .bar { height:6px; background:var(--line); border-radius:3px; margin-top:8px; overflow:hidden; }
  .bar > div { height:100%; background:var(--accent); width:0; transition:width .3s; }
  .job.done .bar > div { background:var(--ok); }
  .job.error .bar > div { background:var(--err); }
  a.dl { color:var(--ok); font-weight:600; text-decoration:none; white-space:nowrap; }
  .empty { color:var(--muted); font-size:14px; }
</style>
</head>
<body>
<main>
  <h1>Scribd to PDF</h1>

  <form id="form" class="card">
    <label for="urls">Document URLs or IDs (one per line)</label>
    <textarea id="urls" name="urls" placeholder="https://www.scribd.com/document/123456789/Example"></textarea>

    <div class="row">
      <div>
        <label for="pages">Pages</label>
        <input id="pages" name="pages" placeholder="all">
        <div class="hint">all, 3, 1-10 or 1-3,7</div>
      </div>
      <div>
        <label for="scale">Quality</label>
        <select id="scale" name="scale">
          <option value="">Default</option>
          <option value="1">1x (smaller)</option>
          <option value="2">2x (sharper)</option>
          <option value="3">3x (largest)</option>
        </select>
      </div>
      <div>
        <label for="delay">Delay (s)</label>
        <input id="delay" name="delay" type="number" step="0.1" min="0" max="10" placeholder="0.5">
      </div>
    </div>

    <div class="actions">
      <button id="submit" type="submit">Convert to PDF</button>
      <span id="error"></span>
    </div>
  </form>

  <section class="card">
    <div class="jobs-head">
      <h2>Jobs</h2>
      <button id="clear" class="secondary" type="button">Clear finished</button>
    </div>
    <div id="jobs"><p class="empty">No jobs yet.</p></div>
  </section>
</main>

<script>
const form = document.getElementById('form');
const jobsEl = document.getElementById('jobs');
const errorEl = document.getElementById('error');
const submitBtn = document.getElementById('submit');

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  errorEl.textContent = '';
  submitBtn.disabled = true;
  try {
    const body = Object.fromEntries(new FormData(form));
    const res = await fetch('/api/jobs', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body)
    });
    const data = await res.json();
    if (!res.ok) { errorEl.textContent = data.error || 'Something went wrong.'; return; }
    form.urls.value = '';
    refresh();
  } catch (err) {
    errorEl.textContent = 'Could not reach the server.';
  } finally {
    submitBtn.disabled = false;
  }
});

document.getElementById('clear').addEventListener('click', async () => {
  await fetch('/api/jobs/clear', {method: 'POST'});
  refresh();
});

function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text != null) n.textContent = text;
  return n;
}

function render(jobs) {
  jobsEl.replaceChildren();
  if (!jobs.length) { jobsEl.append(el('p', 'empty', 'No jobs yet.')); return; }
  for (const j of jobs) {
    const row = el('div', 'job ' + j.status);
    const top = el('div', 'job-top');
    const left = el('div');
    left.style.minWidth = '0';
    left.append(el('div', 'job-title', j.title || j.url));
    const pagesInfo = j.total ? ' · ' + j.current + '/' + j.total : '';
    left.append(el('div', 'job-msg', (j.message || j.status) + pagesInfo));
    top.append(left);
    if (j.has_file) {
      const a = el('a', 'dl', 'Download PDF');
      a.href = '/api/jobs/' + j.id + '/file';
      top.append(a);
    }
    row.append(top);

    const pct = j.status === 'done' || j.status === 'error' ? 100
              : (j.total ? Math.round(j.current / j.total * 100) : 0);
    const bar = el('div', 'bar');
    const fill = el('div');
    fill.style.width = pct + '%';
    bar.append(fill);
    row.append(bar);
    jobsEl.append(row);
  }
}

async function refresh() {
  try {
    const res = await fetch('/api/jobs');
    const data = await res.json();
    render(data.jobs);
  } catch (_) { /* server stopped; keep last view */ }
}

refresh();
setInterval(refresh, 1000);
</script>
</body>
</html>
'''


@app.get("/")
def index():
    return Response(INDEX_HTML, mimetype="text/html")


@app.post("/api/jobs")
def create_jobs():
    data = request.get_json(silent=True) or request.form

    raw_urls = str(data.get("urls", ""))
    urls = [u.strip().strip("'\"") for u in raw_urls.splitlines()]
    urls = [u for u in urls if u and not u.startswith("#")]
    if not urls:
        return jsonify(error="Enter at least one Scribd URL or document ID."), 400

    pages = str(data.get("pages") or "").strip() or "all"

    # Blank scale/delay -> None, so config.ini defaults apply.
    try:
        scale_raw, delay_raw = data.get("scale"), data.get("delay")
        scale = int(scale_raw) if scale_raw not in (None, "") else None
        delay = float(delay_raw) if delay_raw not in (None, "") else None
    except (TypeError, ValueError):
        return jsonify(error="Scale must be a whole number and delay a number."), 400
    if scale is not None:
        scale = min(max(scale, 1), 3)
    if delay is not None:
        delay = min(max(delay, 0.0), 10.0)

    created = []
    for url in urls:
        job_id = uuid.uuid4().hex[:12]
        with _jobs_lock:
            _jobs[job_id] = {
                "id": job_id,
                "url": url,
                "pages": pages,
                "title": None,
                "status": "queued",
                "message": "Waiting for a free slot...",
                "current": 0,
                "total": 0,
                "created": datetime.now().isoformat(timespec="seconds"),
            }
        threading.Thread(
            target=_run_job, args=(job_id, url, pages, scale, delay), daemon=True
        ).start()
        created.append(job_id)

    return jsonify(jobs=created), 202


@app.get("/api/jobs")
def list_jobs():
    with _jobs_lock:
        jobs = [_public(j) for j in _jobs.values()]
    jobs.sort(key=lambda j: j["created"], reverse=True)
    return jsonify(jobs=jobs)


@app.get("/api/jobs/<job_id>")
def get_job(job_id):
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None:
            abort(404)
        return jsonify(_public(job))


@app.get("/api/jobs/<job_id>/file")
def get_file(job_id):
    with _jobs_lock:
        job = _jobs.get(job_id)
        path = job.get("output") if job and job["status"] == "done" else None
    if not path or not os.path.isfile(path):
        abort(404)
    return send_file(path, mimetype="application/pdf", as_attachment=True,
                     download_name=os.path.basename(path))


@app.post("/api/jobs/clear")
def clear_finished():
    """Remove finished/failed jobs from the list (PDFs stay in ./output)."""
    with _jobs_lock:
        for job_id in [k for k, j in _jobs.items() if j["status"] in ("done", "error")]:
            del _jobs[job_id]
    return jsonify(ok=True)


if __name__ == "__main__":
    host = os.environ.get("SCRIBDL_HOST", "127.0.0.1")
    port = int(os.environ.get("SCRIBDL_PORT", "5000"))
    print(f"Open http://{host}:{port}  (Ctrl+C to stop)")
    app.run(host=host, port=port, debug=False, threaded=True)
