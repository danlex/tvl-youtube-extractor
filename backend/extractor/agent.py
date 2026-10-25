"""The Claude agent: turns a raw transcript into a structured story.

Two structured-output calls against the Anthropic Messages API:
  1. build_story  — segment the narration into a narrative arc (acts + beats)
  2. translate    — translate the story + captions into the target language

Model defaults to claude-opus-4-8 (override with ANTHROPIC_MODEL). Streaming is
used so long transcripts/outputs don't hit HTTP timeouts. Output is constrained
with output_config.format (JSON schema) so the result is always valid JSON.
"""
import json
import os

import anthropic

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-8")
_client = None


def client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
    return _client


def _run(system, user, schema, max_tokens=32000):
    with client().messages.stream(
        model=MODEL,
        max_tokens=max_tokens,
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


STORY_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "title": {"type": "string"},
        "acts": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "key": {"type": "string"},
                    "label": {"type": "string"},
                },
                "required": ["key", "label"],
            },
        },
        "beats": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "t": {"type": "number"},
                    "act": {"type": "string"},
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                },
                "required": ["t", "act", "title", "summary"],
            },
        },
    },
    "required": ["title", "acts", "beats"],
}

STORY_SYSTEM = (
    "You are a story editor. Given a timestamped transcript of a video, produce a "
    "clear narrative map. Identify 4-7 narrative ACTS (the arc of the story) with a "
    "short key (lowercase, one word) and a human label. Then break the video into "
    "10-18 BEATS in chronological order. Each beat has: t = the start time in SECONDS "
    "(a number taken from the transcript timestamps), act = which act key it belongs "
    "to, title = a short punchy beat title, summary = 2-4 sentences explaining that "
    "beat in plain language. Write a concise, accurate overall title for the video. "
    "Base everything only on the transcript; never invent facts."
)


def build_story(groups, duration):
    """groups: list of (start, dur, text). Returns the English story dict."""
    lines = "\n".join(f"[{round(s,1)}] {t}" for s, _d, t in groups)
    user = (f"Video duration: {int(duration)} seconds.\n\n"
            f"Transcript (each line prefixed with its start time in seconds):\n{lines}")
    story = _run(STORY_SYSTEM, user, STORY_SCHEMA)
    story["duration"] = duration
    return story


TRANSLATE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "title": {"type": "string"},
        "acts": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"key": {"type": "string"}, "label": {"type": "string"}},
                "required": ["key", "label"],
            },
        },
        "beats": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"title": {"type": "string"}, "summary": {"type": "string"}},
                "required": ["title", "summary"],
            },
        },
        "captions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"start": {"type": "number"}, "text": {"type": "string"}},
                "required": ["start", "text"],
            },
        },
    },
    "required": ["title", "acts", "beats", "captions"],
}


def translate(story, groups, lang="Romanian"):
    """Translate the story + captions into `lang`. Returns a parallel dict:
    {title, acts:[{key,label}], beats:[{title,summary}] (same order),
     captions:[{start,text}] (same starts)}."""
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
        f"`summary`, and caption `text`. Do not merge or drop items."
    )
    user = "Translate this JSON:\n" + json.dumps(payload, ensure_ascii=False)
    return _run(system, user, TRANSLATE_SCHEMA)
