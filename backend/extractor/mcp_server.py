"""MCP server — exposes the extractor as a tool any local agent can call
(Claude Code/Desktop, Codex, Cursor, Cline, …) over stdio.

Run: python -m extractor.mcp_server   (or the `tvl-ytx-mcp` console script)
The LLM step uses your logged-in `claude` session by default (no API key); set
ANTHROPIC_API_KEY to use the Anthropic API instead.
"""
import os
import sys
import uuid

from . import orchestrate, pipeline

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    sys.stderr.write("The 'mcp' package is required: pip install mcp\n")
    raise

JOBS_DIR = os.path.expanduser(
    os.environ.get("TVLX_JOBS", "~/.tvl-youtube-extractor/jobs"))
os.makedirs(JOBS_DIR, exist_ok=True)

mcp = FastMCP("tvl-youtube-extractor")


@mcp.tool()
def extract_video(source: str, language: str = "English") -> dict:
    """Turn a video into a structured story summary with a browsable page.

    Works on a YouTube link, any yt-dlp-supported URL, or a LOCAL FILE PATH. It
    downloads/reads the video, transcribes it (YouTube captions when present, else
    local speech-to-text), and uses an LLM to map the narrative into acts and beats,
    translated into `language`. Runs locally — no server, no API key (uses the
    logged-in Claude session).

    Returns the title, the beats (timestamp + title + 2-4 sentence summary), and the
    absolute path to a self-contained `summary.html` you can open in a browser.

    Args:
        source: YouTube URL/id, another video URL, or a path to a local video file.
        language: Translation language for the summary (default English).
    """
    if not pipeline.valid_source(source):
        raise ValueError("source must be a video URL, YouTube id, or local file path")
    job = uuid.uuid4().hex[:12]
    outdir = os.path.join(JOBS_DIR, job)
    try:
        out = orchestrate.extract(job, source, language, outdir)
    except Exception as e:
        raise RuntimeError(pipeline.friendly_error(str(e)))
    r = out["result"]
    return {
        "title": r["title"],
        "title_translated": r.get("title_t", ""),
        "duration_seconds": round(r.get("duration", 0)),
        "language": language,
        "acts": [a["label"] for a in r["acts"]],
        "beats": [{"time": b["mmss"], "title": b["title"], "summary": b["summary"],
                   "summary_translated": b.get("summary_t", "")} for b in r["beats"]],
        "caption_lines": len(r["captions"]),
        "frame_count": len(r["gallery"]),
        "summary_html": out["html_path"],
        "result_json": out["result_path"],
    }


@mcp.tool()
def get_transcript(source: str) -> dict:
    """Just the transcript of a video (no story/LLM step) — fast.

    Works on a YouTube link, any yt-dlp URL, or a local file path. Returns timed
    sentences [{start, text}] from YouTube captions when available, else local
    speech-to-text (faster-whisper).

    Args:
        source: YouTube URL/id, another video URL, or a path to a local video file.
    """
    if not pipeline.valid_source(source):
        raise ValueError("source must be a video URL, YouTube id, or local file path")
    job = uuid.uuid4().hex[:12]
    outdir = os.path.join(JOBS_DIR, job)
    os.makedirs(outdir, exist_ok=True)
    video = pipeline.download(source, outdir)
    segs, src = pipeline.transcribe_source(video, source, outdir)
    groups = pipeline.sentence_groups(segs)
    return {"source_of_transcript": src,
            "lines": [{"start": round(s, 1), "text": t} for s, _d, t in groups]}


def main():
    mcp.run()


if __name__ == "__main__":
    main()
