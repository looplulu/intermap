# Live Training Handoff

This document is the handoff for the next AI or engineer continuing the
Intermap training work.

## Current Goal

The project is validating a Digital Interaction Engine that grows an interaction
map from real navigation sessions.

The current training unit is not a predefined task. It is an App exploration
session:

1. The operator enters an App name.
2. The operator shares the iPhone Mirroring window in the web training page.
3. The operator freely explores the real App.
4. The system records OCR, page signatures, nodes, transitions, cursor anchors,
   manual annotations, and unresolved pages.
5. Server-side review artifacts are generated automatically.
6. Reviewed evidence is promoted into Golden Flow / interaction graph data.

Do not make the operator choose a Task during training. Tasks should be derived
later from repeated paths and transition clusters.

## Production Surfaces

- Public demo and training page:
  `https://loop-lulu.com/intermap/`
- Static site directory:
  `/var/www/loop-lulu/intermap`
- Capture/event service:
  `/var/www/intermap-capture-server/capture_server.js`
- Capture service process:
  `pm2 restart intermap-capture`
- OCR API service:
  `/opt/intermap-api/api_server.py`
- OCR API process:
  `systemctl restart intermap-api.service`
- Server training data:
  `/var/www/intermap-data/training_sessions/`
- Server review artifacts:
  `/var/www/intermap-data/review_queue/`

Server-side training data is the source of truth. Do not require training data
to sync back into the local project for the main workflow.

## Frontend Training Flow

The training page lives in:

```text
digital-interaction-demo/index.html
```

Operator steps:

1. Open `https://loop-lulu.com/intermap/`.
2. Switch to training mode.
3. Enter the App name manually, for example `淘宝`.
4. Choose the iPhone Mirroring window or a screen region containing it.
5. Start training.
6. Operate the real iPhone/App normally.
7. When an action is ambiguous, add a manual annotation:
   - mark whether it describes the previous step, next step, or current page;
   - write the action, target, and target type;
   - optionally click the preview to mark the target position.
8. End the training session.

Important behavior:

- Uploaded videos are for demo only, not trusted training.
- Training should use the live iPhone Mirroring window.
- The operator does not preselect a task.
- The browser requests cursor capture with `cursor: always`.
- Visible cursor motion in the shared stream is treated as the operation anchor.

## Event Pipeline

Frontend events are sent to:

```text
POST /intermap/api/events
```

Nginx proxies this to the capture service:

```text
http://127.0.0.1:3011/api/events
```

The capture server writes redacted JSONL:

```text
/var/www/intermap-data/training_sessions/<session_id>/events.jsonl
```

Important event types:

- `session_start`
- `frame_sampled`
- `ocr_observed`
- `cursor_observed`
- `node_located`
- `node_transition`
- `interaction_inferred`
- `manual_annotation`
- `node_unresolved`
- `ocr_error`
- `session_end`

On `session_end`, the capture service runs:

```bash
python3 /var/www/intermap-capture-server/build_live_training_flows.py \
  --sessions-dir /var/www/intermap-data/training_sessions \
  --output-dir /var/www/intermap-data/review_queue
```

The output is:

```text
/var/www/intermap-data/review_queue/<session>_<app>_app_exploration.json
/var/www/intermap-data/review_queue/<app>_app_exploration_aggregate.json
```

## OCR And Cursor Alignment

OCR API endpoint:

```text
POST /intermap/api/analyze_base64
```

Nginx proxies it to:

```text
http://127.0.0.1:18000/api/analyze_base64
```

The OCR API uses PaddleOCR and now returns both text and layout:

```json
{
  "ocr_texts": ["退款/售后"],
  "ocr_items": [
    {
      "text": "退款/售后",
      "confidence": 0.98,
      "box": {"x": 120, "y": 640, "w": 92, "h": 28},
      "box_norm": {"x": 0.33, "y": 0.76, "w": 0.25, "h": 0.03},
      "center_norm": {"x": 0.45, "y": 0.775}
    }
  ]
}
```

The frontend estimates cursor anchors from frame differences in the shared
stream and emits `cursor_observed`.

When `ocr_items[].box_norm` exists, the frontend aligns the cursor point with OCR
boxes and produces `cursor_target`:

```json
{
  "cursor_hint": {
    "x_norm": 0.83,
    "y_norm": 0.80,
    "confidence": 0.8,
    "method": "frame_diff_cursor_hint"
  },
  "cursor_target": {
    "matched_text": "更多",
    "relation": "hit",
    "evidence": "cursor_ocr_box_alignment"
  }
}
```

Treat cursor position as the real operation anchor for this demo setup because
the browser preview is a complete mapped image of the iPhone Mirroring window.
The caveat is that the current implementation estimates the cursor from pixels,
so keep `confidence` and `relation` in downstream logic.

## Manual Annotation

Manual annotations are high-value labels.

Use them when:

- the target is an icon without text;
- the target is an avatar, image, tab, or three-dot menu;
- OCR text is noisy;
- the transition is important but the system might infer the wrong action;
- the operator wants to describe the previous or next step in plain language.

The payload includes:

- timing: previous step, next step, or current page;
- action text;
- target text;
- target type;
- optional preview position;
- current node/page signature;
- OCR text and layout context.

Manual annotation should override weak inferred labels during review.

## How To Inspect A New Training Run

List recent sessions:

```bash
ssh root@loop-lulu.com \
  'find /var/www/intermap-data/training_sessions -maxdepth 2 -type f -name events.jsonl -printf "%T@ %p\n" | sort -nr | head'
```

