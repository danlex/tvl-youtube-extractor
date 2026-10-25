"""Offline self-test: validates the pipeline helpers and the HTML renderer
without network, whisper, or the Claude API. Run from backend/:  python selftest.py
"""
from extractor import pipeline, render


def main():
    # id parsing
    assert pipeline.yt_id("https://youtu.be/dsBXYAwQieI?si=abc") == "dsBXYAwQieI"
    assert pipeline.yt_id("https://www.youtube.com/watch?v=dsBXYAwQieI") == "dsBXYAwQieI"
    assert pipeline.yt_id("dsBXYAwQieI") == "dsBXYAwQieI"
    assert pipeline.mmss(125) == "2:05"

    # sentence grouping
    segs = [
        {"text": "Hello world.", "start": 0.0, "end": 2.0},
        {"text": "This", "start": 2.0, "end": 2.6},
        {"text": "is next.", "start": 2.6, "end": 4.0},
    ]
    groups = pipeline.sentence_groups(segs)
    assert len(groups) == 2, groups
    assert groups[0][2] == "Hello world." and groups[1][2] == "This is next."

    # renderer
    story = {
        "title": "Test Video", "duration": 30,
        "acts": [{"key": "intro", "label": "Intro"}, {"key": "end", "label": "Close"}],
        "beats": [
            {"t": 0, "act": "intro", "title": "Opening", "summary": "first beat"},
            {"t": 15, "act": "end", "title": "Wrap", "summary": "second beat"},
        ],
    }
    tr = {
        "title": "Videoclip de test",
        "acts": [{"key": "intro", "label": "Intro"}, {"key": "end", "label": "Final"}],
        "beats": [{"title": "Deschidere", "summary": "primul moment"},
                  {"title": "Încheiere", "summary": "al doilea moment"}],
        "captions": [{"start": 0.0, "text": "Salut lume."}, {"start": 2.6, "text": "Urmează."}],
    }
    caps = [(0.0, "Hello world.", "Salut lume."), (2.6, "This is next.", "Urmează.")]
    html = render.render_html(
        story, tr, ["", ""], [(0, "data:image/jpeg;base64,AAAA")], caps,
        "https://youtu.be/test", lang="Română")
    for needle in ("<!doctype html>", "Story timeline", "Test Video",
                   "primul moment", "Salut lume.", "Deschidere"):
        assert needle in html, f"missing: {needle}"

    print("selftest OK — pipeline + render")


if __name__ == "__main__":
    main()
