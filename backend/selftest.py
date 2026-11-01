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
    # the fetched caption track's filename reveals the real source language
    assert pipeline._vtt_lang("kLpH1nSLJSs.es.vtt") == "es"
    assert pipeline._vtt_lang("abc.en-US.vtt") == "en"
    assert pipeline._vtt_lang("abc.es-orig.vtt") == "es"
    # human-readable labels for the transcript column / markdown
    assert pipeline.lang_name("es") == "Spanish"
    assert pipeline.lang_name("en") == "English"
    assert pipeline.lang_name("") == "English"       # unknown source -> English default
    assert pipeline.lang_name("xx") == "Original"    # known-nonempty but unmapped

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
    caps = [(0.0, "Hola mundo.", "Salut lume."), (2.6, "Esto sigue.", "Urmează.")]
    html = render.render_html(
        story, tr, ["", ""], [(0, "data:image/jpeg;base64,AAAA")], caps,
        "https://youtu.be/test", lang="Română", src_label="Spanish")
    for needle in ("<!doctype html>", "Story timeline", "Test Video",
                   "primul moment", "Salut lume.", "Deschidere",
                   "A short test clip.", "Un scurt clip de test.",
                   "<div>Spanish</div>"):  # source column labeled, not hardcoded English
        assert needle in html, f"missing: {needle}"

    # markdown export (from a result.json-shaped dict), with a non-English source
    result = {
        "title": "Test Video", "tldr": "A short test clip.", "source": "https://youtu.be/test",
        "duration": 30, "lang": "Română", "src_lang": "es",
        "beats": [{"mmss": "0:00", "title": "Opening", "summary": "first beat",
                   "summary_t": "primul moment"}],
        "captions": [{"mmss": "0:00", "en": "Hola mundo.", "t": "Salut lume."}],
    }
    md = render.render_markdown(result)
    for needle in ("# Test Video", "> A short test clip.", "### 0:00 — Opening",
                   "first beat", "*primul moment*", "**0:00** Hola mundo.",
                   "**Spanish → Română**"):
        assert needle in md, f"missing in md: {needle}"

    print("selftest OK — pipeline + render + tldr + markdown + src-lang")


if __name__ == "__main__":
    main()