Summarize a session:

```bash
ssh root@loop-lulu.com 'python3 - <<PY
import json, collections, pathlib
sid = "REPLACE_SESSION_ID"
p = pathlib.Path(f"/var/www/intermap-data/training_sessions/{sid}/events.jsonl")
events = [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
print("events", len(events))
print("first", events[0].get("timestamp"), events[0].get("app"), events[0].get("task"))
print("last", events[-1].get("timestamp"), events[-1].get("event_type"))
print(dict(collections.Counter(e.get("event_type") for e in events)))
PY'
```

Inspect generated review data:

```bash
ssh root@loop-lulu.com \
  'ls -lt /var/www/intermap-data/review_queue | head'
```

Check OCR and capture health:

```bash
curl -fsS https://loop-lulu.com/intermap/api/health
curl -fsS https://loop-lulu.com/intermap/api/capture-health
```

## How To Process Training Data

After each operator session:

1. Confirm `session_end` was received.
2. Confirm the session candidate exists in server `review_queue`.
3. Open the session candidate and inspect:
   - `quality.events`
   - `quality.ocr_events`
   - `quality.located_nodes`
   - `quality.transitions`
   - `quality.cursor_observations`
   - `quality.manual_annotations`
   - `unresolved_pages`
4. Check each transition:
   - source node;
   - destination node;
   - cursor target under or near the operation anchor;
   - OCR target candidates;
   - manual annotation if present.
5. Merge repeated page signatures into stable node definitions.
6. Merge repeated transitions into action edges.
7. Use manual annotations and high-confidence cursor-target hits as primary
   evidence for action labels.
8. Use OCR-only inferred targets as secondary evidence.
9. Keep unresolved pages in the review queue until they can be named or merged.
10. Promote reviewed nodes/transitions into Golden Flow only after evidence is
    strong enough.

Do not automatically overwrite Golden Flow from a single noisy session.

## What "Training The Model" Means Here

The immediate target is not to fine-tune a large language model.

The first training target is the interaction map:

- page signatures become candidate nodes;
- repeated OCR/layout patterns stabilize node identities;
- cursor anchors plus OCR boxes identify action targets;
- node transitions become edges;
- manual annotations provide high-confidence labels;
- repeated paths become task candidates.

Only after enough reviewed sessions exist should a model-training dataset be
exported.

Recommended supervised examples:

```json
{
  "app": "淘宝",
  "page_signature": "abc123",
  "ocr_items": [{"text": "退款/售后", "box_norm": {"x": 0.4, "y": 0.7, "w": 0.2, "h": 0.04}}],
  "cursor_hint": {"x_norm": 0.48, "y_norm": 0.72},
  "label": {
    "node_name": "我的订单",
    "action": "点击退款/售后",
    "target_text": "退款/售后",
    "target_type": "text",
    "next_node": "售后列表"
  }
}
```

Useful model tasks later:

- node classification from OCR/layout;
- target classification from cursor + OCR boxes;
- transition/action labeling;
- task path discovery from repeated transition clusters;
- deviation detection when the path differs from reviewed Golden Flow.

For now, improve the server review artifacts and promotion workflow before
fine-tuning any model.

## Current Known State

As of 2026-07-08:

- Live training data is stored on the server.
- Server-side review queue generation is automatic on `session_end`.
- PaddleOCR returns OCR boxes through `ocr_items`.
- Frontend aligns cursor anchors with OCR boxes as `cursor_target`.
- Two Taobao exploration sessions exist on the server:
  - `web_mrc1j9zu_9255jg`
  - `web_mrc1vjtx_x4kz2a`
- The second session confirmed cursor observations were captured.

## Next Work

Highest-value next steps:

1. Add a server review UI or JSON viewer for `review_queue`.
2. Improve cursor detection stability and filter non-click cursor movement.
3. Add an explicit "I clicked now" annotation button if cursor movement alone is
   too noisy.
4. Add node merge tooling for repeated page signatures.
5. Add transition review tooling that promotes verified edges into Golden Flow.
6. Export reviewed examples for later model training.
7. Keep unverified web candidates quarantined; do not let them override live
   sessions.

## Deployment Commands

Deploy frontend:

```bash
rm -rf /tmp/intermap-demo-dist && mkdir -p /tmp/intermap-demo-dist/assets
cp digital-interaction-demo/index.html /tmp/intermap-demo-dist/index.html
cp digital-interaction-demo/assets/demo-data.js /tmp/intermap-demo-dist/assets/demo-data.js
COPYFILE_DISABLE=1 tar -C /tmp/intermap-demo-dist -cf - . | \
  ssh root@loop-lulu.com \
  'rm -rf /var/www/loop-lulu/intermap && mkdir -p /var/www/loop-lulu/intermap && tar -C /var/www/loop-lulu/intermap -xf - && chown -R root:root /var/www/loop-lulu/intermap'
```

Deploy capture server / builder:

```bash
scp digital-interaction-engine/server/capture_server.js \
  digital-interaction-engine/scripts/build_live_training_flows.py \
  root@loop-lulu.com:/var/www/intermap-capture-server/
ssh root@loop-lulu.com \
  'chmod +x /var/www/intermap-capture-server/build_live_training_flows.py && pm2 restart intermap-capture'
```

Deploy OCR API:

```bash
scp digital-interaction-engine/server/api_server.py \
  root@loop-lulu.com:/opt/intermap-api/api_server.py
ssh root@loop-lulu.com 'systemctl restart intermap-api.service'
```
