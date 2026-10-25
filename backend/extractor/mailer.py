"""Tiny email sender (Resend REST API via stdlib). No-op (logs) without a key."""
import json
import os
import urllib.request

RESEND_API_KEY = os.environ.get("RESEND_API_KEY")
MAIL_FROM = os.environ.get("MAIL_FROM", "TVL Academy <onboarding@resend.dev>")


def send(to, subject, html):
    if not RESEND_API_KEY:
        print(f"[mail] no RESEND_API_KEY — would email {to}: {subject}")
        return False
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=json.dumps({"from": MAIL_FROM, "to": [to],
                         "subject": subject, "html": html}).encode(),
        headers={"Authorization": f"Bearer {RESEND_API_KEY}",
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status in (200, 201)
    except Exception as e:
        print(f"[mail] send failed: {e}")
        return False


def ready_email(title, link):
    return (subj := f"Your video page is ready — {title}"), f"""
<div style="font-family:-apple-system,Segoe UI,Arial,sans-serif;max-width:520px;margin:0 auto;color:#16130f">
  <h2 style="font-size:22px;margin:0 0 6px">Your page is ready.</h2>
  <p style="color:#6b6560;margin:0 0 20px">We turned <b>{title}</b> into a story-timeline page —
     frames, a clip per beat, and a bilingual transcript.</p>
  <a href="{link}" style="display:inline-block;background:#ff4931;color:#fff;font-weight:700;
     text-decoration:none;padding:13px 24px;border-radius:10px">Open your page →</a>
  <p style="color:#9a9088;font-size:13px;margin:22px 0 0">{link}</p>
  <p style="color:#9a9088;font-size:12px;margin:26px 0 0">TVL Academy · YouTube Extractor</p>
</div>"""
