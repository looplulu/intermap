# Douyin APK Flow Evidence Atlas

Analysis date: 2026-10-25. This extends the 2026-09-03 package baseline in
[08-douyin-apk-static-analysis.md](08-douyin-apk-static-analysis.md).

## Scope and conclusion

The sample is the existing official Android Douyin **40.3.0 (400301)** APK,
not a newly acquired current release. Its SHA-256 was checked after copying
from the server:

```text
e4fcd60500d25e1749ce7e6733e534b770d5bbaaab4699d673fc27a6bb499f64
```

The result is a read-only evidence atlas, **not a complete application task
map**. It distinguishes component event bindings, explicit code-level launches,
route declarations, and Activity declarations. Runtime gaps are shown, not
filled with guessed navigation. No existing Golden Flow or training session
was changed.

Retention policy updated on 2026-10-25: package analysis runs locally; the input
APK is a temporary file and is deleted after the verified evidence is saved.
The server directory below retains the atlas and provenance, not the APK.

## Observed results

| Object | Result | Meaning |
| --- | ---: | --- |
| APK entries | 47,388 | Inventory, not features |
| DEX files scanned | 54 / 54 | Method-table scan and targeted instruction decoding |
| Classes / encoded methods | 506,292 / 2,261,154 | Includes bundled libraries |
| Candidate methods decoded | 5,568 | Navigation and event-reference candidates |
| Resource XML parsed | 28,991 / 28,992 | Obfuscated `r/` resources included |
| Asset JSON parsed | 1,464 / 1,467 | Explicit structured event bindings |
| Archives / Zstandard resources expanded | 25 / 7 | Nested data inspected, no program executed |
| Nested JSON parsed | 35 | No additional interaction bindings found |
| Interaction components | 603 | Components, not complete screens |
| Event bindings | 1,507 | 547 fixed event names; 960 runtime expressions |
| SmartRouter route declarations | 710 | Literal route-to-handler map entries |
| Explicit route opens / Activity launches | 592 / 24 | Code fragments, not validated user paths |
| Other route constructions | 425 | Opening was not resolved by the analysis |
| Activity / alias declarations | 1,478 | Manifest declarations, not route coverage |

The order-list resource family contains **112 bindings, including 79 runtime
event expressions**. The `to_all_tab` component explicitly binds `toAllTab`.
Product-row events and per-order refund actions remain partly runtime-driven.
These fragments do not establish a closed profile-to-refund task sequence.

Static analysis is useful for candidate inventories and route/handler skeletons.
This result does not justify replacing real-device collection with an assumption
that only minor final corrections will remain.

## Artifacts

Server source directory:

```text
/var/www/intermap-data/package_static/android/douyin/40.3.0/flow-map-20261025/
```

Local review copy, ignored by Git:

```text
data/package_static/android/douyin/40.3.0/flow-map-20261025/
  flow-evidence.json
  index.html
  dex_evidence/                 # local per-DEX caches, not required for viewing
```

Open `index.html` directly; it embeds its data and layout library and needs no
development server. It supports separate evidence layers, module grouping,
search, source inspection, SVG export, and a scan/gap inventory. The order
audit opens first. The settings code branches provide examples with both
explicit route opens and registered destinations.

## Reproduction

Use Python 3.12 and an isolated environment with
`scripts/requirements-apk-flows.txt`. Acquire Dagre 1.1.5 from its pinned package
distribution; it is an MIT-licensed diagram-layout dependency, not APK code.

```sh
python scripts/extract_apk_flows.py /path/to/douyin-40.3.0.apk /path/to/output
python scripts/render_apk_flow_report.py /path/to/output/flow-evidence.json \
  /path/to/dagre.min.js /path/to/output/index.html
python -m unittest discover -s scripts -p test_extract_apk_flows.py
```

`check_apk_flow_report.cjs` uses Playwright from `NODE_PATH`. Set
`PLAYWRIGHT_CHROMIUM_EXECUTABLE` when using an existing browser executable.
The 2026-10-25 browser check traversed all 603 component diagrams and checked
label bounds, evidence expansion, grouping, search, export, and desktop layout.

## Boundaries and next validation

- The extractor follows literal values within straight-line code segments and
  clears tracked values at branch, switch and exception-handler entries. It is not whole-program control
  flow, cross-method dataflow, reflection, or callback resolution.
- Some UI logic lives in binary Lynx/script/native programs or server-delivered
  schemas. Expanding an archive does not mean decompiling its programs.
- Runtime state, experiments, permissions, authentication, target order choice,
  button visibility and live coordinates remain unverified.
- Filename and class-name module grouping is organizational, not an app ontology.
- The atlas is `apk_static` / `pending_review`. Never publish these edges into
  Golden Flow merely because a route or class exists.
- Validate specific edges with before/action/after real-device evidence, keeping
  observed actions separate from these static suggestions. Review all affected
  state and environment conditions before map promotion.
