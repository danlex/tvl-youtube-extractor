"""Media pipeline: download a video, extract frames + per-beat clips, transcribe.

System binaries required on PATH: yt-dlp, ffmpeg, ffprobe, whisper-cli.
Whisper model: a ggml model file (default small.en) under WHISPER_MODELS.
"""
import base64
import hashlib
import html
import json
import time
import os
import re
import shutil
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


def _ytdlp_opts():
    """Shared yt-dlp flags from env — cookies / proxy / JS runtime / extras.
    Lets self-hosters get past datacenter-IP blocks without code changes."""
    opts = []
    rt = os.environ.get("YTDLP_JS_RUNTIME")
    if rt:
        opts += ["--js-runtimes", rt]
    ck = os.path.expanduser(os.environ.get("YTDLP_COOKIES", ""))
    if ck and os.path.exists(ck):
        opts += ["--cookies", ck]
    cb = os.environ.get("YTDLP_COOKIES_FROM_BROWSER")
    if cb:
        opts += ["--cookies-from-browser", cb]
    px = os.environ.get("YTDLP_PROXY")
    if px:
        opts += ["--proxy", px]
    extra = os.environ.get("YTDLP_EXTRA")
    if extra:
        opts += extra.split()
    return opts


def friendly_error(text):
    """Map a raw yt-dlp / pipeline error to a clear, user-facing message."""
    t = (text or "").lower()
    if "sign in to confirm" in t or "not a bot" in t or "429" in t:
        return ("YouTube is blocking this network (common on servers/VPNs). Run it "
                "locally, or set YTDLP_COOKIES / YTDLP_PROXY.")
    if "private video" in t:
        return "That video is private."
    if "members-only" in t or "join this channel" in t:
        return "That video is members-only."
    if "age" in t and "confirm" in t:
        return "That video is age-restricted — add YTDLP_COOKIES from a logged-in account."
    if "no transcript" in t:
        return ("No captions on this video and no speech-to-text backend available — "
                "install faster-whisper (pip) or set ASR_BACKEND.")
    if "is not a valid url" in t or "unsupported url" in t:
        return "That doesn't look like a supported video URL."
    return (text or "something went wrong").strip()[:300]


def source_id(src):
    """A stable id for any source — a YouTube id, else a hash of the path/URL."""
    if os.path.exists(os.path.expanduser(src)):
        return "f" + hashlib.md5(os.path.abspath(os.path.expanduser(src)).encode()).hexdigest()[:11]
    try:
        return yt_id(src)
    except ValueError:
        return "u" + hashlib.md5(src.encode()).hexdigest()[:11]


def valid_source(src):
    """A local file, any URL, or a YouTube id/link."""
    if not src:
        return False
    if os.path.exists(os.path.expanduser(src)) or "://" in src:
        return True
    try:
        yt_id(src)
        return True
    except ValueError:
        return False


def _yt_target(src):
    """Resolve a source to what yt-dlp should fetch; None for a local file."""
    p = os.path.expanduser(src)
    if os.path.exists(p):
        return None
    try:
        return f"https://www.youtube.com/watch?v={yt_id(src)}"
    except ValueError:
        return src  # any other yt-dlp-supported URL (Vimeo, direct mp4, …)


def download(src, outdir, maxres=720):
    """Get a playable video for `src` — a YouTube URL/id, any yt-dlp URL, or a
    LOCAL FILE PATH (returned as-is; ffmpeg reads it directly)."""
    local = os.path.expanduser(src)
    if os.path.exists(local):
        return local
    os.makedirs(outdir, exist_ok=True)
    out = os.path.join(outdir, f"{source_id(src)}.mp4")
    if not os.path.exists(out):
        sh(["yt-dlp", *_ytdlp_opts(), "-S", f"res:{maxres},ext:mp4:m4a",
            "--recode-video", "mp4", "-o", out, _yt_target(src)])
    return out


