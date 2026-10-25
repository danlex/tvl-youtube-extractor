---
description: Extract a YouTube video into a story-timeline HTML summary (frames, per-beat clips, bilingual transcript) using the TVL YouTube Extractor
argument-hint: <youtube-url> [language]
allowed-tools: Bash(/Users/adan/work/claude/code/tvl-youtube-extractor/extract.sh:*), Read
---

Run the TVL YouTube Extractor on: **$ARGUMENTS**

Do this:

1. Parse the arguments. The first whitespace-separated token is the **YouTube URL**
   (required — a full link or an 11-char id). An optional second token is the
   **translation language** (default `Romanian`). If no URL is present, ask for one
   and stop.

2. Run the extractor headlessly (it downloads the video, pulls frames + a clip per
   beat, transcribes with whisper, and uses the Claude agent to map the story and
   translate it — authenticating off the logged-in `claude` session, no API key):

   ```
   /Users/adan/work/claude/code/tvl-youtube-extractor/extract.sh "<URL>" --lang "<LANGUAGE>" --open
   ```

   Progress prints on stderr; the final line on **stdout is the path to the
   generated `summary.html`**. `--open` opens it in the browser.

3. Report back: the `summary.html` path, and a 2-3 line description of what the
   video is about (read the sibling `result.json` in the same job folder for the
   title and beats if you want specifics). Keep it short.

Notes:
- First run per machine sets up a Python venv and installs deps (slower once).
- Each run costs ~$0.1-0.25 per Claude call (two per video) against the session.
- Requires `yt-dlp`, `ffmpeg`, `whisper-cli` (+ a ggml model) on PATH.
