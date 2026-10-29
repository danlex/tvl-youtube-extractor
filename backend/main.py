"""TVL YouTube Extractor — FastAPI backend.

POST a YouTube URL; a background worker downloads it, extracts frames and per-beat
clips, transcribes the audio, then a Claude agent segments the narrative into a
story (acts + beats) and translates it. The frontend polls /stream (SSE) for live
progress and renders /result; /summary.html is a portable self-contained download.
"""
import hashlib
import json
import os
import threading
import time
import traceback

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from extractor import agent, orchestrate, pipeline

HERE = os.path.dirname(os.path.abspath(__file__))
JOBS_DIR = os.path.join(HERE, "jobs")
os.makedirs(JOBS_DIR, exist_ok=True)
JOB_TTL_DAYS = float(os.environ.get("JOB_TTL_DAYS", "7"))


def prune_jobs():
    """Drop job folders older than JOB_TTL_DAYS so disk doesn't grow forever."""
    import shutil
    cutoff = time.time() - JOB_TTL_DAYS * 86400
    for name in os.listdir(JOBS_DIR):
        p = os.path.join(JOBS_DIR, name)
        try:
            if os.path.isdir(p) and os.path.getmtime(p) < cutoff:
                shutil.rmtree(p, ignore_errors=True)
        except OSError:
            pass


prune_jobs()

app = FastAPI(title="TVL YouTube Extractor")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/media", StaticFiles(directory=JOBS_DIR), name="media")

JOBS = {}  # id -> {status, step, pct, error, title}


def _set(job_id, **kw):
    JOBS[job_id].update(kw)
    try:
        d = os.path.join(JOBS_DIR, job_id)
        os.makedirs(d, exist_ok=True)
        json.dump({"id": job_id, **JOBS[job_id]},
                  open(os.path.join(d, "state.json"), "w"))
    except OSError:
        pass


def _load_jobs():
    """Restore known jobs from disk so /stream + the recent list survive a restart."""
    for name in os.listdir(JOBS_DIR):
        sp = os.path.join(JOBS_DIR, name, "state.json")
        if not os.path.exists(sp):
            continue
        try:
            st = json.load(open(sp))
            st.pop("id", None)
            if st.get("status") == "running":  # thread is gone after a restart
                st["status"] = "error"
                st["error"] = "interrupted (server restarted)"
            JOBS[name] = st
        except (OSError, ValueError):
            pass


_load_jobs()


class ExtractReq(BaseModel):
    url: str
    lang: str = "Romanian"


# Cap how many extractions run at once (each is CPU-heavy). Extra jobs wait.
_SLOTS = threading.Semaphore(max(1, int(os.environ.get("JOB_CONCURRENCY", "2"))))


def run_job(job_id, url, lang):
    outdir = os.path.join(JOBS_DIR, job_id)
    if not _SLOTS.acquire(blocking=False):
        _set(job_id, step="Waiting for a free slot…")
        _SLOTS.acquire()
    try:
        orchestrate.extract(job_id, url, lang, outdir,
                            progress=lambda **k: _set(job_id, **k))
        _set(job_id, status="done", step="Done", pct=100)
    except Exception as e:
        traceback.print_exc()
        _set(job_id, status="error", step="Failed",
             error=pipeline.friendly_error(str(e)))
    finally:
        _SLOTS.release()


@app.post("/api/extract")
def extract(req: ExtractReq):
    if not pipeline.valid_source(req.url):
        raise HTTPException(400, "not a valid video URL, id, or local file path")
    # content-addressed id: same source + language reuses a finished result
    key = hashlib.md5(
        f"{pipeline.source_id(req.url)}|{req.lang}".encode()).hexdigest()[:12]
    outdir = os.path.join(JOBS_DIR, key)
    if os.path.exists(os.path.join(outdir, "view.html")) and \
       os.path.exists(os.path.join(outdir, "result.json")):
        if JOBS.get(key, {}).get("status") != "done":
            try:
                title = json.load(open(os.path.join(outdir, "result.json")))["title"]
            except (OSError, ValueError, KeyError):
                title = ""
            JOBS[key] = {"status": "done", "step": "Done", "pct": 100,
                         "error": None, "title": title}
        return {"job_id": key, "cached": True}
    if JOBS.get(key, {}).get("status") == "running":
        return {"job_id": key}
    JOBS[key] = {"status": "running", "step": "Queued", "pct": 0,
                 "error": None, "title": ""}
    threading.Thread(target=run_job, args=(key, req.url, req.lang),
                     daemon=True).start()
    return {"job_id": key}


@app.get("/api/recent")
def recent(limit: int = 12):
    def mtime(name):
        p = os.path.join(JOBS_DIR, name, "state.json")
        return os.path.getmtime(p) if os.path.exists(p) else 0
    done = [{"id": n, "title": s.get("title", ""),
             "view": f"/api/jobs/{n}/view.html"}
            for n, s in JOBS.items() if s.get("status") == "done"]
    done.sort(key=lambda x: mtime(x["id"]), reverse=True)
    return {"recent": done[:limit]}


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


@app.get("/api/jobs/{job_id}/frames")
def job_frames(job_id: str):
    """Frames produced so far — lets the UI show the result building live."""
    d = os.path.join(JOBS_DIR, job_id, "frames")
    if not os.path.isdir(d):
        return {"frames": []}
    fs = sorted(f for f in os.listdir(d) if f.endswith(".jpg"))
    return {"frames": [f"/media/{job_id}/frames/{f}" for f in fs]}


@app.get("/api/jobs/{job_id}/view.html")
def job_view(job_id: str):
    """Lightweight page (media via /media URLs) — embeds cleanly in the app iframe."""
    path = os.path.join(JOBS_DIR, job_id, "view.html")
    if not os.path.exists(path):
        path = os.path.join(JOBS_DIR, job_id, "summary.html")  # older jobs
    if not os.path.exists(path):
        raise HTTPException(404, "not ready")
    return FileResponse(path, media_type="text/html")


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
