"use client";

import { useRef, useState } from "react";
import {
  API_BASE,
  mediaUrl,
  startExtract,
  fetchResult,
  type JobState,
  type Result,
  type Beat,
} from "@/lib/api";

const LANGS = ["Romanian", "English", "French", "Spanish", "German", "Italian"];

export default function Home() {
  const [url, setUrl] = useState("");
  const [lang, setLang] = useState("Romanian");
  const [job, setJob] = useState<JobState | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const esRef = useRef<EventSource | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!url.trim() || busy) return;
    setError(null);
    setResult(null);
    setJob(null);
    setBusy(true);
    try {
      const id = await startExtract(url.trim(), lang);
      const es = new EventSource(`${API_BASE}/api/jobs/${id}/stream`);
      esRef.current = es;
      es.onmessage = async (ev) => {
        const state: JobState = JSON.parse(ev.data);
        setJob(state);
        if (state.status === "done") {
          es.close();
          try {
            setResult(await fetchResult(id));
          } catch (err: any) {
            setError(err.message);
          }
          setBusy(false);
        } else if (state.status === "error") {
          es.close();
          setError(state.error || "extraction failed");
          setBusy(false);
        }
      };
      es.onerror = () => {
        es.close();
        setError("lost connection to the backend");
        setBusy(false);
      };
    } catch (err: any) {
      setError(err.message);
      setBusy(false);
    }
  }

  return (
    <main className="wrap">
      <section className="hero">
        <h1>
          TVL <span className="brand">YouTube Extractor</span>
        </h1>
        <p>
          Paste a YouTube link. A Claude agent watches the whole video, maps its
          story into a timeline, pulls every frame and a clip per beat, and writes
          the full transcript with a translation.
        </p>
        <form className="form" onSubmit={onSubmit}>
          <input
            type="text"
            placeholder="https://youtu.be/..."
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            disabled={busy}
          />
          <select value={lang} onChange={(e) => setLang(e.target.value)} disabled={busy}>
            {LANGS.map((l) => (
              <option key={l} value={l}>
                {l}
              </option>
            ))}
          </select>
          <button className="go" type="submit" disabled={busy}>
            {busy ? "Working…" : "Extract"}
          </button>
        </form>
        {error && <div className="err">{error}</div>}
      </section>

      {job && !result && (
        <section className="progress">
          <div className="bar">
            <span style={{ width: `${job.pct}%` }} />
          </div>
          <div className="step">
            <b>{job.pct}%</b> — {job.step}
            {job.title ? ` · ${job.title}` : ""}
          </div>
        </section>
      )}

      {result && <ResultView r={result} />}
    </main>
  );
}

function ResultView({ r }: { r: Result }) {
  const total =
    r.duration || (r.beats.length ? r.beats[r.beats.length - 1].t + 10 : 1);
  const colorByAct = Object.fromEntries(r.acts.map((a) => [a.key, a.color]));
  const labelByAct = Object.fromEntries(r.acts.map((a) => [a.key, a.label]));

  // overview bands from consecutive acts
  const seq: [string, number][] = [];
  for (const b of r.beats) {
    if (!seq.length || seq[seq.length - 1][0] !== b.act) seq.push([b.act, b.t]);
  }
  const bands = seq.map(([a, st], i) => {
    const en = i + 1 < seq.length ? seq[i + 1][1] : total;
    return { a, w: Math.max(0, ((en - st) / total) * 100) };
  });

  return (
    <section>
      <div className="head">
        <h2>{r.title}</h2>
        {r.title_t && <p className="ro">{r.title_t}</p>}
        <div className="src">
          Source: <a href={r.source}>{r.source}</a>
          {r.uploader ? ` · ${r.uploader}` : ""}
        </div>
      </div>

      <div className="toolbar">
        <a href={`${API_BASE}/api/jobs/${r.id}/summary.html`} download>
          ⬇ Download self-contained HTML
        </a>
      </div>

      <div className="stats">
        <div className="stat">
          <b>{fmt(total)}</b>runtime
        </div>
        <div className="stat">
          <b>{r.beats.length}</b>story beats
        </div>
        <div className="stat">
          <b>{r.captions.length}</b>caption lines
        </div>
        <div className="stat">
          <b>{r.gallery.length}</b>frames
        </div>
      </div>

      <h3 className="sec">Story timeline</h3>
      <div className="graph">
        <div className="track">
          {bands.map((b, i) => (
            <div
              key={i}
              className="band"
              style={{ flex: `0 0 ${b.w.toFixed(3)}%`, background: colorByAct[b.a] }}
            >
              {labelByAct[b.a]}
            </div>
          ))}
        </div>
        <div className="ticks">
          {r.beats.map((b, i) => (
            <a
              key={i}
              className="dot"
              href={`#b${i}`}
              title={`${b.mmss} — ${b.title}`}
              style={{ left: `${(b.t / total) * 100}%`, background: b.color }}
            >
              <span>{b.mmss}</span>
            </a>
          ))}
        </div>
      </div>

      <h3 className="sec">The story, beat by beat</h3>
      {r.beats.map((b, i) => (
        <BeatCard key={i} b={b} i={i} label={labelByAct[b.act] || b.act} lang={r.lang} />
      ))}

      <h3 className="sec">Frames</h3>
      <div className="gallery">
        {r.gallery.map((g, i) => (
          <figure key={i}>
            <img src={mediaUrl(g.url)} alt="" loading="lazy" />
            <figcaption>{g.mmss}</figcaption>
          </figure>
        ))}
      </div>

      <h3 className="sec">Full captions &amp; {r.lang} translation</h3>
      <div className="caps">
        <div className="cap hd">
          <div>Time</div>
          <div>English</div>
          <div>{r.lang}</div>
        </div>
        {r.captions.map((c, i) => (
          <div className="cap" key={i}>
            <div className="t">{c.mmss}</div>
            <div>{c.en}</div>
            <div className="rotext">{c.t}</div>
          </div>
        ))}
      </div>
    </section>
  );
}

function BeatCard({
  b,
  i,
  label,
  lang,
}: {
  b: Beat;
  i: number;
  label: string;
  lang: string;
}) {
  const vid = useRef<HTMLVideoElement | null>(null);
  return (
    <div className="beat" id={`b${i}`}>
      <div className="rail">
        <div className="node" style={{ background: b.color }} />
        <div className="time">{b.mmss}</div>
      </div>
      <div className="card" style={{ borderLeftColor: b.color }}>
        <span className="tag" style={{ background: b.color }}>
          {label}
        </span>
        <video
          ref={vid}
          className="media"
          src={mediaUrl(b.clip_url)}
          muted
          loop
          playsInline
          preload="metadata"
          onMouseEnter={() => vid.current?.play().catch(() => {})}
          onMouseLeave={() => vid.current?.pause()}
          onClick={() =>
            vid.current?.paused ? vid.current?.play() : vid.current?.pause()
          }
        />
        <h4>{b.title}</h4>
        {b.title_t && <p className="ro-title">{b.title_t}</p>}
        <p className="en">{b.summary}</p>
        {b.summary_t && (
          <p className="roc">
            <b>{lang}</b>
            {b.summary_t}
          </p>
        )}
        <div className="clear" />
      </div>
    </div>
  );
}

function fmt(s: number) {
  s = Math.floor(s);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}
