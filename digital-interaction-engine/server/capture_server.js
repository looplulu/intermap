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
const crypto = require("crypto");
const { spawn } = require("child_process");
const { TrainingEvidenceStore } = require('./training_evidence');

const PORT = Number(process.env.PORT || 3011);
const ARK_API_KEY = process.env.ARK_API_KEY || '';
const ARK_MODEL = process.env.ARK_MODEL || 'doubao-seed-2-1-turbo-260628';
const ARK_BASE_URL = 'https://ark.cn-beijing.volces.com/api/v3';
const DATA_DIR = process.env.INTERMAP_DATA_DIR || "/var/www/intermap-data";
const BUILDER_SCRIPT = process.env.INTERMAP_BUILDER_SCRIPT || path.join(__dirname, "build_live_training_flows.py");
const PYTHON_BIN = process.env.INTERMAP_PYTHON_BIN || "/opt/miniconda3/envs/ocr/bin/python";
const OCR_API_URL = process.env.INTERMAP_OCR_URL || "http://127.0.0.1:18000/api/analyze_base64";
const MAX_BODY_BYTES = 12 * 1024 * 1024;
const evidenceStore = new TrainingEvidenceStore(DATA_DIR);
let evidenceWorker = null;
function processEvidence() {
  if (evidenceWorker) return;
  const script = process.env.INTERMAP_EVIDENCE_PROCESSOR || path.join(__dirname, 'process_android_evidence.py');
  if (!fs.existsSync(script)) return;
  evidenceWorker = spawn(PYTHON_BIN, [script, '--root', evidenceStore.root], {stdio: 'ignore'});
  evidenceWorker.on('error', () => { evidenceWorker = null; });
  evidenceWorker.on('close', () => { evidenceWorker = null; });
}
let buildInProgress = false;

// ═══ Rate Limiting & Caching ═══
let lastApiCallTime = 0;
const API_MIN_INTERVAL_MS = 100;
const aiResultCache = new Map();
const CACHE_TTL_MS = 30000; // 30 seconds
const CACHE_MAX_SIZE = 30;

function getCacheKey(imageB64, task, mode) {
  return crypto.createHash("sha1")
    .update(String(mode || "default"))
    .update("\n")
    .update(String(task || ""))
    .update("\n")
    .update(String(imageB64 || ""))
    .digest("hex");
}

function getCachedResult(key) {
  const entry = aiResultCache.get(key);
  if (!entry) return null;
  if (Date.now() - entry.timestamp > CACHE_TTL_MS) {
    aiResultCache.delete(key);
    return null;
  }
  return entry.result;
}

function setCachedResult(key, result) {
  if (aiResultCache.size >= CACHE_MAX_SIZE) {
    const firstKey = aiResultCache.keys().next().value;
    aiResultCache.delete(firstKey);
  }
  aiResultCache.set(key, { result: JSON.parse(JSON.stringify(result)), timestamp: Date.now() });
}

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

function storeSessionBatch(batch) {
  const snapshot = batch.payload || {};
  const sourceEvents = Array.isArray(snapshot.events) ? snapshot.events : [];
  if (sourceEvents.length === 0) throw new Error("session batch has no events");
  if (sourceEvents.length > 10000) throw new Error("session batch has too many events");

  const sessionId = safeId(batch.session_id || snapshot.session_id);
  const app = String(batch.app || snapshot.app || "unknown");
  const task = String(batch.task || snapshot.task || "unknown");
  const captureMode = String(batch.capture_mode || snapshot.capture_mode || "android_screen");
  const normalizedEvents = sourceEvents.map((item, index) => redactEvent({
    ...item,
    event_id: item.event_id || `${sessionId}_${index + 1}`,
    session_id: sessionId,
    app: item.app || app,
    task: item.task || task,
    capture_mode: item.capture_mode || captureMode,
  }));

  const sessionDir = path.join(DATA_DIR, "training_sessions", sessionId);
  fs.mkdirSync(sessionDir, { recursive: true });
  const eventsPath = path.join(sessionDir, "events.jsonl");
  const tempPath = `${eventsPath}.tmp`;
  fs.writeFileSync(
    tempPath,
    normalizedEvents.map(event => JSON.stringify(event)).join("\n") + "\n",
    "utf8"
  );
  fs.renameSync(tempPath, eventsPath);

  const safeSnapshot = redactEvent({
    ...snapshot,
    events: normalizedEvents,
    upload_state: "received",
  });
  fs.writeFileSync(
    path.join(sessionDir, "session.json"),
    JSON.stringify(safeSnapshot, null, 2),
    "utf8"
  );

  const nodeCount = Array.isArray(snapshot.inferred_nodes) ? snapshot.inferred_nodes.length : 0;
  const annotationCount = Array.isArray(snapshot.annotations) ? snapshot.annotations.length : 0;
  const summary = {
    session_id: sessionId,
    updated_at: new Date().toISOString(),
    app,
    task,
    capture_mode: captureMode,
    last_event_type: normalizedEvents[normalizedEvents.length - 1].event_type || "",
    stored_events: normalizedEvents.length,
    stored_nodes: nodeCount,
    stored_annotations: annotationCount,
    status: "pending_review",
  };
  fs.writeFileSync(
    path.join(sessionDir, "latest.json"),
    JSON.stringify(summary, null, 2),
    "utf8"
  );
  return summary;
}

