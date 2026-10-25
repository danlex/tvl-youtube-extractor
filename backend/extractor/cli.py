"""Headless one-shot extraction — no web server needed.

Usage (from backend/, with the venv active):
    python -m extractor.cli <youtube-url> [--lang Romanian] [--open]

Writes everything under backend/jobs/<id>/ and prints the summary.html path.
Auth: uses your logged-in `claude` CLI session unless ANTHROPIC_API_KEY is set.
"""
import argparse
import os
import sys
import uuid

from . import orchestrate

JOBS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "jobs")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="tvl-extract",
                                 description="YouTube video -> story-timeline HTML summary")
    ap.add_argument("url", help="YouTube URL or 11-char video id")
    ap.add_argument("--lang", default="Romanian", help="translation language (default: Romanian)")
    ap.add_argument("--open", action="store_true", help="open the result in your browser")
    ap.add_argument("--json", action="store_true", help="print the result.json path too")
    a = ap.parse_args(argv)

    job_id = uuid.uuid4().hex[:12]
    outdir = os.path.join(JOBS_DIR, job_id)

    def prog(**k):
        if "pct" in k:
            print(f"  [{k['pct']:>3}%] {k.get('step','')}", file=sys.stderr, flush=True)
        elif "title" in k:
            print(f"        title: {k['title']}", file=sys.stderr, flush=True)

    try:
        out = orchestrate.extract(job_id, a.url, a.lang, outdir, progress=prog)
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    print(out["html_path"])  # stdout = the one thing a caller wants
    if a.json:
        print(out["result_path"])
    if a.open:
        import webbrowser
        webbrowser.open("file://" + out["html_path"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
