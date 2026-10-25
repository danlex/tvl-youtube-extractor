"""TVL YouTube Extractor — FastAPI backend.

POST a YouTube URL; a background worker downloads it, extracts frames and per-beat
clips, transcribes the audio, then a Claude agent segments the narrative into a
story (acts + beats) and translates it. The frontend polls /stream (SSE) for live
progress and renders /result; /summary.html is a portable self-contained download.
"""
import hashlib
import json
import os
import re
import threading
import time
import traceback
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from extractor import agent, mailer, orchestrate, pipeline

HERE = os.path.dirname(os.path.abspath(__file__))
JOBS_DIR = os.path.join(HERE, "jobs")
os.makedirs(JOBS_DIR, exist_ok=True)

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000").rstrip("/")
SALT = os.environ.get("TVLX_SALT", "tvl-youtube-extractor")
DEFAULT_LANG = os.environ.get("DEFAULT_LANG", "Romanian")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

app = FastAPI(title="TVL YouTube Extractor")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/media", StaticFiles(directory=JOBS_DIR), name="media")

JOBS = {}  # id -> {status, step, pct, error, title}


def _set(job_id, **kw):
    JOBS[job_id].update(kw)


class ExtractReq(BaseModel):
    url: str
    lang: str = "Romanian"


def run_job(job_id, url, lang):
    outdir = os.path.join(JOBS_DIR, job_id)
    try:
        orchestrate.extract(job_id, url, lang, outdir,
                            progress=lambda **k: _set(job_id, **k))
        _set(job_id, status="done", step="Done", pct=100)
    except Exception as e:
        traceback.print_exc()
        _set(job_id, status="error", step="Failed", error=str(e))


# ----------------------------------------------------------------- product: email + md5
class SubmitReq(BaseModel):
    url: str
    email: str
    lang: str = DEFAULT_LANG


def _hash(url, email):
    vid = pipeline.yt_id(url)
    return hashlib.md5(f"{vid}|{email.lower()}|{SALT}".encode()).hexdigest()


def run_email_job(h, url, email, lang):
    outdir = os.path.join(JOBS_DIR, h)
    link = f"{BASE_URL}/view?h={h}"
    try:
        orchestrate.extract(h, url, lang, outdir)
        meta = json.load(open(os.path.join(outdir, "result.json")))
        subj, html = mailer.ready_email(meta.get("title", "your video"), link)
        mailer.send(email, subj, html)
        print(f"[job {h}] done → {link}")
    except Exception:
        traceback.print_exc()


@app.post("/api/submit")
def submit(req: SubmitReq):
    try:
        pipeline.yt_id(req.url)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not EMAIL_RE.match(req.email or ""):
        raise HTTPException(400, "please enter a valid email")
    h = _hash(req.url, req.email)
    outdir = os.path.join(JOBS_DIR, h)
    link = f"{BASE_URL}/view?h={h}"
    if os.path.exists(os.path.join(outdir, "summary.html")):
        subj, html = mailer.ready_email("your video", link)
        mailer.send(req.email, subj, html)
        return {"status": "ready", "view": link}
    threading.Thread(target=run_email_job, args=(h, req.url, req.email, req.lang),
                     daemon=True).start()
    return {"status": "queued", "view": link}


@app.get("/view", response_class=HTMLResponse)
def view(h: str):
    if not re.fullmatch(r"[a-f0-9]{32}", h or ""):
        raise HTTPException(400, "bad id")
    path = os.path.join(JOBS_DIR, h, "summary.html")
    if os.path.exists(path):
        return FileResponse(path, media_type="text/html")
    return HTMLResponse(
        "<!doctype html><meta charset=utf-8><meta http-equiv=refresh content=10>"
        "<title>Still cooking…</title>"
        "<body style='font:17px/1.6 -apple-system,sans-serif;background:#f6f1e9;"
        "color:#16130f;display:grid;place-items:center;height:90vh;text-align:center'>"
        "<div><h1 style='color:#ff4931'>Still cooking…</h1>"
        "<p>Your page isn't ready yet. This refreshes automatically, and we'll "
        "email you the moment it's done.</p></div>", status_code=202)


@app.post("/api/extract")
def extract(req: ExtractReq):
    try:
        pipeline.yt_id(req.url)
    except ValueError as e:
        raise HTTPException(400, str(e))
    job_id = uuid.uuid4().hex[:12]
    JOBS[job_id] = {"status": "running", "step": "Queued", "pct": 0,
                    "error": None, "title": ""}
    threading.Thread(target=run_job, args=(job_id, req.url, req.lang),
                     daemon=True).start()
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(404, "unknown job")
    return {"id": job_id, **JOBS[job_id]}


@app.get("/api/jobs/{job_id}/stream")
def job_stream(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(404, "unknown job")

    def gen():
        last = None
        while True:
            state = JOBS.get(job_id, {})
            snap = json.dumps({"id": job_id, **state})
            if snap != last:
                yield f"data: {snap}\n\n"
                last = snap
            if state.get("status") in ("done", "error"):
                break
            time.sleep(0.6)
    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/api/jobs/{job_id}/result")
def job_result(job_id: str):
    path = os.path.join(JOBS_DIR, job_id, "result.json")
    if not os.path.exists(path):
        raise HTTPException(404, "result not ready")
    return json.load(open(path))


@app.get("/api/jobs/{job_id}/summary.html")
def job_html(job_id: str):
    path = os.path.join(JOBS_DIR, job_id, "summary.html")
    if not os.path.exists(path):
        raise HTTPException(404, "summary not ready")
    return FileResponse(path, media_type="text/html",
                        filename=f"{job_id}-summary.html")


@app.get("/api/health")
def health():
    return {"ok": True,
            "auth": "api-key" if agent.USE_SDK else "claude-cli-session",
            "model": agent.MODEL or "session default"}


# Serve the product landing (backend/web) — or the built Next.js export if present.
# Mounted last so /api, /media, /view take precedence.
WEB = os.path.join(HERE, "web")
NEXT = os.path.abspath(os.path.join(HERE, "..", "frontend", "out"))
_root = WEB if os.path.isdir(WEB) else (NEXT if os.path.isdir(NEXT) else None)
if _root:
    app.mount("/", StaticFiles(directory=_root, html=True), name="web")
