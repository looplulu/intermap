# Intermap Agent Notes

Read this before changing the project.

## Current Product Direction

As confirmed on 2026-10-31, the 1.1 Android pilot uses GUI + model reasoning for
continuous task navigation without requiring a prebuilt map. Remove accessibility
and manual training from the shipped APK. Keep the user's control over every
action, text and voice goal input, and a floating task entry. The app collects
opt-in structured feedback on the server, not continuous recordings. Inferred
observations are not observed clicks; user-confirmed completion is
`user_report_only`, never automatic verified-map publication. Preserve all legacy
training data. Current implementation, APIs and limitations are documented in
`digital-interaction-engine/docs/14-consumer-pilot-1.1.md`.

As confirmed on 2026-09-10, Xiaolu is a commercial product for middle-aged and
older smartphone users in China. Competition and charity positioning no longer
determine scope, success metrics, or pricing.

The product provides continuous spoken, step-by-step navigation while the user
retains control of every action. Both text and voice goal input are required;
text is a first-class entry and correction method for dialect recognition errors.
Do not make voice recognition or automatic phone operation a prerequisite.
Visual recognition remains the primary perception path. Reviewed maps may add
conditional evidence later; the 1.1 pilot does not query them in its main path.
GUI reasoning locates the current state and visible target. Any future map
retrieval must match state and environment conditions.
As confirmed on 2026-11-01, Android navigation accepts general goals across apps
and system pages, not just Douyin or refunds. Do not use app-specific examples in
generic entry/confirmation UI. This does not claim every app/version is verified.
Automatic guidance on the same stable page must wait for speech completion;
as confirmed on 2026-11-07, leave four seconds of silence after audio completion
before one automatic reminder. Do not replay immediately when the model rephrases
the same page. Do not repeat stale guidance while a new frame is being analyzed.
Only a changed page with changed guidance
may interrupt. Explicit user pause/stop/repeat remains under user control.
Black capture enters recovery without cancelling MediaProjection. The supplied
vivo screenshots show Screen Sharing Protection > Privacy App Protection;
only guide this optional control, not all privacy switches. Never infer its
enabled state from black pixels or promise this overrides app-level protection.

Systematic real-device collection and navigation should both produce reviewable
map evidence. Record app/OS versions, device/display context, before/after state,
observed action and outcome. Preserve observed actions separately from model
suggestions; inferred variants need review before map publication. Android
GUI/accessibility learning and iPhone Mirroring data remain legacy evidence,
separate from the new consumer feedback collection. Pricing and payer segments are
unvalidated hypotheses; do not assume core navigation must be free.

The current product definition is in
`digital-interaction-engine/docs/00-project-context.md`.

## Must-Read Handoff

For the current Android pilot, read `digital-interaction-engine/docs/14-consumer-pilot-1.1.md`
and `App/README.md` first. Consumer feedback is stored in
`/var/www/intermap-data/consumer_feedback_v1/`, independently of older collections.
`POST /intermap/api/consumer/review` requires the existing training password;
the public app never receives that password or model API keys.
`ARK_API_KEY` is required on the capture service; `ARK_MODEL` optionally overrides
the legacy visual model. As of 2026-11-07, `CONSUMER_VISION_PROVIDER=deepseek`
selects `deepseek-flash` as the consumer visual main path; `DEEPSEEK_API_KEY`
is loaded from `/etc/intermap-deepseek.env` (600) via a systemd drop-in.
Never commit this file. Official API version currently maps to V4.1-Flash-1017.
Synthetic UI tests passed after explicitly correcting privacy-switch semantics;
this is not real-device or all-app accuracy verification, nor a subsecond guarantee.
`TRAIN_PASSWORD` is required for protected review; production preserves the existing
password in `/etc/intermap-consumer-auth.env` (mode 600), loaded by a systemd drop-in.
Do not commit this file or restore a hardcoded password default.

For the retained legacy web training workflow, read:

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

## Third-Party Package Analysis Storage

As confirmed on 2026-10-25, download and analyze third-party app packages on the
local computer only. The server has limited capacity and must not retain APK,
APKS, XAPK or IPA inputs. Keep local packages only while their analysis is in
progress; delete them after the required evidence has been verified and saved.
This cleanup policy does not apply to Xiaolu's own release APKs.
Process one app at a time by default so a whole batch of binaries does not
accumulate locally before analysis.

Retain compact derived nodes, edges, flow diagrams, unresolved gaps and source
records on the server under `package_static/<platform>/<app>/<version>/`.
Record the source URL, collection time, package/version, signing identity and
hash even after the input binary is deleted. Keep `apk_static` evidence separate
from real training data and `pending_review` until checked on a real device.
Do not upload decompiled trees or temporary analysis caches to the server.

Obtain the user's approval of a new app shortlist before acquiring or analyzing
that batch. A proposed app is not an approved collection target.

## Current Collection Scope

Scope decisions confirmed on 2026-10-25: exclude banking apps, China Mobile,
China Unicom, China Telecom, public-service apps and electricity-service apps
from the upcoming collection batch. Exclude railway 12306 and SF Express.
The approved Android batch is WeChat, Douyin, Kuaishou, Taobao, Pinduoduo, JD,
Meituan, Meituan Waimai, Taobao Flash, Amap, Baidu Maps, Didi, Ctrip and Cainiao.
Ctrip replaces 12306 and is listed once. Reuse the verified Douyin sample's
existing analysis rather than acquiring that same binary again.

Later on 2026-10-25, the user chose to retain only the eight completed results:
WeChat, Douyin, Amap, Baidu Maps, Taobao Flash, Cainiao, Pinduoduo and Meituan
Waimai. Taobao, Kuaishou, JD, Meituan, Didi and Ctrip acquisition is deferred.
Do not retry those six automatically; wait for a new user request.

Novel, long-video and short-drama apps, including Hongguo, are still under
discussion. Do not treat their mention as approval to download or reverse
engineer them. Prioritize concrete tasks where target users actually need help,
not app popularity or exhaustive feature coverage. Payment-app scope has not
been confirmed by excluding banking apps; do not silently extend or revoke it.

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
