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

    # source_id: YouTube -> video id; other URLs -> stable hashed id (needs hashlib)
    assert pipeline.source_id("https://youtu.be/dsBXYAwQieI") == "dsBXYAwQieI"
    sid = pipeline.source_id("https://vimeo.com/12345")
    assert sid.startswith("u") and len(sid) == 12, sid
    assert pipeline.source_id("https://vimeo.com/12345") == sid  # deterministic

    # source-language handling
    assert pipeline._norm_lang("en-US") == "en"
    assert pipeline._norm_lang("fr_FR") == "fr"
    assert pipeline._norm_lang(None) == ""
    assert pipeline._caption_langs(None) == pipeline._EN      # default English
    assert pipeline._caption_langs("en-GB") == pipeline._EN   # English stays English
    fr = pipeline._caption_langs("fr")
    assert fr.startswith("fr.*,fr,") and fr.endswith(pipeline._EN), fr  # source first

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
        "title": "Test Video", "duration": 30, "tldr": "A short test clip.",
        "acts": [{"key": "intro", "label": "Intro"}, {"key": "end", "label": "Close"}],
        "beats": [
            {"t": 0, "act": "intro", "title": "Opening", "summary": "first beat"},
            {"t": 15, "act": "end", "title": "Wrap", "summary": "second beat"},
        ],
    }
    tr = {
        "title": "Videoclip de test", "tldr": "Un scurt clip de test.",
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
                   "primul moment", "Salut lume.", "Deschidere",
                   "A short test clip.", "Un scurt clip de test."):
        assert needle in html, f"missing: {needle}"

    # markdown export (from a result.json-shaped dict)
    result = {
        "title": "Test Video", "tldr": "A short test clip.", "source": "https://youtu.be/test",
        "duration": 30, "lang": "Română",
        "beats": [{"mmss": "0:00", "title": "Opening", "summary": "first beat",
                   "summary_t": "primul moment"}],
        "captions": [{"mmss": "0:00", "en": "Hello world.", "t": "Salut lume."}],
    }
    md = render.render_markdown(result)
    for needle in ("# Test Video", "> A short test clip.", "### 0:00 — Opening",
                   "first beat", "*primul moment*", "**0:00** Hello world."):
        assert needle in md, f"missing in md: {needle}"

    print("selftest OK — pipeline + render + tldr + markdown")


if __name__ == "__main__":
    main()
