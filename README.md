# TVL YouTube Extractor

Turn any YouTube video into a **story-timeline summary**: a Claude agent watches the
whole transcript, maps the narrative into acts and beats, and the pipeline pulls
every frame, a short looping clip per beat, and the full transcript with a
translation. Runs **entirely locally** as a single app.

- **Frontend** — Next.js (static export), served by the backend.
- **Backend** — FastAPI. Background worker runs the media pipeline; a **Claude
  agent** (Anthropic SDK, structured outputs) writes the story and the translation.
- **Output** — an interactive page in the browser, plus a downloadable
  self-contained `summary.html` (all frames + clips embedded as data URIs). See
  `examples/riemann-hypothesis-ai.html` for a finished sample.

## How it works

```
YouTube URL
   │  yt-dlp            download the video
   │  ffmpeg            frames every 5s + one clip per beat
   │  whisper-cli       transcribe audio → timed sentences
   │  Claude agent  ──▶ build_story  (acts + beats, English)
   │  Claude agent  ──▶ translate    (story + captions → target language)
   ▼
story-timeline UI  +  self-contained summary.html
```

## Prerequisites

System binaries on your `PATH`:

- [`yt-dlp`](https://github.com/yt-dlp/yt-dlp), `ffmpeg` + `ffprobe`
- [`whisper-cli`](https://github.com/ggml-org/whisper.cpp) and a ggml model
  (default `small.en`) under `~/.cache/hyperframes/whisper/models/` (override with
  `WHISPER_MODELS` / `WHISPER_MODEL`)
- Python 3.10+, and Node 18+ (to build the UI)

macOS: `brew install yt-dlp ffmpeg whisper-cpp`

## Setup

```bash
cp backend/.env.example backend/.env    # add your ANTHROPIC_API_KEY
./run.sh                                 # builds UI, installs deps, serves everything
# open http://localhost:8000
```

`run.sh` builds the frontend once (delete `frontend/out` to rebuild), creates the
backend venv, installs deps, and serves the API **and** the UI at
`http://localhost:8000`.

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
| GET | `/api/jobs/{id}/summary.html` | download the self-contained HTML |
| GET | `/api/health` | `{ok, model}` |

## Configuration

Set in `backend/.env`:

| Var | Default | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | **required** |
| `ANTHROPIC_MODEL` | `claude-opus-4-8` | any Claude model id |
| `WHISPER_MODEL` | `small.en` | ggml model name or absolute path |
| `WHISPER_MODELS` | `~/.cache/hyperframes/whisper/models` | model directory |

## Notes

- Transcription is CPU-bound; an 8-minute video takes a couple of minutes on a
  laptop. Longer videos take proportionally longer.
- Job outputs live under `backend/jobs/<id>/` and are gitignored.
- The agent never invents facts — the story and translation are grounded only in
  the transcript.
