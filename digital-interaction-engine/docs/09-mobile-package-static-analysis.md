# Mobile Package Static Analysis

This workflow uses mobile application packages as low-trust corroborating
evidence for the interaction map. It does not replace live training.

## Current collection status

The 2026-10-25 approved list and eight retained results are documented in
`13-approved-app-static-evidence.md`. Six acquisitions are deferred by the user;
do not automatically resume them. The inventory includes legacy entries and
must not be interpreted as blanket collection approval. `select_apps` enforces
the approved list and user deferrals.

The serial `run_approved_package_batch.py` workflow performs local extraction,
allowlisted JSON upload, remote checksum comparison and temporary-input cleanup.
The older package-lab commands described below do not provide automatic cleanup.

## Legacy inventory

The initial inventory covers:

- 微信
- 抖音
- 快手
- 小红书
- 淘宝
- 京东
- 拼多多
- 美团
- 美团外卖
- 淘宝闪购（原饿了么）

Canonical Android package names, iOS Bundle IDs, and App Store IDs live in:

```text
configs/mobile_app_inventory.json
```

## Android workflow

Storage policy confirmed on 2026-10-25: all downloads and package analysis run
locally, not on the production server. Approve the target app list with the user
before starting a new batch. Use local temporary package files and delete them
after the required evidence has been verified and saved. Do not retain input
APKs, APKS, XAPK or IPA files on either machine after analysis. This does not
apply to Xiaolu's own release APKs.

Upload only compact derived reports, candidate nodes/edges, diagrams and source
records. Group these by platform, app and version, with source `apk_static` and
status `pending_review`. Retain source URL, acquisition time, version, signer
fingerprints and file hashes; do not upload decompiled trees or per-DEX caches.

The package lab obtains current metadata and APK download links from an
authorized official app store distribution page. It then verifies:

1. distributor-provided file size and MD5;
2. ZIP/APK structure;
3. expected Android package name;
4. APK signature integrity;
5. signer certificate fingerprints;
6. SHA-256 for local provenance.

For an approved target, run the package lab locally one app at a time. The
current batch command acquires all selected inputs before analysis, so do not
use an unbounded multi-app batch as a substitute for staged local processing.
For example, for an approved Douyin run:

```bash
cd digital-interaction-engine
python scripts/mobile_package_lab.py inventory --apps douyin
python scripts/mobile_package_lab.py analyze-android --apps douyin
```

For very large multi-DEX packages or low-memory hosts, force the lighter
per-DEX scanner:

```bash
INTERMAP_USE_DEXDUMP=1 python scripts/mobile_package_lab.py analyze-android --apps douyin
```

The existing command writes downloaded APKs and JSON reports below the local
output directory (or the explicitly supplied `--output` directory):

```text
data/package_static/
```

This directory is ignored by Git. The current command does not automatically
purge APK inputs: the operator must remove them after the required analysis and
evidence checks, and must never upload them with the reports or commit them.
An analysis interrupted by an error is not a completed evidence export; retry
or explicitly abandon and clean up its temporary input.

Each Android report extracts package/version metadata, permissions, signer
identity, manifest components, resource text candidates, DEX class candidates,
asset candidates, and package structure counts. The report source is always:

```text
apk_static
```

Its status is always:

```text
pending_review
```

## iOS boundary

Public App Store IPA files use Apple FairPlay protection. This project does not
bypass that protection and does not use cracked or decrypted packages. The iOS
side therefore stores only official App Store metadata and public assets from
the Apple lookup service:

- Bundle ID;
- App Store ID and URL;
- current version and release date;
- seller and minimum OS version;
- public artwork.

Actual iOS nodes, coordinates, labels, and transitions must come from live
device or iPhone Mirroring training. Differences between iOS releases are kept
as separate environment variants rather than merged blindly.

## Promotion rule

Package evidence may propose candidate page names, components, routes, labels,
and synonyms. It cannot prove the current UI, coordinates, account state,
server-driven content, A/B experiments, WebViews, or mini-program behavior.

Promotion priority remains:

```text
live_android_accessibility
> live_android_screen
> live_web_training
> video_derived
> apk_static
> web_unverified
```

No script in this workflow writes into `data/golden_flows/`. A reviewer must
cross-check package candidates against real-device evidence before promotion.
