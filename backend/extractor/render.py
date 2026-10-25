"""Render a self-contained HTML story summary (all media embedded as data URIs).

This is the portable, shareable artifact the backend offers for download. The
live Next.js UI renders the same data interactively from the job JSON; this file
is the "save as one HTML" path.
"""
from .pipeline import mmss

PALETTE = ["#FF4931", "#0E9AA7", "#E0962B", "#2E9E5B", "#7A5AF8",
           "#5A6472", "#C0392B", "#2C7BE5"]

CSS = """
:root{--coral:#FF4931;--ink:#1c1b19;--cream:#F7F2E7;--card:#fffdf7;--muted:#6b6459;--line:#e7ddc8}
*{box-sizing:border-box}
body{margin:0;background:var(--cream);color:var(--ink);font:16px/1.55 -apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif}
.wrap{max-width:1020px;margin:0 auto;padding:32px 20px 80px}
.head h1{font-size:30px;line-height:1.15;margin:0 0 6px;letter-spacing:-.01em}
.head .src{color:var(--muted);font-size:14px}
.head .src a{color:var(--coral);text-decoration:none}
.stats{display:flex;flex-wrap:wrap;gap:10px;margin:18px 0 10px}
.stat{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:8px 14px;font-size:13px}
.stat b{display:block;font-size:19px}
h2{font-size:13px;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);margin:46px 0 14px}
.graph{position:relative;margin:10px 0 30px}
.track{position:relative;height:46px;border-radius:9px;overflow:hidden;display:flex;border:1px solid var(--line)}
.band{display:flex;align-items:center;justify-content:center;color:#fff;font-size:11px;font-weight:700;letter-spacing:.03em;text-align:center;padding:0 4px;overflow:hidden;white-space:nowrap}
.ticks{position:relative;height:30px;margin-top:4px}
.dot{position:absolute;top:0;transform:translateX(-50%);width:13px;height:13px;border-radius:50%;border:2px solid #fff;cursor:pointer;box-shadow:0 1px 3px rgba(0,0,0,.25)}
.dot span{position:absolute;top:16px;left:50%;transform:translateX(-50%);font-size:9px;color:var(--muted);white-space:nowrap}
.beat{display:grid;grid-template-columns:70px 1fr;position:relative}
.rail{position:relative}
.rail:before{content:'';position:absolute;left:14px;top:0;bottom:0;width:2px;background:var(--line)}
.beat:last-child .rail:before{bottom:auto;height:30px}
.node{position:absolute;left:7px;top:26px;width:16px;height:16px;border-radius:50%;border:3px solid var(--cream);z-index:2}
.time{position:absolute;left:34px;top:24px;font-size:12px;font-weight:700;color:var(--muted)}
.card{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--coral);border-radius:12px;padding:16px 18px;margin:0 0 22px}
.card .tag{font-size:10px;letter-spacing:.1em;text-transform:uppercase;font-weight:700;padding:3px 8px;border-radius:20px;color:#fff}
.card h3{margin:10px 0 2px;font-size:19px;line-height:1.25}
.card .ro-title{color:var(--muted);font-style:italic;font-size:15px;margin:0 0 10px}
.card .media{float:right;width:260px;max-width:44%;margin:0 0 10px 16px;border-radius:9px;border:1px solid var(--line);background:#0b0d12;display:block;aspect-ratio:16/9;object-fit:cover}
.card video.media{cursor:pointer}
.card .en{margin:0 0 10px}
.card .ro{margin:0;padding:10px 12px;background:#fdf6ec;border-left:3px solid var(--coral);border-radius:0 8px 8px 0;font-size:14.5px;color:#55402f}
.card .ro b{color:var(--coral);font-size:10px;letter-spacing:.1em;text-transform:uppercase;display:block;margin-bottom:3px}
.clear{clear:both}
.gallery{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px}
.gallery figure{margin:0;position:relative}
.gallery img{width:100%;border-radius:7px;border:1px solid var(--line);display:block}
.gallery figcaption{position:absolute;left:5px;bottom:5px;background:rgba(0,0,0,.6);color:#fff;font-size:10px;padding:1px 5px;border-radius:4px}
.caps{border:1px solid var(--line);border-radius:12px;overflow:hidden;background:var(--card)}
.cap{display:grid;grid-template-columns:62px 1fr 1fr;gap:14px;padding:11px 14px;border-top:1px solid var(--line);font-size:14px}
.cap:first-child{border-top:none}
.cap .t{color:var(--muted);font-size:12px;font-weight:700}
.cap .rotext{color:#55402f}
.caps .hd{background:#f1e7d2;font-size:11px;letter-spacing:.08em;text-transform:uppercase;font-weight:700;color:var(--muted)}
@media(max-width:720px){.card .media{float:none;width:100%;max-width:100%;margin:0 0 12px}.cap{grid-template-columns:1fr;gap:4px}.band{font-size:9px}}
"""

