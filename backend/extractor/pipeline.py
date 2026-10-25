"""Media pipeline: download a video, extract frames + per-beat clips, transcribe.

System binaries required on PATH: yt-dlp, ffmpeg, ffprobe, whisper-cli.
Whisper model: a ggml model file (default small.en) under WHISPER_MODELS.
"""
import base64
import glob
import json
import os
import re
import subprocess

WHISPER_MODELS = os.environ.get(
    "WHISPER_MODELS",
    os.path.expanduser("~/.cache/hyperframes/whisper/models"),
)


def sh(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"{cmd[0]} failed: {r.stderr.strip()[:500]}")
    return r


def yt_id(url_or_id):
    m = re.search(r"(?:v=|/shorts/|youtu\.be/|/embed/)([A-Za-z0-9_-]{11})", url_or_id)
    if m:
        return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", url_or_id):
        return url_or_id
    raise ValueError(f"could not parse a YouTube id from: {url_or_id}")


def download(url, outdir, maxres=720):
    vid = yt_id(url)
    os.makedirs(outdir, exist_ok=True)
    out = os.path.join(outdir, f"{vid}.mp4")
    if not os.path.exists(out):
        sh(["yt-dlp", "-S", f"res:{maxres},ext:mp4:m4a", "--recode-video", "mp4",
            "-o", out, f"https://www.youtube.com/watch?v={vid}"])
    return out


def probe_dur(path):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", path], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def meta(url):
    """Title + duration without downloading (yt-dlp --dump-json)."""
    vid = yt_id(url)
    r = subprocess.run(
        ["yt-dlp", "--skip-download", "--dump-json",
         f"https://www.youtube.com/watch?v={vid}"],
        capture_output=True, text=True)
    try:
        d = json.loads(r.stdout)
        return {"title": d.get("title", vid), "duration": d.get("duration", 0),
                "uploader": d.get("uploader", ""), "id": vid}
    except json.JSONDecodeError:
        return {"title": vid, "duration": 0, "uploader": "", "id": vid}


def extract_frames(video, frames_dir, every=5, width=640):
    os.makedirs(frames_dir, exist_ok=True)
    dur = probe_dur(video)
    frames = []
    t = 0.0
    while t < max(dur, 1):
        fp = os.path.join(frames_dir, f"f_{int(t):05d}.jpg")
        if not os.path.exists(fp):
            sh(["ffmpeg", "-y", "-v", "error", "-ss", str(t), "-i", video,
                "-frames:v", "1", "-vf", f"scale={width}:-1", "-q:v", "4", fp])
        frames.append((int(t), fp))
        t += every
    return frames


def cut_clip(video, start, dur, out, width=360):
    sh(["ffmpeg", "-y", "-v", "error", "-ss", str(start), "-i", video,
        "-t", str(dur), "-an", "-vf", f"scale={width}:-2",
        "-c:v", "libx264", "-crf", "30", "-preset", "veryfast",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", out])
    return out


def nearest_frame(frames, sec):
    if not frames:
        return None
    return min(frames, key=lambda f: abs(f[0] - sec))[1]


def data_uri(path):
    mime = "video/mp4" if path.endswith(".mp4") else "image/jpeg"
    with open(path, "rb") as f:
        return f"data:{mime};base64," + base64.b64encode(f.read()).decode()


def transcribe(video, workdir, model="small.en"):
    """Extract 16kHz mono audio and run whisper-cli; return normalized segments
    [{text,start,end}] (start/end in seconds)."""
    wav = os.path.join(workdir, "audio.wav")
    if not os.path.exists(wav):
        sh(["ffmpeg", "-y", "-v", "error", "-i", video,
            "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", wav])
    model_path = model if os.path.exists(model) else os.path.join(
        WHISPER_MODELS, f"ggml-{model}.bin")
    if not os.path.exists(model_path):
        raise RuntimeError(f"whisper model not found: {model_path}")
    prefix = os.path.join(workdir, "transcript")
    sh(["whisper-cli", "-m", model_path, "-f", wav, "-oj", "-of", prefix])
    raw = json.load(open(prefix + ".json"))
    segs = []
    for s in raw.get("transcription", []):
        off = s.get("offsets", {})
        segs.append({"text": (s.get("text") or "").strip(),
                     "start": off.get("from", 0) / 1000.0,
                     "end": off.get("to", 0) / 1000.0})
    json.dump(segs, open(prefix + ".json", "w"), indent=2)
    return segs


def sentence_groups(segments):
    """Group whisper segments into sentence-level (start, dur, text) tuples."""
    groups, cur, start, last = [], [], None, None

    def flush():
        if cur and start is not None:
            groups.append((start, (last - start) if last is not None else 0,
                           " ".join(cur)))
    for s in segments:
        tok = (s.get("text") or "").strip()
        if not tok:
            continue
        if start is None:
            start = s["start"]
        cur.append(tok)
        last = s.get("end", s["start"])
        if tok.endswith((".", "?", "!")):
            flush()
            cur, start = [], None
    flush()
    return groups


def mmss(s):
    s = int(s)
    return f"{s // 60}:{s % 60:02d}"
