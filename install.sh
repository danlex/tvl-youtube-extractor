#!/usr/bin/env bash
# One-line installer: the video-extractor AGENT, its SKILL + /tvl-extract COMMAND,
# and the one tvl-ytx MCP SERVER (tools) for Claude Code.
#
#   curl -fsSL https://raw.githubusercontent.com/danlex/tvl-youtube-extractor/main/install.sh | bash
#
# Env overrides:
#   TVL_EXTRACTOR_DIR   where to clone the repo   (default: ~/.tvl-youtube-extractor)
#   CLAUDE_CONFIG_DIR   Claude Code config dir    (default: ~/.claude)
set -euo pipefail

REPO="https://github.com/danlex/tvl-youtube-extractor.git"
DIR="${TVL_EXTRACTOR_DIR:-$HOME/.tvl-youtube-extractor}"
CLAUDE="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"

say() { printf '  %s\n' "$*"; }
command -v git >/dev/null 2>&1 || { echo "error: git is required" >&2; exit 1; }

echo "▸ Installing TVL YouTube Extractor…"

# 1. clone (or update) the repo
if [ -d "$DIR/.git" ]; then
  git -C "$DIR" pull --ff-only --quiet || git -C "$DIR" fetch --quiet --depth 1 origin main && git -C "$DIR" reset --hard --quiet origin/main
  say "updated $DIR"
else
  rm -rf "$DIR"
  git clone --depth 1 --quiet "$REPO" "$DIR"
  say "cloned → $DIR"
fi
chmod +x "$DIR/extract.sh" "$DIR/run.sh" "$DIR/dev.sh" 2>/dev/null || true

# 2. install the skill(s)
mkdir -p "$CLAUDE/skills" "$CLAUDE/commands" "$CLAUDE/agents"
rm -rf "$CLAUDE/skills/tvl-youtube-extractor"
cp -r "$DIR/.claude/skills/tvl-youtube-extractor" "$CLAUDE/skills/"
say "skill   → $CLAUDE/skills/tvl-youtube-extractor"

# 3. install the agent
cp "$DIR/.claude/agents/video-extractor.md" "$CLAUDE/agents/video-extractor.md"
say "agent   → $CLAUDE/agents/video-extractor.md"

# 4. install the command, wiring in the absolute path to extract.sh
sed "s|__EXTRACT_SH__|$DIR/extract.sh|g" \
  "$DIR/.claude/commands/tvl-extract.md" > "$CLAUDE/commands/tvl-extract.md"
say "command → $CLAUDE/commands/tvl-extract.md"
if grep -q "__EXTRACT_SH__" "$CLAUDE/commands/tvl-extract.md"; then
  echo "error: command path was not substituted" >&2; exit 1
fi

# 5. register the one MCP server (tools) — lazily bootstrapped by bin/mcp.js
if command -v claude >/dev/null 2>&1 && command -v node >/dev/null 2>&1; then
  claude mcp remove tvl-ytx >/dev/null 2>&1 || true
  if claude mcp add tvl-ytx -- node "$DIR/bin/mcp.js" >/dev/null 2>&1; then
    say "mcp     → tvl-ytx (extract_video, get_transcript)"
  fi
elif command -v claude >/dev/null 2>&1; then
  say "mcp: install Node to auto-register, or run: claude mcp add tvl-ytx -- node $DIR/bin/mcp.js"
fi

echo "✓ Done — one agent, its skill + command, and one MCP."
echo
echo "  Ask Claude:  \"summarize this YouTube video: <url>\""
echo "  Command:     /tvl-extract https://youtu.be/VIDEO_ID Romanian"
echo "  Any agent:   the tvl-ytx MCP exposes extract_video / get_transcript"
echo
if ! command -v yt-dlp >/dev/null 2>&1 || ! command -v ffmpeg >/dev/null 2>&1; then
  echo "  Media tools needed:  brew install yt-dlp ffmpeg"
fi