def probe_dur(path):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", path], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def meta(src):
    """Title + duration for any source (local file, YouTube, or other URL)."""
    local = os.path.expanduser(src)
    if os.path.exists(local):
        return {"title": os.path.splitext(os.path.basename(local))[0],
                "duration": probe_dur(local), "uploader": "", "id": source_id(src),
                "language": ""}
    target = _yt_target(src)
    r = subprocess.run(
        ["yt-dlp", *_ytdlp_opts(), "--skip-download", "--dump-json", target],
        capture_output=True, text=True)
    try:
        d = json.loads(r.stdout)
        return {"title": d.get("title", source_id(src)),
                "duration": d.get("duration", 0),
                "uploader": d.get("uploader", ""), "id": d.get("id", source_id(src)),
                "language": _norm_lang(d.get("language"))}
    except json.JSONDecodeError:
        return {"title": source_id(src), "duration": 0, "uploader": "",
                "id": source_id(src), "language": ""}


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


def _extract_wav(video, workdir, seconds=None, offset=0):
    """16kHz mono wav. seconds>0 extracts only a slice (for cheap language detection),
    optionally starting at `offset` seconds, into its own file so it never clobbers the
    full-audio cache."""
    if seconds:
        wav = os.path.join(workdir, f"audio_{int(offset)}_{int(seconds)}s.wav")
        if not os.path.exists(wav):
            sh(["ffmpeg", "-y", "-v", "error", "-ss", str(int(offset)),
                "-t", str(int(seconds)), "-i", video,
                "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", wav])
        return wav
    wav = os.path.join(workdir, "audio.wav")
    if not os.path.exists(wav):
        sh(["ffmpeg", "-y", "-v", "error", "-i", video,
            "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", wav])
    return wav


_FW_MODELS = {}  # model name -> loaded WhisperModel (warm across jobs in a process)


def _fw_model(model):
    m = _FW_MODELS.get(model)
    if m is None:
        from faster_whisper import WhisperModel
        threads = int(os.environ.get("ASR_THREADS", "0"))
        m = WhisperModel(model, device="cpu", compute_type="int8", cpu_threads=threads)
        _FW_MODELS[model] = m
    return m


def transcribe_fw(video, workdir, model="base.en", language=None):
    """Transcribe with faster-whisper (CTranslate2, int8 CPU). We decode the 16kHz
    mono wav to a numpy array ourselves so faster-whisper never touches PyAV (whose
    version often clashes). The model is loaded once per process and reused.
    `language` (e.g. 'fr') hints a multilingual model; None lets it auto-detect.
    Returns (segments, detected_language) — detected_language is faster-whisper's
    own guess (empty with an English-only model)."""
    import wave as _wave
    import numpy as np
    wav = _extract_wav(video, workdir)
    wf = _wave.open(wav)
    audio = (np.frombuffer(wf.readframes(wf.getnframes()), np.int16)
             .astype(np.float32) / 32768.0)
    segs, info = _fw_model(model).transcribe(audio, beam_size=1, language=language)
    out = [{"text": s.text.strip(), "start": float(s.start), "end": float(s.end)}
           for s in segs]
    return out, _norm_lang(getattr(info, "language", "") or "")


def detect_language(video, workdir, seconds=None):
    """Best-effort source-language detection from a leading audio slice, using a
    multilingual faster-whisper model. Returns a base code ('fr') or '' on failure.
    This is the only reliable signal: yt-dlp rarely exposes `language`, and YouTube
    auto-generates English captions for nearly everything, so a caption probe would
    wrongly report English for a foreign video."""
    seconds = seconds or int(os.environ.get("DETECT_LANG_SECONDS", "45"))
    try:
        import wave as _wave
        import numpy as np
        # Sample from ~30% in, not the start: intros are often music / English
        # branding / call-outs and mislead detection (e.g. "Oh Fonsi" in a Spanish song).
        dur = probe_dur(video)
        offset = max(0, min(dur * 0.3, max(0, dur - seconds)))
        wav = _extract_wav(video, workdir, seconds=seconds, offset=offset)
        wf = _wave.open(wav)
        audio = (np.frombuffer(wf.readframes(wf.getnframes()), np.int16)
                 .astype(np.float32) / 32768.0)
        _segs, info = _fw_model(_ml_model()).transcribe(audio, beam_size=1)
        return _norm_lang(getattr(info, "language", "") or "")
    except Exception as e:
        print(f"[lang] detect failed: {e}")
        return ""


