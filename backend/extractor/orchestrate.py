"""Shared end-to-end orchestration used by both the FastAPI server and the CLI.

extract() runs the full pipeline for one video and writes result.json +
summary.html into outdir, reporting progress through an optional callback.
"""
import json
import os

from . import agent, pipeline, render


def _story_payload(story, tr, duration):
    """A compact story for the live build view (acts + beats with colors)."""
    color = {a["key"]: render.PALETTE[i % len(render.PALETTE)]
             for i, a in enumerate(story["acts"])}
    tb = (tr or {}).get("beats", [])
    return {
        "title": story["title"], "title_t": (tr or {}).get("title", ""),
        "duration": duration,
        "acts": [{"key": a["key"], "label": a["label"], "color": color[a["key"]]}
                 for a in story["acts"]],
        "beats": [{
            "t": b["t"], "mmss": pipeline.mmss(b["t"]), "act": b["act"],
            "color": color.get(b["act"], "#999"), "title": b["title"],
            "title_t": (tb[i].get("title", "") if i < len(tb) else ""),
        } for i, b in enumerate(story["beats"])],
    }


def _captions(groups, tr):
    rot = {round(c["start"], 1): c["text"] for c in tr.get("captions", [])}
    return [(s, en, rot.get(round(s, 1), "")) for s, _d, en in groups]


def build_result(job_id, info, url, lang, story, tr, beats, clip_files, frames, groups):
    color = {a["key"]: render.PALETTE[i % len(render.PALETTE)]
             for i, a in enumerate(story["acts"])}
    labelt = {a["key"]: t["label"]
              for a, t in zip(story["acts"], tr.get("acts", story["acts"]))}
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
        "captions": [{"start": s, "mmss": pipeline.mmss(s), "en": en, "t": rot}
                     for s, en, rot in _captions(groups, tr)],
    }


def extract(job_id, url, lang, outdir, progress=None):
    """Run the full pipeline. progress is an optional callable(**fields) receiving
    e.g. step=/pct=/title=. Returns {result, result_path, html_path}."""
    p = progress or (lambda **k: None)
    os.makedirs(outdir, exist_ok=True)

    p(step="Reading video info", pct=5)
    info = pipeline.meta(url)
    p(title=info["title"])

    p(step="Downloading video", pct=20)
    video = pipeline.download(url, outdir)
    duration = pipeline.probe_dur(video)
    p(duration=duration)

    p(step="Extracting frames", pct=38)
    frames = pipeline.extract_frames(video, os.path.join(outdir, "frames"),
                                     every=5, width=640)

    p(step="Transcribing", pct=55)
    segments, tsource = pipeline.transcribe_source(
        video, url, outdir,
        whisper_model=os.environ.get("WHISPER_MODEL", "small.en"),
        prefer=os.environ.get("TRANSCRIBE_PREFER", "captions"))
    p(step=f"Transcript via {tsource}", pct=60)
    groups = pipeline.sentence_groups(segments)

    p(step=f"Claude is mapping the story ({lang})", pct=72)
    story, tr = agent.build_and_translate(groups, duration, lang=lang, cwd=outdir)
    p(step="Story ready", pct=88, story=_story_payload(story, tr, duration))

    p(step="Cutting beat clips", pct=92)
    clips_dir = os.path.join(outdir, "clips")
    os.makedirs(clips_dir, exist_ok=True)
    beats = story["beats"]
    clip_files = []
    for i, b in enumerate(beats):
        nxt = beats[i + 1]["t"] if i + 1 < len(beats) else duration
        d = max(3.0, min(6.0, nxt - b["t"])) if nxt > b["t"] else 6.0
        cp = os.path.join(clips_dir, f"clip_{i:02d}.mp4")
        if not os.path.exists(cp):
            pipeline.cut_clip(video, b["t"], d, cp)
        clip_files.append(cp)

    p(step="Assembling", pct=97)
    result = build_result(job_id, info, url, lang, story, tr, beats,
                          clip_files, frames, groups)
    result_path = os.path.join(outdir, "result.json")
    json.dump(result, open(result_path, "w"), ensure_ascii=False, indent=2)

    captions = _captions(groups, tr)

    # Lightweight view.html — media via /media URLs (fast, embeds cleanly in the UI).
    base = f"/media/{job_id}"
    gallery_urls = [(s, f"{base}/frames/{os.path.basename(p)}") for s, p in frames]
    beat_urls = [f"{base}/clips/{os.path.basename(c)}" for c in clip_files]
    view = render.render_html(story, tr, beat_urls, gallery_urls, captions, url, lang=lang)
    open(os.path.join(outdir, "view.html"), "w").write(view)

    # Self-contained summary.html — all media inlined as data URIs (for download/share).
    gallery_du = [(s, pipeline.data_uri(pth)) for s, pth in frames]
    beat_du = [pipeline.data_uri(pth) for pth in clip_files]
    html = render.render_html(story, tr, beat_du, gallery_du, captions, url, lang=lang)
    html_path = os.path.join(outdir, "summary.html")
    open(html_path, "w").write(html)

    p(step="Done", pct=100)
    return {"result": result, "result_path": result_path, "html_path": html_path}
