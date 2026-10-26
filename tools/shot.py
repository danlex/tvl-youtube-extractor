"""Dev helper: screenshot a local HTML file (or URL) with headless Chromium.

Usage:
    python tools/shot.py <file-or-url> <out.png> [width] [--viewport]
Needs Playwright + a chromium build (reuse any venv that has them).
"""
import os
import sys

from playwright.sync_api import sync_playwright


def main():
    src = sys.argv[1]
    out = sys.argv[2]
    width = int(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3].isdigit() else 1280
    sel = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--sel=")), None)
    submit = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--submit=")), None)
    waitsel = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--wait=")), "#story .beat")
    full = "--viewport" not in sys.argv and not sel
    url = src if "://" in src else "file://" + os.path.abspath(src)
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": width, "height": 860}, device_scale_factor=2)
        pg.goto(url, wait_until="networkidle")
        pg.wait_for_timeout(400)
        if submit:
            pg.fill("#url", submit)
            pg.click("#go")
            try:
                pg.wait_for_selector(waitsel, timeout=180000)
            except Exception:
                pass
            pg.wait_for_timeout(900)
            pg.screenshot(path=out, full_page=full)
            b.close()
            print(out)
            return
        # scroll through so IntersectionObserver reveal animations fire
        h = pg.evaluate("document.body.scrollHeight")
        y = 0
        while y < h:
            pg.evaluate(f"window.scrollTo(0,{y})")
            pg.wait_for_timeout(90)
            y += 600
        if sel:
            pg.eval_on_selector(sel, "e => e.scrollIntoView({block:'center'})")
            pg.wait_for_timeout(400)
        else:
            pg.evaluate("window.scrollTo(0,0)")
            pg.wait_for_timeout(350)
        pg.screenshot(path=out, full_page=full)
        b.close()
    print(out)


if __name__ == "__main__":
    main()
