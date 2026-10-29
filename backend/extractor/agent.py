"""The Claude agent: turns a raw transcript into a structured story.

Two jobs — build_story (segment the narrative) and translate (story + captions).

Auth: by default the agent shells out to the `claude` CLI in headless mode
(`claude -p --output-format json`), which uses your logged-in Claude session — no
API key required. If ANTHROPIC_API_KEY is set, it uses the Anthropic SDK instead
(structured outputs). Override the model with ANTHROPIC_MODEL.
"""
import json
import os
import re
import subprocess

MODEL = os.environ.get("ANTHROPIC_MODEL")          # None => session/CLI default
USE_SDK = bool(os.environ.get("ANTHROPIC_API_KEY"))
CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "claude")


# ----------------------------------------------------------------- JSON helpers
def _extract_json(text):
    t = (text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\n?", "", t)
        t = re.sub(r"\n?```$", "", t).strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        i, j = t.find("{"), t.rfind("}")
        if i >= 0 and j > i:
            return json.loads(t[i:j + 1])
        raise


# ----------------------------------------------------------------- CLI backend
def _run_cli(system, user, cwd=None):
    # No tools: these are pure text->JSON transforms. Without this the model may
    # attempt a tool call and hit the turn limit (error_max_turns).
    cmd = [CLAUDE_BIN, "-p", "--output-format", "json",
           "--append-system-prompt", system, "--tools", "", "--max-turns", "2"]
    if MODEL:
        cmd += ["--model", MODEL]
    r = subprocess.run(cmd, input=user, capture_output=True, text=True, cwd=cwd)
    if r.returncode != 0:
        raise RuntimeError(f"claude CLI failed: {(r.stderr or r.stdout).strip()[:500]}")
    env = json.loads(r.stdout)
    if env.get("is_error"):
        raise RuntimeError(f"claude error: {str(env.get('result',''))[:300]}")
    return _extract_json(env["result"])


# ----------------------------------------------------------------- SDK backend
def _run_sdk(system, user, schema):
    import anthropic
    client = anthropic.Anthropic()
    with client.messages.stream(
        model=MODEL or "claude-opus-4-8",
        max_tokens=32000,
        thinking={"type": "adaptive"},
        system=system,
        output_config={"format": {"type": "json_schema", "schema": schema}},
        messages=[{"role": "user", "content": user}],
    ) as stream:
        msg = stream.get_final_message()
    if msg.stop_reason == "refusal":
        raise RuntimeError("model refused the request")
    text = next((b.text for b in msg.content if b.type == "text"), "")
    return json.loads(text)


def _run(system, user, schema, cwd=None):
    return _run_sdk(system, user, schema) if USE_SDK else _run_cli(system, user, cwd)


# ----------------------------------------------------------------- story
STORY_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "title": {"type": "string"},
        "acts": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "properties": {"key": {"type": "string"}, "label": {"type": "string"}},
            "required": ["key", "label"]}},
        "beats": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "properties": {"t": {"type": "number"}, "act": {"type": "string"},
                           "title": {"type": "string"}, "summary": {"type": "string"}},
            "required": ["t", "act", "title", "summary"]}},
    },
    "required": ["title", "acts", "beats"],
}

STORY_SYSTEM = (
    "You are a story editor. Given a timestamped transcript of a video, produce a "
    "clear narrative map. Identify 3-7 narrative ACTS (the arc of the story), each "
    "with a short lowercase one-word key and a human label. Then split the video "
    "into chronological BEATS — roughly one beat per 20-45 seconds of video, at "
    "least 2, no more than 20. Each beat: t = its start time in SECONDS (a number "
    "from the transcript timestamps), act = one of your act keys, title = a short "
    "punchy beat title, summary = 2-4 plain-language sentences. Also write a "
    "concise, accurate overall title for the video. Base everything only on the "
    "transcript; never invent facts.\n\n"
    "Return ONLY minified JSON, no prose and no code fence, with exactly this shape: "
    '{"title":string,"acts":[{"key":string,"label":string}],'
    '"beats":[{"t":number,"act":string,"title":string,"summary":string}]}'
)


def build_story(groups, duration, cwd=None):
    lines = "\n".join(f"[{round(s,1)}] {t}" for s, _d, t in groups)
    user = (f"Video duration: {int(duration)} seconds.\n\n"
            f"Transcript (each line prefixed with its start time in seconds):\n{lines}")
    story = _run(STORY_SYSTEM, user, STORY_SCHEMA, cwd=cwd)
    story["duration"] = duration
    return story


