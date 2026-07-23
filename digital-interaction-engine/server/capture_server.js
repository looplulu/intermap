#!/usr/bin/env node
/*
 * Intermap capture server.
 *
 * Stores redacted interaction events from the web demo as JSONL training data.
 * It deliberately does not store screenshots or videos.
 */

const http = require("http");
const fs = require("fs");
const path = require("path");
const { spawn } = require("child_process");

const PORT = Number(process.env.PORT || 3011);
const DATA_DIR = process.env.INTERMAP_DATA_DIR || "/var/www/intermap-data";
const BUILDER_SCRIPT = process.env.INTERMAP_BUILDER_SCRIPT || path.join(__dirname, "build_live_training_flows.py");
const MAX_BODY_BYTES = 1024 * 1024;
let buildInProgress = false;

function sendJson(res, status, data) {
  const payload = Buffer.from(JSON.stringify(data), "utf8");
  res.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Access-Control-Allow-Origin": "https://loop-lulu.com",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Content-Length": payload.length,
  });
  res.end(payload);
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    let size = 0;
    const chunks = [];
    req.on("data", (chunk) => {
      size += chunk.length;
      if (size > MAX_BODY_BYTES) {
        reject(new Error("request body too large"));
        req.destroy();
        return;
      }
      chunks.push(chunk);
    });
    req.on("end", () => resolve(Buffer.concat(chunks).toString("utf8")));
    req.on("error", reject);
  });
}

function safeId(value) {
  return String(value || "unknown").replace(/[^a-zA-Z0-9_-]/g, "_").slice(0, 80);
}

function redactText(text) {
  return String(text || "")
    .replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi, "[email]")
    .replace(/1[3-9]\d{9}/g, "[phone]")
    .replace(/\b\d{8,}\b/g, "[number]");
}

function redactEvent(event) {
  const cloned = JSON.parse(JSON.stringify(event || {}));
  return redactValue(cloned);
}

function redactValue(value) {
  if (typeof value === "string") return redactText(value);
  if (Array.isArray(value)) return value.map(redactValue).filter((item) => item !== "");
  if (value && typeof value === "object") {
    const out = {};
    for (const [key, item] of Object.entries(value)) {
      out[key] = redactValue(item);
    }
    return out;
  }
  return value;
}

function appendEvent(event) {
  const redacted = redactEvent(event);
  const sessionId = safeId(redacted.session_id);
  const sessionDir = path.join(DATA_DIR, "training_sessions", sessionId);
  fs.mkdirSync(sessionDir, { recursive: true });

  const line = JSON.stringify(redacted) + "\n";
  fs.appendFileSync(path.join(sessionDir, "events.jsonl"), line, "utf8");

  const summary = {
    session_id: sessionId,
    updated_at: new Date().toISOString(),
    app: redacted.app || "",
    task: redacted.task || "",
    capture_mode: redacted.capture_mode || "",
    last_event_type: redacted.event_type || "",
    last_frame_seq: redacted.frame_seq || 0,
  };
  fs.writeFileSync(path.join(sessionDir, "latest.json"), JSON.stringify(summary, null, 2), "utf8");
  return { session_id: sessionId, path: sessionDir };
}

function buildReviewQueue() {
  if (buildInProgress) return;
  if (!fs.existsSync(BUILDER_SCRIPT)) return;
  buildInProgress = true;

  const sessionsDir = path.join(DATA_DIR, "training_sessions");
  const outputDir = path.join(DATA_DIR, "review_queue");
  fs.mkdirSync(outputDir, { recursive: true });

  const child = spawn("python3", [
    BUILDER_SCRIPT,
    "--sessions-dir",
    sessionsDir,
    "--output-dir",
    outputDir,
  ], { stdio: "ignore" });

  child.on("close", () => {
    buildInProgress = false;
  });
  child.on("error", () => {
    buildInProgress = false;
  });
}

const server = http.createServer(async (req, res) => {
  if (req.method === "OPTIONS") {
    sendJson(res, 204, {});
    return;
  }

  if (req.method === "GET" && (req.url === "/health" || req.url === "/api/health")) {
    sendJson(res, 200, { ok: true, service: "intermap-capture", data_dir: DATA_DIR });
    return;
  }

  if (req.method === "POST" && (req.url === "/events" || req.url === "/api/events")) {
    try {
      const body = await readBody(req);
      const event = JSON.parse(body);
      if (!event.session_id || !event.event_type) {
        sendJson(res, 400, { ok: false, error: "missing session_id or event_type" });
        return;
      }
      const saved = appendEvent(event);
      if (event.event_type === "session_end") buildReviewQueue();
      sendJson(res, 200, { ok: true, ...saved });
    } catch (error) {
      sendJson(res, 400, { ok: false, error: String(error.message || error) });
    }
    return;
  }

  sendJson(res, 404, { ok: false, error: "not found" });
});

server.listen(PORT, "127.0.0.1", () => {
  console.log(`intermap-capture listening on 127.0.0.1:${PORT}`);
  console.log(`data dir: ${DATA_DIR}`);
});