def transcribe(video, workdir, model="small.en"):
    """Extract 16kHz mono audio and run whisper-cli; return normalized segments
    [{text,start,end}] (start/end in seconds)."""
    wav = _extract_wav(video, workdir)
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


_VTT_TC = re.compile(
    r"(\d\d):(\d\d):(\d\d)[.,](\d\d\d)\s*-->\s*(\d\d):(\d\d):(\d\d)[.,](\d\d\d)")


def _parse_vtt(path):
    """Parse a WebVTT subtitle file into [{text,start,end}] (seconds), collapsing
    the rolling duplicates that YouTube auto-captions emit."""
    def secs(h_, m_, s_, ms_):
        return int(h_) * 3600 + int(m_) * 60 + int(s_) + int(ms_) / 1000.0
    segs = []
    with open(path, encoding="utf-8", errors="ignore") as f:
        raw = f.read()
    for block in raw.split("\n\n"):
        m = _VTT_TC.search(block)
        if not m:
            continue
        st, en = secs(*m.group(1, 2, 3, 4)), secs(*m.group(5, 6, 7, 8))
        lines = [ln for ln in block.splitlines()
                 if "-->" not in ln and ln.strip() and not ln.strip().isdigit()
                 and not ln.startswith("WEBVTT")]
        txt = re.sub(r"<[^>]+>", "", html.unescape(" ".join(lines))).strip()
        txt = re.sub(r"\s+", " ", txt)
        if txt:
            segs.append({"text": txt, "start": st, "end": en})
    out = []
    for s in segs:
        if out and (out[-1]["text"] == s["text"] or s["text"].startswith(out[-1]["text"])):
            out[-1] = {"text": s["text"], "start": out[-1]["start"], "end": s["end"]}
        else:
            out.append(s)
    return out


_EN = "en.*,en,en-US,en-GB,en-orig"


def _norm_lang(code):
    """Normalize a yt-dlp language tag ('en-US', 'fr-FR') to a base code ('en', 'fr')."""
    if not code:
        return ""
    return str(code).split("-")[0].split("_")[0].strip().lower()


def _caption_langs(src_lang):
    """Build a yt-dlp --sub-langs preference string, SOURCE LANGUAGE FIRST then
    English. A non-English track is requested ahead of English so it isn't missed
    (English auto-captions can silently shadow the real source track)."""
    base = _norm_lang(src_lang)
    if not base or base == "en":
        return _EN
    return f"{base}.*,{base},{_EN}"


def _ml_model():
    """Multilingual ASR model for non-English audio (ASR_MODEL is English-only)."""
    return os.environ.get("ASR_MODEL_ML", "base")


_LANG_NAMES = {
    "en": "English", "es": "Spanish", "fr": "French", "de": "German",
    "it": "Italian", "pt": "Portuguese", "ro": "Romanian", "ru": "Russian",
    "nl": "Dutch", "pl": "Polish", "tr": "Turkish", "ar": "Arabic",
    "hi": "Hindi", "ja": "Japanese", "ko": "Korean", "zh": "Chinese",
    "uk": "Ukrainian", "sv": "Swedish", "cs": "Czech", "el": "Greek",
}


def lang_name(code):
    """Human-readable name for a base language code; 'Original' if unknown/empty."""
    return _LANG_NAMES.get(_norm_lang(code), "Original" if code else "English")


def _vtt_lang(fname):
    """Base language code of a yt-dlp subtitle filename '<id>.<lang>.vtt'."""
    parts = fname.rsplit(".", 2)          # [..., lang, "vtt"]
    lang = parts[-2] if len(parts) >= 2 else ""
    return _norm_lang(lang.replace("-orig", ""))