# ----------------------------------------------------------------- translate
TRANSLATE_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "title": {"type": "string"},
        "acts": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "properties": {"key": {"type": "string"}, "label": {"type": "string"}},
            "required": ["key", "label"]}},
        "beats": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "properties": {"title": {"type": "string"}, "summary": {"type": "string"}},
            "required": ["title", "summary"]}},
        "captions": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "properties": {"start": {"type": "number"}, "text": {"type": "string"}},
            "required": ["start", "text"]}},
    },
    "required": ["title", "acts", "beats", "captions"],
}


def translate(story, groups, lang="Romanian", cwd=None):
    payload = {
        "title": story["title"],
        "acts": story["acts"],
        "beats": [{"title": b["title"], "summary": b["summary"]} for b in story["beats"]],
        "captions": [{"start": round(s, 1), "text": t} for s, _d, t in groups],
    }
    system = (
        f"You are a professional subtitle translator. Translate every human-readable "
        f"string in the given JSON into {lang}, natural and fluent. Keep the SAME "
        f"structure, the SAME number of array items, the SAME order, and the SAME "
        f"`key` and `start` values unchanged — translate only `label`, `title`, "
        f"`summary`, and caption `text`. Do not merge, drop, or add items.\n\n"
        f"Return ONLY minified JSON, no prose and no code fence, with the same shape "
        f"as the input."
    )
    user = "Translate this JSON:\n" + json.dumps(payload, ensure_ascii=False)
    return _run(system, user, TRANSLATE_SCHEMA, cwd=cwd)


# ----------------------------------------------------------------- combined (1 call)
COMBINED_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "title": {"type": "string"}, "title_t": {"type": "string"},
        "acts": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "properties": {"key": {"type": "string"}, "label": {"type": "string"},
                           "label_t": {"type": "string"}},
            "required": ["key", "label", "label_t"]}},
        "beats": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "properties": {"t": {"type": "number"}, "act": {"type": "string"},
                           "title": {"type": "string"}, "title_t": {"type": "string"},
                           "summary": {"type": "string"}, "summary_t": {"type": "string"}},
            "required": ["t", "act", "title", "title_t", "summary", "summary_t"]}},
        "captions": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "properties": {"start": {"type": "number"}, "text_t": {"type": "string"}},
            "required": ["start", "text_t"]}},
    },
    "required": ["title", "title_t", "acts", "beats", "captions"],
}


def build_and_translate(groups, duration, lang="English", cwd=None):
    """Map the story AND translate it in ONE agent call (half the cost/latency of
    build_story + translate). Returns (story, tr) in the same shapes those produce."""
    system = (
        STORY_SYSTEM + "\n\n"
        f"ALSO translate into {lang}: the overall title (`title_t`), each act label "
        f"(`label_t`), each beat's title (`title_t`) and summary (`summary_t`), and "
        f"EVERY transcript line (`captions`: one {{start, text_t}} per input line, "
        f"same start values, same count, in order). Keep the English originals.\n\n"
        "Return ONLY minified JSON, no prose, no code fence, with exactly this shape: "
        '{"title":str,"title_t":str,"acts":[{"key":str,"label":str,"label_t":str}],'
        '"beats":[{"t":num,"act":str,"title":str,"title_t":str,"summary":str,'
        '"summary_t":str}],"captions":[{"start":num,"text_t":str}]}'
    )
    lines = "\n".join(f"[{round(s,1)}] {t}" for s, _d, t in groups)
    user = (f"Video duration: {int(duration)} seconds.\n\n"
            f"Transcript (each line prefixed with its start time in seconds):\n{lines}")
    c = _run(system, user, COMBINED_SCHEMA, cwd=cwd)
    story = {
        "title": c["title"], "duration": duration,
        "acts": [{"key": a["key"], "label": a["label"]} for a in c["acts"]],
        "beats": [{"t": b["t"], "act": b["act"], "title": b["title"],
                   "summary": b["summary"]} for b in c["beats"]],
    }
    tr = {
        "title": c.get("title_t", ""),
        "acts": [{"key": a["key"], "label": a.get("label_t", a["label"])} for a in c["acts"]],
        "beats": [{"title": b.get("title_t", ""), "summary": b.get("summary_t", "")}
                  for b in c["beats"]],
        "captions": [{"start": x["start"], "text": x.get("text_t", "")}
                     for x in c.get("captions", [])],
    }
    return story, tr
