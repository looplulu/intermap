# Intermap Agent Notes

Read this before changing the project.

## Current Product Direction

V1 is Continuous Task Navigation: navigation itself builds the interaction map.
The current training mode is taskless App exploration. The operator enters an
App name and freely operates the real App through iPhone Mirroring.

## Must-Read Handoff

For the live training workflow, read:

```text
digital-interaction-engine/docs/07-training-handoff.md
```

That file is the current source for:

- operator training steps;
- frontend/backend responsibilities;
- server paths and deploy commands;
- OCR box and cursor-target alignment;
- how to process review_queue data;
- how reviewed training should grow Golden Flow.

## Server Training Source Of Truth

Do not make local sync a requirement for the main training workflow.

Primary server paths:

- raw sessions: `/var/www/intermap-data/training_sessions/`
- generated review artifacts: `/var/www/intermap-data/review_queue/`
- capture service: `/var/www/intermap-capture-server/capture_server.js`
- OCR API: `/opt/intermap-api/api_server.py`
- static site: `/var/www/loop-lulu/intermap`

Local `data/live_training/` is only for backup, debugging, or offline review.

## Production URL

```text
https://loop-lulu.com/intermap/
```

## Deployment Defaults

Completed changes to the demo/training site should be deployed to production.
For the intermap subsite, replace the server directory instead of layering new
files over stale files.

## Data Priority

1. Live web training on the server.
2. Video-derived evidence.
3. Unverified web candidates.

Live training wins when sources conflict.

## GitHub Stage Backups

After each self-contained milestone, upload a source snapshot to:

```text
https://github.com/looplulu/intermap
```

Use the current version number in the backup name. Keep every milestone backup
on GitHub permanently. Never automatically delete an older snapshot branch or
tag. Recommended naming:

- branch: `snapshot/xiaolu-<version>`
- tag: `xiaolu-<version>`
- commit: `小路<version> 阶段备份`

A milestone means a verified APK version, a completed production subsite
deployment, a closed training/backend loop, or docs that unblock the next
development stage. Do not overwrite a same-version branch or tag; if a same
version already exists, bump the debug version first. Upload source, docs, and
required static assets only. Do not upload build output, APK files, raw training
videos, generated databases, local environment files, or tool caches.