def captions(url, outdir, sub_langs=_EN):
    """Fetch YouTube subtitles (manual first, then auto) via yt-dlp — no whisper,
    no audio decode. Returns (segments, lang) — lang is the base language code of the
    track actually fetched (so callers know the real source language), or ([], "")
    for local files / non-YouTube / no-captions (which fall through to speech-to-text)."""
    try:
        vid = yt_id(url)
    except ValueError:
        return [], ""
    subprocess.run(
        ["yt-dlp", *_ytdlp_opts(), "--write-subs", "--write-auto-subs",
         "--sub-langs", sub_langs, "--skip-download", "--sub-format", "vtt",
         "-o", os.path.join(outdir, "%(id)s.%(ext)s"),
         f"https://www.youtube.com/watch?v={vid}"],
        capture_output=True, text=True)
    cands = [f for f in os.listdir(outdir)
             if f.startswith(vid + ".") and f.endswith(".vtt")]
    if not cands:
        return [], ""
    # prefer a manual track (no ".auto" / "-auto" marker) and a shorter lang tag
    cands.sort(key=lambda f: ("auto" in f.lower(), len(f)))
    chosen = cands[0]
    return _parse_vtt(os.path.join(outdir, chosen)), _vtt_lang(chosen)


def _asr(video, workdir, src_lang=None):
    """Run the configured speech-to-text backend. Returns (segments, source, lang) or
    None. ASR_BACKEND: faster-whisper (default) | whisper-cli.
    Model choice: an English hint -> ASR_MODEL (English-only, fast). Anything else
    (a non-English hint OR no hint at all) -> a multilingual model (ASR_MODEL_ML) that
    AUTO-DETECTS the language, which it then reports back. The captions fast-path means
    ASR is usually the fallback for caption-less videos, which skew non-English, so
    defaulting the fallback to multilingual is the right trade."""
    base = _norm_lang(src_lang)
    english = base == "en"
    backend = os.environ.get("ASR_BACKEND", "faster-whisper")
    if backend == "faster-whisper":
        try:
            model = os.environ.get("ASR_MODEL", "base.en") if english else _ml_model()
            segs, detected = transcribe_fw(video, workdir, model, language=base or None)
            return segs, f"faster-whisper:{model}", (base or detected or "en")
        except Exception as e:
            print(f"[asr] faster-whisper failed: {e}")
    if backend == "whisper-cli" or shutil.which("whisper-cli"):
        try:
            model = os.environ.get("WHISPER_MODEL", "small.en") if english else _ml_model()
            return transcribe(video, workdir, model), "whisper-cli", (base or "en")
        except Exception as e:
            print(f"[asr] whisper-cli failed: {e}")
    return None


def transcribe_source(video, url, workdir, whisper_model="small.en", prefer="captions",
                      src_lang=None):
    """Get a transcript the cheapest way that works. Returns (segments, source, lang):
    `lang` is the resolved source-language code (the caption track actually fetched, or
    whisper's audio auto-detection). prefer='captions' tries subtitles first (free, no
    CPU), then falls back to real speech transcription (faster-whisper). prefer='asr'
    flips it. An explicit src_lang hint requests that caption track first; with no hint
    and DETECT_LANG on (default), the source language is detected from the audio first
    so the right caption track / ASR language is chosen (set DETECT_LANG=0 to skip)."""
    hint = _norm_lang(src_lang)
    if not hint and os.environ.get("DETECT_LANG", "1") != "0":
        t0 = time.time()
        hint = detect_language(video, workdir)
        print(f"[lang] detected {hint or '?'} in {time.time() - t0:.1f}s")
        src_lang = hint or src_lang

    def try_caps():
        try:
            return captions(url, workdir, sub_langs=_caption_langs(src_lang))
        except Exception:
            return [], ""
    if prefer == "captions":
        segs, clang = try_caps()
        if segs:
            return segs, "captions", (hint or clang or "en")
    got = _asr(video, workdir, src_lang=src_lang)
    if got:
        return got
    if prefer != "captions":
        segs, clang = try_caps()
        if segs:
            return segs, "captions", (hint or clang or "en")
    raise RuntimeError(
        "no transcript: no YouTube captions and no working speech-to-text backend "
        "(install faster-whisper or whisper-cli)")


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
