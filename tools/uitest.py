"""UI smoke test for the live app: submit a URL, wait for the result, click
'Copy transcript', and verify the clipboard actually received the transcript.

Usage: python tools/uitest.py <base_url> [video_url]
Needs Playwright + a chromium build (reuse any venv that has them). Exits non-zero
on failure so it can gate CI or a pre-commit check.
"""
import sys

from playwright.sync_api import sync_playwright


def main():
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
    url = sys.argv[2] if len(sys.argv) > 2 else "https://www.youtube.com/watch?v=jNQXAC9IVRw"
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context()
        # the copy button uses the async clipboard API; grant it for this origin
        ctx.grant_permissions(["clipboard-read", "clipboard-write"], origin=base)
        pg = ctx.new_page()
        pg.goto(base, wait_until="networkidle")
        pg.fill("#url", url)
        pg.click("#go")
        pg.wait_for_selector("#result", state="visible", timeout=180000)
        pg.wait_for_timeout(1500)
        pg.click("#copytx")
        pg.wait_for_timeout(800)
        label = pg.inner_text("#copytx")
        clip = pg.evaluate("navigator.clipboard.readText()") or ""
        b.close()
    ok = ("Copied" in label) and len(clip) > 0
    print(f"button={label!r}  clip_len={len(clip)}  first={clip[:70]!r}")
    print("UITEST OK" if ok else "UITEST FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