JS = """
<script>
(function(){
  var vids=[].slice.call(document.querySelectorAll('video[data-lazy]'));
  if(!('IntersectionObserver' in window)){vids.forEach(function(v){v.play().catch(function(){});});return;}
  var io=new IntersectionObserver(function(es){es.forEach(function(e){
    if(e.isIntersecting){e.target.play().catch(function(){});}else{e.target.pause();}});},{threshold:0.3});
  vids.forEach(function(v){io.observe(v);v.addEventListener('click',function(){v.paused?v.play():v.pause();});});
})();
</script>
"""


def _esc(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_html(story, tr, beat_clips, gallery, captions, source_url, lang="Română"):
    """beat_clips: list of data-URI strings aligned to story['beats'] (or '').
    gallery: list of (sec, data_uri). captions: list of (start, en, ro)."""
    acts = story["acts"]
    color = {a["key"]: PALETTE[i % len(PALETTE)] for i, a in enumerate(acts)}
    labelt = {a["key"]: t["label"] for a, t in zip(acts, tr.get("acts", acts))}
    beats = story["beats"]
    tbeats = tr.get("beats", [{} for _ in beats])
    total = story.get("duration") or (beats[-1]["t"] + 10 if beats else 1)

    # overview graph: act bands + beat dots
    seq = []
    for b in beats:
        if not seq or seq[-1][0] != b["act"]:
            seq.append([b["act"], b["t"]])
    bands = ""
    for i, (a, st) in enumerate(seq):
        en = seq[i + 1][1] if i + 1 < len(seq) else total
        w = max(0.0, (en - st) / total * 100)
        bands += (f'<div class="band" style="flex:0 0 {w:.3f}%;background:{color.get(a,"#999")}">'
                  f'{_esc(dict((x["key"],x["label"]) for x in acts).get(a,a))}</div>')
    dots = ""
    for i, b in enumerate(beats):
        left = b["t"] / total * 100
        dots += (f'<a class="dot" href="#b{i}" style="left:{left:.3f}%;background:{color.get(b["act"],"#999")}" '
                 f'title="{mmss(b["t"])} — {_esc(b["title"])}"><span>{mmss(b["t"])}</span></a>')
    graph = f'<div class="graph"><div class="track">{bands}</div><div class="ticks">{dots}</div></div>'

    labels = {a["key"]: a["label"] for a in acts}
    cards = ""
    for i, b in enumerate(beats):
        c = color.get(b["act"], "#999")
        clip = beat_clips[i] if i < len(beat_clips) else ""
        media = (f'<video class="media" src="{clip}" muted loop playsinline preload="metadata" data-lazy></video>'
                 if clip else "")
        t = tbeats[i] if i < len(tbeats) else {}
        ro_title = _esc(t.get("title", ""))
        ro_sum = _esc(t.get("summary", ""))
        ro_html = (f'<p class="ro"><b>{_esc(lang)}</b>{ro_sum}</p>' if ro_sum else "")
        cards += (
            f'<div class="beat" id="b{i}">'
            f'<div class="rail"><div class="node" style="background:{c}"></div>'
            f'<div class="time">{mmss(b["t"])}</div></div>'
            f'<div class="card" style="border-left-color:{c}">'
            f'<span class="tag" style="background:{c}">{_esc(labels.get(b["act"],b["act"]))}</span>'
            f'{media}<h3>{_esc(b["title"])}</h3>'
            f'<p class="ro-title">{ro_title}</p>'
            f'<p class="en">{_esc(b["summary"])}</p>{ro_html}<div class="clear"></div></div></div>')

    gal = "".join(
        f'<figure><img src="{uri}" alt=""><figcaption>{mmss(sec)}</figcaption></figure>'
        for sec, uri in gallery)

    caps = (f'<div class="cap hd"><div>Time</div><div>English</div><div>{_esc(lang)}</div></div>'
            + "".join(f'<div class="cap"><div class="t">{mmss(st)}</div>'
                      f'<div>{_esc(en)}</div><div class="rotext">{_esc(ro)}</div></div>'
                      for st, en, ro in captions))

    inner = (
        f'<style>{CSS}</style><div class="wrap">'
        f'<div class="head"><h1>{_esc(story["title"])}</h1>'
        f'<div class="src">Source: <a href="{_esc(source_url)}">{_esc(source_url)}</a></div></div>'
        f'<div class="stats">'
        f'<div class="stat"><b>{mmss(total)}</b>runtime</div>'
        f'<div class="stat"><b>{len(beats)}</b>story beats</div>'
        f'<div class="stat"><b>{len(captions)}</b>caption lines</div>'
        f'<div class="stat"><b>{len(gallery)}</b>frames</div></div>'
        f'<h2>Story timeline</h2>{graph}'
        f'<h2>The story, beat by beat</h2>{cards}'
        f'<h2>Frames</h2><div class="gallery">{gal}</div>'
        f'<h2>Full captions &amp; {_esc(lang)} translation</h2><div class="caps">{caps}</div>'
        f'</div>{JS}')

    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{_esc(story["title"])}</title></head><body>{inner}</body></html>')
