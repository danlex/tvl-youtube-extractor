# TVL YouTube Extractor

Turn any YouTube video into a **story-timeline summary**: a Claude agent watches the
whole transcript, maps the narrative into acts and beats, and the pipeline pulls
every frame, a short looping clip per beat, and the full transcript with a
translation. Runs **entirely locally** as a single app.

- **Frontend** — Next.js (static export), served by the backend.
- **Backend** — FastAPI. Background worker runs the media pipeline; a **Claude
  agent** writes the story and the translation. By default it uses your logged-in
  `claude` CLI session (**no API key needed**); set `ANTHROPIC_API_KEY` to use the
  Anthropic SDK directly instead.
- **Output** — an interactive page in the browser, plus a downloadable
  self-contained `summary.html` (all frames + clips embedded as data URIs). See
  `examples/riemann-hypothesis-ai.html` for a finished sample.

**Links:** [live site](https://danlex.github.io/tvl-youtube-extractor/) ·
[install guide](https://danlex.github.io/tvl-youtube-extractor/install.html) ·
[sample output](https://danlex.github.io/tvl-youtube-extractor/examples/riemann-hypothesis-ai.html)

## Quick start

```bash
# A) use it inside Claude Code — installs /tvl-extract + the skill
curl -fsSL https://raw.githubusercontent.com/danlex/tvl-youtube-extractor/main/install.sh | bash

# B) run the full app locally
git clone https://github.com/danlex/tvl-youtube-extractor.git
cd tvl-youtube-extractor && ./run.sh      # → http://localhost:8000
```

**No API key needed** — the agent runs through your logged-in Claude Code session.
You just need `yt-dlp` + `ffmpeg` (`brew install yt-dlp ffmpeg`) and Claude Code
installed and logged in. Full details in the
[install guide](https://danlex.github.io/tvl-youtube-extractor/install.html).

## Using it

Every method takes one input — a YouTube link — and returns a page with the story,
frames, clips, and a bilingual transcript.

- **In Claude Code (easiest):** `/tvl-extract https://youtu.be/… Romanian` — or just
  say *“summarize this YouTube video: <link>”* and the skill runs it.
- **In your browser:** `./run.sh` → open `http://localhost:8000`, paste a link, pick a
  language, click **Extract**, watch progress, then view/download the page.
- **From the terminal:** `./extract.sh "https://youtu.be/…" --lang Romanian --open` —
  prints one self-contained `summary.html` and opens it.

Change the language with the second argument (`French`, `Spanish`, `German`, …); the
English transcript is always kept alongside the translation.

## How it works

```
YouTube URL
   │  yt-dlp            download the video
   │  ffmpeg            frames every 5s + one clip per beat
   │  transcript        YouTube captions → else faster-whisper (CPU, int8)
   │  Claude agent  ──▶ build_story  (acts + beats, English)
   │  Claude agent  ──▶ translate    (story + captions → target language)
   ▼
story-timeline UI  +  self-contained summary.html
```

## Prerequisites

System binaries on your `PATH`:

- [`yt-dlp`](https://github.com/yt-dlp/yt-dlp), `ffmpeg` + `ffprobe`
- **Claude Code** (`claude` CLI), logged in — the agent uses your session, so no
  API key is required. (Alternatively, set `ANTHROPIC_API_KEY`.)
- Python 3.10+. Node 18+ only if you want to build the web UI (the CLI and the
  `/tvl-extract` command don't need it).

macOS: `brew install yt-dlp ffmpeg`

**Transcription** needs no setup: the pipeline uses the video's **YouTube captions**
when present, and falls back to **faster-whisper** (installed via `pip`, runs int8 on
CPU — light enough for a 1-vCPU box) when there are none. `whisper-cli` is an optional
third option. Control it with `TRANSCRIBE_PREFER` (`captions`|`asr`), `ASR_BACKEND`
(`faster-whisper`|`whisper-cli`), and `ASR_MODEL` (e.g. `tiny.en`, `base.en`).

> **Self-hosting on a server?** YouTube blocks most **datacenter IPs** with a
> bot-check, so `yt-dlp` downloads fail from typical cloud VMs. Run it locally, or
> pass cookies / a proxy to `yt-dlp` (`--cookies`, `--proxy`) on a server.

## Setup

No key needed if you're logged into Claude Code:

```bash
./run.sh            # builds the UI, installs deps, serves everything
# open http://localhost:8000
```

To use the Anthropic API instead of your session, `cp backend/.env.example
backend/.env` and set `ANTHROPIC_API_KEY`.

`run.sh` builds the frontend once (delete `frontend/out` to rebuild), creates the
backend venv, installs deps, and serves the API **and** the UI at
`http://localhost:8000`.

## Headless CLI (no web server)

One-shot extraction straight to a self-contained `summary.html`:

```bash
./extract.sh "https://youtu.be/VIDEO_ID" --lang Romanian --open
# prints the summary.html path on stdout; --open opens it in the browser
```

Equivalent: `cd backend && python -m extractor.cli <url> --lang <language>`.
Outputs land in `backend/jobs/<id>/` (video, frames, clips, transcript, result.json,
summary.html).

## Claude Code integration

This repo ships a slash command and a skill (in `.claude/`). Install both with **one line**:

```bash
curl -fsSL https://raw.githubusercontent.com/danlex/tvl-youtube-extractor/main/install.sh | bash
```

It clones to `~/.tvl-youtube-extractor`, installs the skill, and wires up the command.
(Manual: `cp .claude/commands/tvl-extract.md ~/.claude/commands/` and
`cp -r .claude/skills/tvl-youtube-extractor ~/.claude/skills/`, then set the path in the command.)

- **`/tvl-extract <youtube-url> [language]`** — runs the headless extractor and
  reports the resulting `summary.html` (opens it too).
- **`tvl-youtube-extractor` skill** — lets Claude run the tool automatically when you
  ask it to "extract / summarize / transcribe a YouTube video". Documents the CLI, the
  web app, auth, and prerequisites.

Both use the logged-in `claude` session for the agent step, so no API key is required.

**Public how-to page:** https://danlex.github.io/tvl-youtube-extractor/
(source: [`docs/index.html`](docs/index.html), served via GitHub Pages).

## Development

```bash
./dev.sh     # FastAPI --reload on :8000, Next.js dev server on :3000
# open http://localhost:3000
```

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/extract` | `{url, lang}` → `{job_id}` |
| GET | `/api/jobs/{id}` | current status (`step`, `pct`, …) |
| GET | `/api/jobs/{id}/stream` | Server-Sent Events progress |
| GET | `/api/jobs/{id}/result` | the story JSON (acts, beats, captions, media URLs) |
| GET | `/api/jobs/{id}/frames` | frames produced so far (lets the UI show it building) |
| GET | `/api/jobs/{id}/summary.html` | the finished self-contained page |
| GET | `/api/health` | `{ok, auth, model}` |

The product landing (`backend/web/`, served at `/`) takes a URL, starts a job via
`/api/extract`, streams progress from `/api/jobs/{id}/stream`, shows frames appearing
from `/api/jobs/{id}/frames`, and embeds the finished page when it's done — all live,
no email.

## Configuration

Set in `backend/.env` (see `backend/.env.example`):

| Var | Default | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | optional — if set, uses the Anthropic SDK instead of the `claude` CLI session |
| `ANTHROPIC_MODEL` | session default | any Claude model id |
| `TRANSCRIBE_PREFER` | `captions` | `captions` (YouTube subs first) or `asr` |
| `ASR_BACKEND` | `faster-whisper` | or `whisper-cli` |
| `ASR_MODEL` | `base.en` | faster-whisper model (`tiny.en`, `base.en`, `small.en`, …) |

## Notes

- Transcription is CPU-bound; an 8-minute video takes a couple of minutes on a
  laptop. Longer videos take proportionally longer.
- Job outputs live under `backend/jobs/<id>/` and are gitignored.
- The agent never invents facts — the story and translation are grounded only in
  the transcript.
