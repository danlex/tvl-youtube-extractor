// In production the UI is served by FastAPI at the same origin, so API_BASE is "".
// In dev (next dev on :3000), set NEXT_PUBLIC_API_BASE=http://localhost:8000.
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "";

export const mediaUrl = (u: string) =>
  u.startsWith("http") ? u : API_BASE + u;

export type Act = { key: string; label: string; label_t: string; color: string };
export type Beat = {
  t: number; mmss: string; act: string; color: string;
  title: string; title_t: string; summary: string; summary_t: string;
  clip_url: string;
};
export type Caption = { start: number; mmss: string; en: string; t: string };
export type GalleryItem = { sec: number; mmss: string; url: string };
export type Result = {
  id: string; title: string; title_t: string; source: string;
  uploader: string; duration: number; lang: string;
  acts: Act[]; beats: Beat[]; gallery: GalleryItem[]; captions: Caption[];
};
export type JobState = {
  id: string; status: "running" | "done" | "error";
  step: string; pct: number; error: string | null; title: string;
};

export async function startExtract(url: string, lang: string): Promise<string> {
  const r = await fetch(`${API_BASE}/api/extract`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ url, lang }),
  });
  if (!r.ok) throw new Error((await r.json()).detail || "request failed");
  return (await r.json()).job_id;
}

export async function fetchResult(id: string): Promise<Result> {
  const r = await fetch(`${API_BASE}/api/jobs/${id}/result`);
  if (!r.ok) throw new Error("result not ready");
  return r.json();
}
