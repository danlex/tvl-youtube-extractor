---
name: tvl-youtube-extractor
description: Extract a YouTube (or local) video into a self-contained story-timeline HTML — a narrative-arc graph, per-beat video clips, every frame, and the full transcript with a translation. Use when the user asks to "extract / summarize / break down a YouTube video", "turn this video into a page/report", "get the transcript + translation", "make a story timeline of this video", or runs /tvl-extract. Backed by the standalone tvl-youtube-extractor app (FastAPI + Next.js) whose Claude agent authenticates off the logged-in claude session (no API key).
---

# TVL YouTube Extractor

Turns a video URL into a **story-timeline summary**: a Claude agent reads the whole
transcript, segments it into narrative acts + beats, and the pipeline pulls every
frame, one short looping clip per beat, and the full transcript with a translation.
Output is an interactive page plus a portable self-contained `summary.html` (all
media embedded as data URIs).

Repo: `/Users/adan/work/claude/code/tvl-youtube-extractor` (`danlex/tvl-youtube-extractor`).

## Two ways to run

### 1. Headless CLI (best for one-off extraction / the /tvl-extract command)
```
./extract.sh "<youtube-url>" --lang Romanian [--open]
```
- Prints the generated `summary.html` path on **stdout** (progress on stderr).
- Writes everything to `backend/jobs/<id>/` (video, frames/, clips/, transcript.json,
  result.json, summary.html).
- Equivalent: `cd backend && python -m extractor.cli <url> --lang <lang>`.

### 2. Web app (interactive, reusable)
```
./run.sh     # builds the UI + serves API and UI at http://localhost:8000
./dev.sh     # dev mode: FastAPI :8000 + Next.js :3000
```
Paste a URL, pick a language, watch live SSE progress, browse the timeline, download
the HTML. API: `POST /api/extract`, `GET /api/jobs/{id}` + `/stream` (SSE) + `/result`
+ `/summary.html`, `GET /api/health`.

## How it works
```
URL → yt-dlp (download) → ffmpeg (frames every 5s + a clip per beat)
    → whisper-cli (transcribe → timed sentences)
    → Claude agent: build_story (acts + beats)  →  translate (story + captions)
    → render self-contained summary.html
```

## Auth (important)
The agent uses the **logged-in `claude` CLI session** by default — **no API key**.
It shells out to `claude -p --output-format json --tools ""` (tools disabled so the
text→JSON transform doesn't hit the turn limit). Set `ANTHROPIC_API_KEY` to use the
Anthropic SDK (structured outputs) instead. Override the model with `ANTHROPIC_MODEL`.

## Prerequisites
`yt-dlp`, `ffmpeg` + `ffprobe`, `whisper-cli` + a ggml model (default `small.en` under
`~/.cache/hyperframes/whisper/models/`), Python 3.10+, Node 18+ (only for the web UI),
and Claude Code logged in (for session auth). macOS: `brew install yt-dlp ffmpeg whisper-cpp`.

## Tips & gotchas
- `--tools ""` on the `claude` CLI call is REQUIRED — without it the agent attempts a
  tool call and dies with `error_max_turns`. It's in `extractor/agent.py`.
- Transcription is CPU-bound: ~a couple minutes for an 8-min video.
- Cost: each agent call re-sends Claude Code's system prompt (~$0.1-0.25/call, two per video).
- Job outputs under `backend/jobs/` are gitignored. `backend/selftest.py` is an offline
  pipeline+render check. `examples/riemann-hypothesis-ai.html` is a finished sample.
- Extend capabilities in `extractor/` (pipeline, agent, render, orchestrate) and keep
  this skill + the `/tvl-extract` command in sync.
