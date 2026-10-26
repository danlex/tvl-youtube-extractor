#!/usr/bin/env node
"use strict";
// Launch the TVL YouTube Extractor MCP server (Python) over stdio.
// First run bootstraps a venv + deps; all setup output goes to stderr so it never
// corrupts the MCP protocol on stdout.
const { spawnSync, spawn } = require("child_process");
const path = require("path");
const fs = require("fs");

const root = path.join(__dirname, "..", "backend");
const venv = path.join(root, ".venv");
const isWin = process.platform === "win32";
const py = isWin
  ? path.join(venv, "Scripts", "python.exe")
  : path.join(venv, "bin", "python");

function ensure() {
  if (fs.existsSync(py)) return;
  const quiet = { stdio: ["ignore", "ignore", "inherit"] };
  const python3 = isWin ? "python" : "python3";
  process.stderr.write("[tvl-ytx] first run: setting up Python env…\n");
  let r = spawnSync(python3, ["-m", "venv", venv], quiet);
  if (r.status !== 0) { process.stderr.write("[tvl-ytx] could not create venv (need python3)\n"); process.exit(1); }
  r = spawnSync(py, ["-m", "pip", "install", "-q", "--upgrade", "pip"], quiet);
  r = spawnSync(py, ["-m", "pip", "install", "-q", "-r", path.join(root, "requirements.txt")], quiet);
  if (r.status !== 0) { process.stderr.write("[tvl-ytx] dependency install failed\n"); process.exit(1); }
}

ensure();
const child = spawn(py, ["-m", "extractor.mcp_server"], { cwd: root, stdio: "inherit" });
child.on("exit", (code) => process.exit(code || 0));