function appendNavigationDiagnostic(input) {
  const allowedTypes = new Set([
    "navigation_started",
    "local_ocr_result",
    "api_error",
    "api_result",
    "guidance_suppressed",
    "guidance_announced",
  ]);
  const eventType = String(input.event_type || "");
  if (!allowedTypes.has(eventType)) throw new Error("invalid diagnostic event type");

  const sessionId = safeId(input.session_id);
  const day = new Date().toISOString().slice(0, 10);
  const outputDir = path.join(DATA_DIR, "navigation_diagnostics", day);
  fs.mkdirSync(outputDir, { recursive: true });
  const sourcePayload = input.payload && typeof input.payload === "object"
    ? input.payload
    : {};
  const payload = {};
  for (const key of [
    "capture_mode",
    "error",
    "duration_ms",
    "http_status",
    "page_name",
    "page_key",
    "guidance",
    "action_type",
    "confidence",
    "reason",
    "ocr_count",
  ]) {
    if (sourcePayload[key] !== undefined) payload[key] = sourcePayload[key];
  }
  const event = redactEvent({
    session_id: sessionId,
    event_type: eventType,
    timestamp: input.timestamp || new Date().toISOString(),
    app: String(input.app || "douyin").slice(0, 40),
    payload,
  });
  fs.appendFileSync(
    path.join(outputDir, `${sessionId}.jsonl`),
    JSON.stringify(event) + "\n",
    "utf8"
  );
  return { session_id: sessionId, stored: true };
}

