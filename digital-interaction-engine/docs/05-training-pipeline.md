# Training Pipeline

## Goal

Use the web demo's iPhone Mirroring capture as the real interaction data source.
The system observes the shared iPhone window, runs OCR, matches the current page
to a Golden Flow node, gives guidance, and stores redacted interaction events for
map growth.

## Capture Loop

1. User enters the App name.
2. User shares the iPhone Mirroring window in the browser.
3. The page captures frames from the shared window.
4. Optional crop selects only the iPhone area when the full desktop is shared.
5. The browser sends sampled frames to PaddleOCR first, with local OCR only as
   fallback.
6. If a reviewed Golden Flow exists, matching locates the current node.
7. If no reviewed node exists, the page creates an exploration node from the
   page signature and OCR layout.
8. The page estimates the visible cursor anchor from the shared stream and
   aligns it with OCR boxes when available.
9. If the operator sees an ambiguous action, icon-only target, avatar tap, or
   unclear next step, they can add a manual annotation and optionally mark the
   target position on the preview.
10. The page posts redacted events to `/intermap/api/events`.

Training mode is intentionally stricter than demo mode: it only accepts a live
iPhone Mirroring window or a cropped screen area. Uploaded recordings are useful
for presentation, but they are not accepted as training data because they do not
prove that the current user action caused the current page transition.

Training mode is taskless for now. A live session is an App exploration session:
the user can operate many features in one run, and tasks are derived later from
observed page paths and transition clusters.

Data priority is: live web training first, video-derived evidence second, and
unverified web candidates last. When sources conflict, the live training trace
wins.

## Stored Events

The server stores JSONL under:

```text
/var/www/intermap-data/training_sessions/<session_id>/events.jsonl
```

Events include:

- `session_start`
- `frame_sampled`
- `ocr_observed`
- `cursor_observed`
- `node_located` (`synthetic=true` means an exploration page node)
- `node_transition`
- `interaction_inferred`
- `manual_annotation`
- `node_unresolved`
- `ocr_error`
- `session_end`

The server does not store screenshots, recordings, or raw user accounts. OCR
texts are redacted for obvious email addresses, phone numbers, and long numeric
IDs before being written to disk.

## Server Source Of Truth

Training data is processed on the server. The main workflow should not depend on
syncing sessions back to the local project.

Server raw sessions:

```text
/var/www/intermap-data/training_sessions/
```

Server review artifacts:

```text
/var/www/intermap-data/review_queue/
```

Local sync scripts are only for backup, debugging, or offline review.

## Training Use

Captured sessions should be converted into reviewable Learned Flow candidates:

1. Group events by `session_id`.
2. Extract node transition paths from `node_transition` and `node_located`.
3. Use `node_unresolved` to find pages that the current map cannot locate.
4. Use `interaction_inferred` to propose action/target candidates.
5. Use `cursor_observed` and `cursor_target` to identify what the operator
   actually pointed at.
6. Use `manual_annotation` as high-signal human feedback for ambiguous actions,
   icon-only targets, target types, and preview positions.
7. Compare transitions with the matching Golden Flow.
8. Mark missing nodes, repeated loops, low-confidence OCR pages, and backtracks.
9. Human-review the candidate.
10. Update Golden Flow only after review.

See [07-training-handoff.md](07-training-handoff.md) for the complete handoff,
server commands, and review workflow.

The training loop is therefore not just "watch the screen." The user operates
the real app, but the system stores a structured interaction trace: app intent,
sampled frame metadata, redacted OCR text, page signature, OCR layout, located or
synthetic node, transition edge, inferred interaction, manual annotation,
cursor target, confidence, deviation, and final session summary. That trace is
what later grows the map.

This keeps V1 aligned with the project principle: navigation generates the
interaction map, and the map grows from real usage instead of manual page
enumeration.
