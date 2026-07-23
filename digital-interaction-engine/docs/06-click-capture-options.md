# Click Capture Options

The web demo observes the shared iPhone Mirroring image, OCR text, OCR layout,
visible cursor movement, and page transitions. The browser still cannot read
system-level mouse-down events in another Mac window, but the visible cursor in
the shared stream is a practical operation anchor for the current demo.

## Current Approach

Use cursor-anchored transition inference:

1. Capture page snapshot A.
2. User operates iPhone Mirroring.
3. Estimate visible cursor position from frame differences.
4. Align cursor position with OCR boxes to produce `cursor_target`.
5. Capture page snapshot B.
6. Record `cursor_observed`, `node_transition`, and `interaction_inferred`.
7. Infer possible action/target from cursor target, OCR layout, manual
   annotation, and page transition.

This is enough to build the first interaction graph: pages, transitions,
unresolved screens, cursor targets, and likely action labels.

## Native Click Option A: Native Mac Collector

Best for real operation.

Required permissions:

- Screen Recording
- Accessibility

Collector responsibilities:

1. Let the user select or calibrate the iPhone Mirroring window/region.
2. Listen for global mouse-down events.
3. Convert global mouse coordinates to normalized coordinates inside the iPhone
   region.
4. Send a `click_observed` event to `/intermap/api/events`.
5. Include timestamp, frame sequence if available, normalized x/y, button, and
   selected region metadata.

Example event shape:

```json
{
  "session_id": "web_xxx",
  "event_type": "click_observed",
  "timestamp": "2026-07-08T12:00:00Z",
  "app": "taobao",
  "task": "app_exploration",
  "capture_mode": "screen",
  "frame_seq": 42,
  "payload": {
    "x_norm": 0.52,
    "y_norm": 0.81,
    "button": "left",
    "region": {"x": 120, "y": 80, "w": 390, "h": 844}
  }
}
```

A Swift helper is still the cleanest path if true mouse-down timestamps are
needed. Python or Node can also work, but usually require native dependencies for
global mouse hooks.

## Coordinate Option B: Web Preview Annotation

Simpler but less natural.

The user clicks inside the browser preview, so JavaScript can record exact
coordinates. This is useful for labeling or review, but by itself it does not
operate the iPhone. It becomes a real control surface only if paired with a
native bridge that forwards clicks to the mirrored phone/window.

## Recommendation

For the competition demo and V1 validation, use cursor-anchored transition
inference plus manual annotation first. Build the native Mac collector only if
the model needs exact mouse-down timing instead of the current visible-cursor
anchor.