function buildReviewQueue() {
  if (buildInProgress) return;
  if (!fs.existsSync(BUILDER_SCRIPT)) return;
  buildInProgress = true;

  const sessionsDir = path.join(DATA_DIR, "training_sessions");
  const outputDir = path.join(DATA_DIR, "review_queue");
  fs.mkdirSync(outputDir, { recursive: true });

  const child = spawn(PYTHON_BIN, [
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

// ═══ Corrections Knowledge ═══
const KNOWLEDGE_FILE = path.join(DATA_DIR, "corrections_knowledge.json");
let correctionsKnowledge = null;
let knowledgeLoadedAt = 0;

function loadCorrectionsKnowledge() {
  // Reload every 60 seconds
  if (correctionsKnowledge && (Date.now() - knowledgeLoadedAt) < 60000) {
    return correctionsKnowledge;
  }
  try {
    if (fs.existsSync(KNOWLEDGE_FILE)) {
      correctionsKnowledge = JSON.parse(fs.readFileSync(KNOWLEDGE_FILE, "utf8"));
      knowledgeLoadedAt = Date.now();
      return correctionsKnowledge;
    }
  } catch (e) {}
  correctionsKnowledge = { pages: {}, updated_at: "" };
  return correctionsKnowledge;
}

function buildCorrectionsKnowledge() {
  try {
    const sessionsDir = path.join(DATA_DIR, "training_sessions");
    if (!fs.existsSync(sessionsDir)) return;

    // Scan all training_step_corrected events
    const pageCorrections = {}; // page_name -> [{ai_action, correction, count}]
    const sessions = fs.readdirSync(sessionsDir).sort();

    for (const sid of sessions) {
      const eventsFile = path.join(sessionsDir, sid, "events.jsonl");
      if (!fs.existsSync(eventsFile)) continue;
      const lines = fs.readFileSync(eventsFile, "utf8").split("\n");
      for (const line of lines) {
        if (!line.trim()) continue;
        try {
          const evt = JSON.parse(line);
          if (evt.event_type !== "train_step_corrected") continue;
          const payload = evt.payload || {};
          const page = String(payload.page || "unknown").trim();
          const correction = String(payload.feedback_note || "").trim();
          if (!correction) continue;

          if (!pageCorrections[page]) pageCorrections[page] = [];
          pageCorrections[page].push(correction);
        } catch (e) {}
      }
    }

    // Aggregate: count frequency, deduplicate similar corrections
    const pages = {};
    for (const [page, corrections] of Object.entries(pageCorrections)) {
      // Count each correction text
      const counts = {};
      corrections.forEach(c => { counts[c] = (counts[c] || 0) + 1; });
      // Sort by frequency, deduplicate
      const sorted = Object.entries(counts)
        .sort((a, b) => b[1] - a[1]);
      // Keep unique corrections (top 5 by frequency)
      const unique = sorted.slice(0, 5).map(([text, count]) => ({ text, count }));

      pages[page] = {
        corrections: unique,
        total_corrections: corrections.length,
      };
    }

    const knowledge = {
      pages: pages,
      total_pages: Object.keys(pages).length,
      updated_at: new Date().toISOString(),
    };

    fs.writeFileSync(KNOWLEDGE_FILE, JSON.stringify(knowledge, null, 2), "utf8");
    correctionsKnowledge = knowledge;
    knowledgeLoadedAt = Date.now();
    console.log(`Built corrections knowledge: ${Object.keys(pages).length} pages`);
  } catch (e) {
    console.error("Failed to build corrections knowledge:", e.message);
  }
}

function getKnowledgeForPage(pageName) {
  const knowledge = loadCorrectionsKnowledge();
  if (!knowledge || !knowledge.pages) return null;

  // Exact match first
  if (knowledge.pages[pageName]) {
    return knowledge.pages[pageName];
  }

  // Fuzzy match: find pages with >50% character overlap
  for (const [key, value] of Object.entries(knowledge.pages)) {
    if (pageNameSimilarChars(pageName, key)) {
      return value;
    }
  }
  return null;
}

function pageNameSimilarChars(a, b) {
  if (!a || !b || a === b) return a === b;
  const shorter = a.length <= b.length ? a : b;
  const longer = a.length <= b.length ? b : a;
  let common = 0;
  for (let i = 0; i < shorter.length; i++) {
    if (longer.indexOf(shorter[i]) >= 0) common++;
  }
  return common / shorter.length > 0.5;
}

// ═══ Task Flows ═══
const TASK_FLOWS_FILE = path.join(DATA_DIR, "task_flows.json");
let taskFlows = null;
let taskFlowsLoadedAt = 0;

function loadTaskFlows() {
  if (taskFlows && (Date.now() - taskFlowsLoadedAt) < 60000) return taskFlows;
  try {
    if (fs.existsSync(TASK_FLOWS_FILE)) {
      taskFlows = JSON.parse(fs.readFileSync(TASK_FLOWS_FILE, "utf8"));
      taskFlowsLoadedAt = Date.now();
      return taskFlows;
    }
  } catch (e) {}
  taskFlows = { flows: [] };
  return taskFlows;
}

function normalizeAppKey(value) {
  const app = String(value || "").toLowerCase();
  if (app.includes("douyin") || app.includes("抖音")) return "douyin";
  if (app.includes("taobao") || app.includes("淘宝")) return "taobao";
  if (app.includes("jd") || app.includes("京东")) return "jd";
  return app.replace(/[^a-z0-9\u4e00-\u9fff]+/g, "");
}

function sameTrainingPage(a, b) {
  const left = normalizePageName(a);
  const right = normalizePageName(b);
  if (!left || !right) return false;
  return left === right || left.includes(right) || right.includes(left);
}

function mergeTrainingPaths(paths) {
  const ordered = paths
    .filter(path => Array.isArray(path) && path.length > 0)
    .sort((a, b) => {
      const score = path => path.length * 10
        + path.filter(step => step.action).length
        + path.filter(step => step.is_correction).length * 3;
      return score(b) - score(a);
    });
  if (ordered.length === 0) return [];

  let canonical = ordered[0].map(step => ({ ...step }));
  for (const candidate of ordered.slice(1)) {
    let overlap = null;
    for (let candidateIndex = 0; candidateIndex < candidate.length; candidateIndex++) {
      for (let canonicalIndex = 0; canonicalIndex < canonical.length; canonicalIndex++) {
        if (!sameTrainingPage(candidate[candidateIndex].page, canonical[canonicalIndex].page)) continue;
        overlap = { candidateIndex, canonicalIndex };
        break;
      }
      if (overlap) break;
    }
    if (!overlap) continue;

    for (const step of candidate) {
      const target = canonical.find(item => sameTrainingPage(item.page, step.page));
      if (!target) continue;
      const newerCorrection = step.is_correction &&
        step.action &&
        (!target.is_correction || (step.timestamp || 0) >= (target.timestamp || 0));
      if (newerCorrection || (!target.action && step.action)) {
        target.action = step.action;
        target.timestamp = step.timestamp || 0;
      }
      if (step.is_correction) target.is_correction = true;
    }

    if (overlap.canonicalIndex === 0 && overlap.candidateIndex > 0) {
      canonical = candidate
        .slice(0, overlap.candidateIndex)
        .map(step => ({ ...step }))
        .concat(canonical);
    }
    if (
      overlap.canonicalIndex === canonical.length - 1 &&
      overlap.candidateIndex < candidate.length - 1
    ) {
      canonical = canonical.concat(
        candidate.slice(overlap.candidateIndex + 1).map(step => ({ ...step }))
      );
    }
  }
  return canonical;
}

function buildTaskFlows() {
  try {
    const sessionsDir = path.join(DATA_DIR, "training_sessions");
    if (!fs.existsSync(sessionsDir)) return;

    // Collect all training steps grouped by session
    const sessionGoals = {}; // session_id -> { goal, steps: [{step_count, page, action, feedback_type, feedback_note}] }
    const sessions = fs.readdirSync(sessionsDir).sort();

    for (const sid of sessions) {
      const eventsFile = path.join(sessionsDir, sid, "events.jsonl");
      if (!fs.existsSync(eventsFile)) continue;
      const lines = fs.readFileSync(eventsFile, "utf8").split("\n");
      let sessionGoal = "";
      let sessionApp = "";
      let steps = [];

      for (const line of lines) {
        if (!line.trim()) continue;
        try {
          const evt = JSON.parse(line);
          const payload = evt.payload || {};

          if (!sessionApp) {
            sessionApp = normalizeAppKey(payload.app_key || evt.app || "");
          }

          if (evt.event_type === "train_step_corrected" || evt.event_type === "train_step_confirmed") {
            const goal = String(payload.goal || sessionGoal || "").trim();
            if (!sessionGoal && goal) sessionGoal = goal;
            steps.push({
              step_count: payload.step_count || steps.length + 1,
              page: String(payload.page || "").trim(),
              action: String(payload.action || "").trim(),
              feedback_type: payload.feedback_type || evt.event_type,
              feedback_note: String(payload.feedback_note || "").trim(),
              timestamp: Date.parse(evt.timestamp || "") || 0,
              verified: evt.event_type === "train_step_confirmed" || (payload.feedback_type === "wrong_action" && payload.feedback_note),
            });
          }
        } catch (e) {}
      }

      if (steps.length > 0 && sessionGoal) {
        sessionGoals[sid] = { goal: sessionGoal, app: sessionApp, steps: steps };
      }
    }

    // Aggregate by goal: merge all sessions for the same goal, keep best path
    const goalFlows = {};
    for (const [sid, data] of Object.entries(sessionGoals)) {
      const goal = data.goal;
      if (!goal) continue;

      // Build path from steps: use corrected/confirmed actions as the verified path
      const path = data.steps
        .sort((a, b) => (a.step_count || 0) - (b.step_count || 0))
        .map(s => ({
          page: s.page,
          action: s.feedback_note || s.action,
          is_correction: s.feedback_type === "wrong_action",
          timestamp: s.timestamp || 0,
        }));

      const flowKey = `${normalizeAppKey(data.app)}::${goal}`;
      if (!goalFlows[flowKey]) {
        goalFlows[flowKey] = { goal: goal, app: normalizeAppKey(data.app), paths: [], total_runs: 0 };
      }
      goalFlows[flowKey].paths.push(path);
      goalFlows[flowKey].total_runs++;
    }

    // For each goal, pick the longest verified path as canonical
    const flows = [];
    for (const data of Object.values(goalFlows)) {
      const canonicalPath = mergeTrainingPaths(data.paths).map(step => ({
        page: step.page,
        best_action: step.action,
        correction_count: step.is_correction ? 1 : 0,
      }));

      flows.push({
        goal: data.goal,
        app: data.app,
        steps: canonicalPath,
        total_runs: data.total_runs,
        step_count: canonicalPath.length,
      });
    }

    const result = { flows: flows, total_flows: flows.length, updated_at: new Date().toISOString() };
    fs.writeFileSync(TASK_FLOWS_FILE, JSON.stringify(result, null, 2), "utf8");
    taskFlows = result;
    taskFlowsLoadedAt = Date.now();
    console.log(`Built task flows: ${flows.length} goals, ${flows.reduce((s, f) => s + f.step_count, 0)} total steps`);
  } catch (e) {
    console.error("Failed to build task flows:", e.message);
  }
}

function findBestFlow(goal, app) {
  const data = loadTaskFlows();
  if (!data || !data.flows) return null;

  const goalLower = (goal || "").toLowerCase().trim();
  if (!goalLower) return null;
  const appKey = normalizeAppKey(app);
  const candidates = data.flows.filter(flow => {
    const flowApp = normalizeAppKey(flow.app);
    return !appKey || !flowApp || appKey === flowApp;
  });

  // Exact match
  for (const flow of candidates) {
    if (flow.goal.toLowerCase() === goalLower) return flow;
  }

  const refundWords = ["退款", "退货"];
  if (refundWords.some(word => goalLower.includes(word))) {
    const refundFlow = candidates.find(flow =>
      refundWords.some(word => String(flow.goal || "").includes(word))
    );
    if (refundFlow) return refundFlow;
  }

  // Keyword match: check if goal contains key words from flow
  for (const flow of candidates) {
    const flowWords = flow.goal.split(/[\s,，、]+/).filter(w => w.length >= 2);
    const matched = flowWords.filter(w => goalLower.includes(w));
    if (matched.length >= 1 && matched.length / flowWords.length >= 0.5) return flow;
  }

  return null;
}

function verifyTrainPassword(password) {
  const expected = process.env.TRAIN_PASSWORD || "1623";
  return password === expected;
}

function normalizePageName(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/^(当前是|这是|当前页面是)\s*/, "")
    .replace(/\d+(?:\.\d+)?/g, "")
    .replace(/(页面|页)$/g, "")
    .replace(/[^\u4e00-\u9fffa-z]+/g, "");
}

function stablePageKey(pageName, ocrTexts) {
  const normalizedName = normalizePageName(pageName);
  const stableTexts = (ocrTexts || [])
    .map(normalizePageName)
    .filter(text => text.length >= 2)
    .slice(0, 8)
    .sort()
    .join("|");
  const identity = normalizedName || stableTexts || "unknown";
  return crypto.createHash("sha1").update(identity).digest("hex").slice(0, 12);
}

function extractThoughtField(thought, label, stopLabels) {
  const stop = stopLabels.map(value => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|");
  const escapedLabel = label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = String(thought || "").match(
    new RegExp(`(?:^|\\n)${escapedLabel}\\s*[:：]\\s*(.+?)(?=\\n(?:${stop})\\s*[:：]|$)`, "s")
  );
  return match ? match[1].trim() : "";
}

function normalizeFastNavigationThought(thought) {
  const text = String(thought || "").trim();
  if (!text || /(?:^|\n)(?:页面名|当前页面|页面)\s*[:：]/.test(text)) {
    return text;
  }
  const lines = text.split(/\n+/).map(line => line.trim()).filter(Boolean);
  if (lines.length < 2) return text;
  return `页面名: ${lines[0]}\n操作: ${lines.slice(1).join(" ")}`;
}

function extractAmounts(texts) {
  const amounts = new Set();
  for (const text of texts || []) {
    const matches = String(text).match(/(?:¥|￥)?\s*\d+(?:\.\d{1,2})/g) || [];
    matches.forEach(value => {
      const cleaned = value.replace(/\s+/g, "");
      if (cleaned.includes(".") || cleaned.startsWith("¥") || cleaned.startsWith("￥")) {
        amounts.add(cleaned);
      }
    });
  }
  return Array.from(amounts).slice(0, 20);
}

async function getOcrEvidence(imageData) {
  try {
    const raw = String(imageData || "").replace(/^data:image\/[^;]+;base64,/, "");
    const form = new FormData();
    form.append("image_base64", raw);
    form.append("app", "douyin");
    form.append("task", "screen_observation");
    const response = await fetch(OCR_API_URL, {
      method: "POST",
      body: form,
      signal: AbortSignal.timeout(20000),
    });
    if (!response.ok) return { texts: [], items: [] };
    const data = await response.json();
    return {
      texts: Array.isArray(data.ocr_texts) ? data.ocr_texts : [],
      items: Array.isArray(data.ocr_items) ? data.ocr_items : [],
    };
  } catch (_) {
    return { texts: [], items: [] };
  }
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

  if (req.method === "POST" && (req.url === "/api/rebuild-knowledge" || req.url === "/rebuild-knowledge")) {
    let auth;
    try { auth = JSON.parse(await readBody(req)); } catch (_) { sendJson(res, 400, {ok: false}); return; }
    if (!verifyTrainPassword(String(auth.password || ''))) { sendJson(res, 403, {ok: false}); return; }
    buildCorrectionsKnowledge();
    buildTaskFlows();
    const kb = loadCorrectionsKnowledge();
    const tf = loadTaskFlows();
    sendJson(res, 200, { ok: true, pages: kb.total_pages || Object.keys(kb.pages || {}).length, task_flows: tf.total_flows || 0 });
    return;
  }

  if (req.method === 'POST' && req.url === '/api/training-evidence') {
    try {
      const data = JSON.parse(await readBody(req));
      if (!verifyTrainPassword(String(data.password || ''))) {
        sendJson(res, 403, {ok: false, error: 'invalid training password'}); return;
      }
      delete data.password;
      const receipt = evidenceStore.handle(data);
      sendJson(res, 200, receipt);
      if (data.operation === 'finish' || data.operation === 'retry') processEvidence();
    } catch (error) { sendJson(res, 400, {ok: false, error: String(error.message || error)}); }
    return;
  }

  if (req.method === "POST" && (req.url === "/events" || req.url === "/api/events")) {
    try {
      const body = await readBody(req);
      const event = JSON.parse(body);
      if (!verifyTrainPassword(String(event.password || ''))) {
        sendJson(res, 403, {ok: false, error: 'invalid training password'}); return;
      }
      if (!event.session_id || !event.event_type) {
        sendJson(res, 400, { ok: false, error: "missing session_id or event_type" });
        return;
      }
      if (event.event_type === "session_batch") {
        if (!verifyTrainPassword(String(event.password || ""))) {
          sendJson(res, 403, { ok: false, error: "invalid training password" });
          return;
        }
        delete event.password;
        const receipt = storeSessionBatch(event);
        buildReviewQueue();
        buildCorrectionsKnowledge();
        buildTaskFlows();
        sendJson(res, 200, {
          ok: true,
          ...receipt,
          map_status: "pending_review",
        });
        return;
      }
      delete event.password;
      const saved = appendEvent(event);
      if (event.event_type === "session_end") {
        buildReviewQueue();
        buildCorrectionsKnowledge();
        buildTaskFlows();
      }
      sendJson(res, 200, { ok: true, ...saved });
    } catch (error) {
      sendJson(res, 400, { ok: false, error: String(error.message || error) });
    }
    return;
  }

  if (req.method === "POST" && (req.url === "/api/verify-train-password" || req.url === "/verify-train-password")) {
    try {
      const body = await readBody(req);
      const data = JSON.parse(body);
      const password = String(data.password || "");
      const ok = verifyTrainPassword(password);
      sendJson(res, 200, { ok: true, verified: ok });
    } catch (error) {
      sendJson(res, 400, { ok: false, error: String(error.message || error) });
    }
    return;
  }

  if (req.method === "POST" && (req.url === "/api/navigation-diagnostics" || req.url === "/navigation-diagnostics")) {
    try {
      const body = await readBody(req);
      const diagnostic = JSON.parse(body);
      const saved = appendNavigationDiagnostic(diagnostic);
      sendJson(res, 200, { ok: true, ...saved });
    } catch (error) {
      sendJson(res, 400, { ok: false, error: String(error.message || error) });
    }
    return;
  }

  // GET /api/corrections — return recent train_step_corrected events
  if (req.method === "GET" && (req.url === "/api/corrections" || req.url === "/corrections")) {
    try {
      const sessionsDir = path.join(DATA_DIR, "training_sessions");
      const corrections = [];
      if (fs.existsSync(sessionsDir)) {
        const sessions = fs.readdirSync(sessionsDir).sort().reverse();
        for (const sid of sessions) {
          const eventsFile = path.join(sessionsDir, sid, "events.jsonl");
          if (!fs.existsSync(eventsFile)) continue;
          const lines = fs.readFileSync(eventsFile, "utf8").split("\n");
          for (const line of lines) {
            if (!line.trim()) continue;
            try {
              const evt = JSON.parse(line);
              if (evt.event_type === "train_step_corrected") {
                corrections.push({
                  page: evt.payload && evt.payload.page || "",
                  ai_action: evt.payload && evt.payload.action || "",
                  correction: evt.payload && evt.payload.feedback_note || "",
                  feedback_type: evt.payload && evt.payload.feedback_type || "",
                  step: evt.payload && evt.payload.step_count || 0,
                  timestamp: evt.timestamp || ""
                });
              }
            } catch (e) {}
          }
          if (corrections.length >= 50) break;
        }
      }
      sendJson(res, 200, { ok: true, corrections: corrections.slice(0, 50) });
    } catch (error) {
      sendJson(res, 500, { ok: false, error: String(error.message || error) });
    }
    return;
  }

  if (req.method === 'POST' && (req.url === '/api/ui-tars' || req.url === '/ui-tars')) {
    try {
      const body = await readBody(req);
      const data = JSON.parse(body);

      if (!ARK_API_KEY) {
        sendJson(res, 500, { ok: false, error: 'ARK_API_KEY not configured on server' });
        return;
      }

      // Extract fields from request
      const imageData = data.image; // base64 image data (with or without data:image prefix)
      if (!imageData) {
        sendJson(res, 400, { ok: false, error: "image field is required" });
        return;
      }
      const task = data.task || '\u8bc6\u522b\u5f53\u524d\u9875\u9762\u5185\u5bb9\uff0c\u5e76\u6307\u51fa\u5e94\u8be5\u70b9\u51fb\u54ea\u4e2a\u6309\u94ae';
      const fastNavigation = data.fast_navigation === true;

      // Check cache first
      const cacheKey = getCacheKey(imageData, task, fastNavigation ? "fast" : "full");
      const cached = getCachedResult(cacheKey);
      if (cached) {
        cached.cached = true;
        sendJson(res, 200, cached);
        return;
      }

      // Rate limit: wait if needed
      const now = Date.now();
      const waitTime = lastApiCallTime + API_MIN_INTERVAL_MS - now;
      if (waitTime > 0) {
        await new Promise(r => setTimeout(r, waitTime));
      }
      const history = data.history || []; // array of previous messages [{role, content}]
      const app = normalizeAppKey(data.app || "");
      const imageWidth = data.image_width || 0;
      const imageHeight = data.image_height || 0;
      // Demo navigation must stay responsive. Training explicitly opts in to
      // the slower server OCR pass when it needs archival evidence.
      const includeOcrEvidence = data.include_ocr_evidence === true;
      const ocrEvidence = includeOcrEvidence
        ? await getOcrEvidence(imageData)
        : { texts: [], items: [] };
      const ocrTexts = ocrEvidence.texts;
      const amounts = extractAmounts(ocrTexts);

      // Try to find a verified task flow matching the user's goal
      const goalMatch = task.match(/用户的目标是[:：]?\s*"([^"]+)"/);
      const userGoal = goalMatch ? goalMatch[1].trim() : task.trim();
      const matchedFlow = findBestFlow(userGoal, app);
      const isDouyinRefund = app === "douyin" && /退款|退货/.test(userGoal);

      let enrichedTask = task;
      if (ocrTexts.length > 0) {
        enrichedTask += "\n\n## 独立OCR核对结果\n";
        enrichedTask += ocrTexts.slice(0, 60).map(text => `- ${text}`).join("\n");
        if (amounts.length > 0) {
          enrichedTask += `\n检测到的金额或小数: ${amounts.join("、")}`;
        }
        enrichedTask += "\nOCR中的小数点、金额和数量必须原样保留。视觉结果与OCR冲突时，仔细查看截图二次核对，不要擅自去掉小数点。\n";
      }
      if (matchedFlow && !isDouyinRefund) {
        // Inject verified path as step-by-step guidance
        enrichedTask += '\n\n## 已验证的操作路径（用户已纠正确认，请按此路径引导）：\n';
        enrichedTask += `目标: ${matchedFlow.goal}（用户验证了${matchedFlow.total_runs}次）\n`;
        matchedFlow.steps.forEach((step, i) => {
          enrichedTask += `第${i + 1}步: 在"${step.page}"页面 → ${step.best_action}\n`;
        });
        enrichedTask += '\n请根据当前截图判断用户在第几步，建议下一步操作。如果当前页面与路径中的步骤不匹配，可以适当调整。\n';
      } else if (!fastNavigation) {
        // Fallback: inject page-level corrections knowledge
        const knowledge = loadCorrectionsKnowledge();
        if (knowledge && knowledge.pages && Object.keys(knowledge.pages).length > 0) {
          enrichedTask += '\n\n## 用户纠正知识库（这些是用户之前纠正过的操作，请务必遵守）：\n';
          for (const [page, info] of Object.entries(knowledge.pages)) {
            if (!info.corrections || info.corrections.length === 0) continue;
            enrichedTask += `\n当页面为"${page}"时：\n`;
            info.corrections.forEach(c => {
              enrichedTask += `- 正确操作: ${c.text}（用户纠正了${c.count}次）\n`;
            });
          }
        }
      }
      if (isDouyinRefund) {
        enrichedTask += "\n\n## 已验证的抖音退款路径，不得改道\n";
        enrichedTask += "首页→点右下角‘我’；个人主页→点购物车图标的第一个订单入口；";
        enrichedTask += "商城页→点左上角的第二个订单入口，禁止点‘退款/售后’；";
        enrichedTask += "进入全部订单页后→让用户自己选想退货的商品；订单详情→点‘申请退款’。\n";
        enrichedTask += "地图只决定目标位置和语义。按钮文字必须逐字采用当前截图实际显示，";
        enrichedTask += "即使与训练时的‘我的订单’不同，也绝不能用历史文字替代。\n";
      }

      // Build system prompt using UI-TARS phone template
      const instruction = enrichedTask;
      const language = 'Chinese';
      let systemPrompt = fastNavigation
        ? `根据手机截图和用户目标给出下一步。只输出两行，不解释：\n页面名: 稳定简短的页面名\n操作: 严格使用“在{位置}，点击{当前截图实际显示的文字或元素名称}[，它是{图标外观}]”句式\n必须先说位置，再说点击什么，最后才说图标外观；目标没有图标或图案时，省略最后的外观描述\n可见文字必须逐字来自当前截图，禁止照抄地图里的历史按钮名\n例如：在屏幕下方偏左，点击“抖音”，它是黑色方形里有彩色音符的图标\n例如：在页面底部，点击“提交申请”\n同一页面始终使用同一页面名。看不清金额时不要猜测或复述。\n用户目标：${instruction}`
        : `You are a GUI agent helping an elderly user navigate a phone app. You are given a task and screenshots. You need to analyze the current screen and suggest the next action.\n## Output Format\n\`\`\`\nThought: ...\nAction: ...\n\`\`\`\n\n## Action Space\nclick(point='<point>x1 y1</point>')\nlong_press(point='<point>x1 y1</point>')\ntype(content='')\nscroll(point='<point>x1 y1</point>', direction='down or up or right or left')\nopen_app(app_name='')\ndrag(start_point='<point>x1 y1</point>', end_point='<point>x2 y2</point>')\npress_home()\npress_back()\nfinished(content='')\n\n## CRITICAL RULES for Thought part (use ${language}):\n1. 第一行写: 页面名: XXX（简洁的页面名称，如"抖音首页"、"抖音个人主页"）\n2. 第二行写: 操作: 用通俗易懂的文字描述下一步操作，必须说清楚：在屏幕的什么位置（如左上角、右下角、中间偏下）、是什么元素（按钮、图标、文字链接）、上面写着什么字或画着什么图案。例如："点击右下角的'我'标签"、"点击左上角的返回箭头"、"向上滑动屏幕查看更多商品"。\n3. 绝对不要在Thought中输出坐标数字。\n4. 页面名要简洁稳定，同一个页面每次用相同的名字。\n\n## User Instruction\n${instruction}`;
      systemPrompt += "\n\n## 精度规则\n";
      systemPrompt += "5. 涉及金额时，只有看清小数点后才能提及；导航语音无需复述金额。\n";

      const imageUrl = imageData.startsWith('data:') ? imageData : `data:image/jpeg;base64,${imageData}`;
      const messages = fastNavigation
        ? [{
            role: 'user',
            content: [
              { type: 'text', text: systemPrompt },
              { type: 'image_url', image_url: { url: imageUrl, detail: 'high' } }
            ]
          }]
        : [{ role: 'user', content: systemPrompt }];

      if (!fastNavigation) {
        history.forEach(function(h) {
          messages.push({ role: h.role, content: h.content });
        });
        messages.push({
          role: 'user',
          content: [
            { type: 'text', text: task },
            { type: 'image_url', image_url: { url: imageUrl, detail: 'high' } }
          ]
        });
      }

      // Call Volcengine API
      const apiResponse = await fetch(ARK_BASE_URL + '/chat/completions', {
        method: 'POST',
        headers: {
          'Authorization': 'Bearer ' + ARK_API_KEY,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          model: ARK_MODEL,
          messages: messages,
          temperature: 0,
          max_tokens: fastNavigation ? 80 : 160,
          thinking: { type: 'disabled' } // disable thinking for speed
        })
      });

      const apiData = await apiResponse.json();

      if (apiData.error) {
        sendJson(res, apiResponse.status || 502, {
          ok: false,
          error: apiData.error.message || 'ARK API error',
          code: apiData.error.code
        });
        return;
      }

      const rawContent = apiData.choices && apiData.choices[0] && apiData.choices[0].message
        ? apiData.choices[0].message.content
        : '';

      // Parse thought and action from response
      let thought = '';
      let action = '';
      let actionType = '';
      let point = null;

      // Parse thought: support both standard "Thought: ..." format and direct output
      const thoughtMatch = rawContent.match(/Thought:\s*([\s\S]*?)(?=\nAction:|$)/);
      if (thoughtMatch) {
        thought = thoughtMatch[1].trim();
      } else if (rawContent.indexOf('Action:') > 0) {
        // No "Thought:" prefix — treat everything before "Action:" as thought
        thought = rawContent.split('Action:')[0].trim();
      } else {
        thought = rawContent.trim();
      }
      if (fastNavigation) {
        thought = normalizeFastNavigationThought(thought);
      }

      const actionMatch = rawContent.match(/Action:\s*(.+)/);
      if (actionMatch) action = actionMatch[1].trim();

      // Parse action type and coordinates
      if (action) {
        if (action.startsWith('click')) {
          actionType = 'click';
          const pointMatch = action.match(/<point>(\d+)\s+(\d+)<\/point>/);
          if (pointMatch) {
            point = { x: parseInt(pointMatch[1]), y: parseInt(pointMatch[2]) };
          }
        } else if (action.startsWith('scroll')) {
          actionType = 'scroll';
          const pointMatch = action.match(/<point>(\d+)\s+(\d+)<\/point>/);
          const dirMatch = action.match(/direction='(\w+)'/);
          if (pointMatch) point = { x: parseInt(pointMatch[1]), y: parseInt(pointMatch[2]) };
        } else if (action.startsWith('type')) {
          actionType = 'type';
          const contentMatch = action.match(/content='([^']*)'/);
          if (contentMatch) point = { text: contentMatch[1] };
        } else if (action.startsWith('long_press')) {
          actionType = 'long_press';
          const pointMatch = action.match(/<point>(\d+)\s+(\d+)<\/point>/);
          if (pointMatch) point = { x: parseInt(pointMatch[1]), y: parseInt(pointMatch[2]) };
        } else if (action.startsWith('press_back')) {
          actionType = 'press_back';
        } else if (action.startsWith('press_home')) {
          actionType = 'press_home';
        } else if (action.startsWith('open_app')) {
          actionType = 'open_app';
          const appMatch = action.match(/app_name='([^']*)'/);
          if (appMatch) point = { app_name: appMatch[1] };
        } else if (action.startsWith('finished')) {
          actionType = 'finished';
          const contentMatch = action.match(/content='([^']*)'/);
          if (contentMatch) point = { text: contentMatch[1] };
        }
      }

      const result = {
        ok: true,
        raw: rawContent,
        thought: thought,
        action: action,
        action_type: actionType,
        point: point,
        page_name: extractThoughtField(
          thought,
          "页面名",
          ["操作", "关键文字", "金额"]
        ) || extractThoughtField(
          thought,
          "页面",
          ["操作", "关键文字", "金额"]
        ),
        ocr_texts: ocrTexts,
        ocr_items: ocrEvidence.items,
        amounts: amounts,
        confidence: ocrTexts.length > 0 ? 0.9 : 0.7,
        image_width: imageWidth,
        image_height: imageHeight,
        usage: apiData.usage || null
      };
      result.page_key = stablePageKey(result.page_name, ocrTexts);

      // Save to cache and update rate limit timestamp
      setCachedResult(cacheKey, result);
      lastApiCallTime = Date.now();

      sendJson(res, 200, result);

    } catch (error) {
      sendJson(res, 500, { ok: false, error: String(error.message || error) });
    }
    return;
  }

  sendJson(res, 404, { ok: false, error: "not found" });
});

if (require.main === module) {
  setInterval(processEvidence, 60000).unref();
  processEvidence();
  server.listen(PORT, "127.0.0.1", () => {
    console.log(`intermap-capture listening on 127.0.0.1:${PORT}`);
    console.log(`data dir: ${DATA_DIR}`);
  });
}

module.exports = {
  mergeTrainingPaths,
  normalizeAppKey,
  normalizeFastNavigationThought,
};
