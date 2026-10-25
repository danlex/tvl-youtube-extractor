"""TVL YouTube Extractor — FastAPI backend.

POST a YouTube URL; a background worker downloads it, extracts frames and per-beat
clips, transcribes the audio, then a Claude agent segments the narrative into a
story (acts + beats) and translates it. The frontend polls /stream (SSE) for live
progress and renders /result; /summary.html is a portable self-contained download.
"""
import json
import os
import threading
import time
import traceback
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from extractor import agent, pipeline, render

HERE = os.path.dirname(os.path.abspath(__file__))
JOBS_DIR = os.path.join(HERE, "jobs")
os.makedirs(JOBS_DIR, exist_ok=True)

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
    os.makedirs(outdir, exist_ok=True)
    try:
        _set(job_id, step="Reading video info", pct=5)
        info = pipeline.meta(url)
        _set(job_id, title=info["title"])

        _set(job_id, step="Downloading video", pct=20)
        video = pipeline.download(url, outdir)
        duration = pipeline.probe_dur(video)

        _set(job_id, step="Extracting frames", pct=38)
        frames_dir = os.path.join(outdir, "frames")
        frames = pipeline.extract_frames(video, frames_dir, every=5, width=640)

        _set(job_id, step="Transcribing audio", pct=55)
        segments = pipeline.transcribe(video, outdir,
                                       model=os.environ.get("WHISPER_MODEL", "small.en"))
        groups = pipeline.sentence_groups(segments)

        _set(job_id, step="Claude is mapping the story", pct=72)
        story = agent.build_story(groups, duration, cwd=outdir)

        _set(job_id, step=f"Claude is translating ({lang})", pct=84)
        tr = agent.translate(story, groups, lang=lang, cwd=outdir)

        _set(job_id, step="Cutting beat clips", pct=92)
        clips_dir = os.path.join(outdir, "clips")
        os.makedirs(clips_dir, exist_ok=True)
        beats = story["beats"]
        beat_clip_files = []
        for i, b in enumerate(beats):
            nxt = beats[i + 1]["t"] if i + 1 < len(beats) else duration
            d = max(3.0, min(6.0, nxt - b["t"])) if nxt > b["t"] else 6.0
            cp = os.path.join(clips_dir, f"clip_{i:02d}.mp4")
            if not os.path.exists(cp):
                pipeline.cut_clip(video, b["t"], d, cp)
            beat_clip_files.append(cp)

        _set(job_id, step="Assembling", pct=97)
        result = build_result(job_id, info, url, lang, story, tr, beats,
                              beat_clip_files, frames, groups)
        json.dump(result, open(os.path.join(outdir, "result.json"), "w"),
                  ensure_ascii=False, indent=2)

        # portable self-contained HTML (data URIs)
        captions = _captions(groups, tr)
        gallery_du = [(s, pipeline.data_uri(p)) for s, p in frames]
        beat_du = [pipeline.data_uri(p) for p in beat_clip_files]
        html = render.render_html(story, tr, beat_du, gallery_du, captions, url,
                                  lang=lang)
        open(os.path.join(outdir, "summary.html"), "w").write(html)

        _set(job_id, status="done", step="Done", pct=100)
    except Exception as e:
        traceback.print_exc()
        _set(job_id, status="error", step="Failed", error=str(e))


def _captions(groups, tr):
    rot = {round(c["start"], 1): c["text"] for c in tr.get("captions", [])}
    return [(s, en, rot.get(round(s, 1), "")) for s, _d, en in groups]


def build_result(job_id, info, url, lang, story, tr, beats, clip_files, frames, groups):
    color = {a["key"]: render.PALETTE[i % len(render.PALETTE)]
             for i, a in enumerate(story["acts"])}
    labelt = {a["key"]: t["label"] for a, t in zip(story["acts"], tr.get("acts", story["acts"]))}
    tbeats = tr.get("beats", [{} for _ in beats])
    base = f"/media/{job_id}"
    return {
        "id": job_id,
        "title": story["title"],
        "title_t": tr.get("title", ""),
        "source": url,
        "uploader": info.get("uploader", ""),
        "duration": story.get("duration", 0),
        "lang": lang,
        "acts": [{"key": a["key"], "label": a["label"],
                  "label_t": labelt.get(a["key"], ""), "color": color[a["key"]]}
                 for a in story["acts"]],
        "beats": [{
            "t": b["t"], "mmss": pipeline.mmss(b["t"]), "act": b["act"],
            "color": color.get(b["act"], "#999"),
            "title": b["title"], "title_t": tbeats[i].get("title", ""),
            "summary": b["summary"], "summary_t": tbeats[i].get("summary", ""),
            "clip_url": f"{base}/clips/clip_{i:02d}.mp4",
        } for i, b in enumerate(beats)],
        "gallery": [{"sec": s, "mmss": pipeline.mmss(s),
                     "url": f"{base}/frames/{os.path.basename(p)}"} for s, p in frames],
        "captions": [{"start": s, "mmss": pipeline.mmss(s), "en": en,
                      "t": rot} for s, en, rot in _captions(groups, tr)],
    }


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


# Serve the built Next.js static export as a single local app (if present).
# Mounted last so /api and /media routes take precedence.
FRONTEND = os.path.abspath(os.path.join(HERE, "..", "frontend", "out"))
if os.path.isdir(FRONTEND):
    app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="web")
