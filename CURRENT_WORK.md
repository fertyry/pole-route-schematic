# PoleRoute Schematic — Current Work

> Short-lived execution memory for the next implementation milestones.
> Read `PROJECT_CONTEXT.md`, `AGENTS.md`, and the linked architecture documents before
> changing code. GitHub `main` is the source of truth. Move durable decisions to
> `PROJECT_CONTEXT.md`; update this file as milestones finish.

## Current objective

Build a reviewed PEA GIS data pipeline and useful free geographic context without
replacing the geometry, persistence, or CAD foundations already implemented.

This document separates completed foundations from the next planned milestone.

## Next Implementation

### 1. PEA GIS Workbook Import — COMPLETE (Milestone A1)

- Discover supported coordinate-bearing worksheets in a multi-sheet PEA GIS workbook.
- Implement `DS_Pole` as the first profile without locking the design to that sheet.
- Preserve source worksheet, raw values, raw voltage text, and stable source identity.
- Parse voltage ranges and units into optional `voltage_min_kv` / `voltage_max_kv`.
- Apply a reviewable default inclusion policy: height at least 12 m **or** maximum
  voltage at least 22 kV.
- Never silently delete excluded, contradictory, or unparseable records.
- Extend `.prs` only with additive, backward-safe fields unless a schema change is first
  justified and approved.

Implemented foundation:

- Multi-sheet workbook discovery lists every sheet and recognizes `DS_Pole` even when it
  is not the active worksheet.
- Unsupported `DS_*` worksheets remain visible as discovery results for later profiles.
- `DS_Pole` rows retain source identity, worksheet/row audit data, raw attributes,
  normalized height/voltage, default inclusion, and QC warnings.
- The generic Excel/CSV pole importer remains a separate unchanged workflow.
- `.prs` schema v1 stores optional `pea_poles`; older projects load it as an empty list.

### 2. Pole QC / Ordering — COMPLETE (Milestone A2)

- Project each geographic pole point onto the confirmed Main Route.
- Calculate station from START and offset from the route; sort by station rather than
  Excel row order.
- Confirm or reverse route direction before accepting the order.
- Provide table-based QC with explicit Move Up, Move Down, Reverse, Exclude, Restore Auto
  Sort, and Accept actions.
- Preserve manual ordering as explicit state; auto-sort must never overwrite it silently.
- Treat offset thresholds as tunable warnings, initially: up to 10 m normal, 10–15 m
  review, above 15 m stronger review.
- Project every valid PEA record onto exactly one authoritative Main Route using the
  existing metric projection infrastructure.
- Persist proposed/confirmed order, route-direction choice, inclusion state, manual
  override, station, route offset, projected point, and composed QC reasons additively.
- Keep excluded records reviewable; only confirmed included records become the active
  ordered pole overlay.
- Block route-based review when there is no Main Route or more than one Main Route rather
  than inventing or concatenating an alignment.

### 3. Google Earth Pro QC — COMPLETE (Milestone A3)

- Generate a persistent deterministic `<project>_PEA_QC.kml` beside the saved `.prs`;
  `.prs`, not KML, remains the source of truth.
- Include the effective Main Route direction, START/END, and proposed or confirmed pole
  points with Pole ID, height, voltage, station, offset, order, inclusion, manual-override,
  and QC metadata.
- Preserve A2's exact reviewed order, keep excluded poles visible for audit, and distinguish
  Normal, Review, Strong review, and Excluded records with deterministic KML styles.
- `Check in Google Earth` regenerates the same artifact atomically and opens it through the
  Windows `.kml` file association. An unsaved project must be saved first, and launch failure
  leaves the generated KML intact for manual opening.

### 4. Surround Reliability + Performance — COMPLETE (Milestone C0)

- Keep efficient 3 km primary OSM intervals and adaptively subdivide only retryable
  failures down to the bounded policy minimum.
- Persist final provider coverage and expose COMPLETE/PARTIAL/FAILED state in Review.
- `Retry failed areas` reuses successful candidates and requests only unresolved intervals;
  `Refresh surroundings` remains an intentional full new snapshot.
- Record provider request/retry/split, timing, cache, candidate, conflation, and review
  preparation metrics for real-route diagnosis.
- Keep providers sequential in the existing single background worker for predictable Qt
  ownership and responsible public-provider load; bounded cross-provider concurrency may be
  reconsidered only with measured evidence.

### 5. Overture Places — COMPLETE (Milestone C1)

- Add source-neutral high-value landmarks with stable Overture identity, release/source
  provenance, Thai-first names, and centralized tier/distance filtering.
- Tier A covers hospitals, education, worship, and government/public facilities; Tier B
  covers markets, fuel, malls, stadium/sports, and major attractions; Tier C generic
  businesses require close distance plus real high-confidence source data and are never
  selected as recommended automatically.
- Provider failures remain isolated and structured coverage/metrics support retrying only
  failed Places intervals. Overture Transportation and broad consumer-POI clutter remain
  excluded.

### 6. Fetch Benchmark / Diagnostics Log — COMPLETE (Milestone C2)

- Automatically record every completed Refresh surroundings and Retry failed areas network
  operation in a project-local, append-friendly UTF-8 JSONL history outside `.prs`.
- Capture canonical provider metrics, final structured coverage and unresolved intervals,
  candidate category inventory, elapsed time, and lightweight Windows process RSS/peak RSS.
- Keep the newest 200 runs, tolerate malformed interrupted lines, and keep diagnostic write
  failures non-fatal to candidates and Accepted Surroundings.
- Provide Data → Diagnostics → View Fetch Diagnostics for a compact summary and safe access
  to the log file/folder. Review surroundings creates no record because it performs no
  network fetch.

### 7. Real Surround validation profiles — COMPLETE for Urban Dense and Long/Mixed

- Run Urban Dense and Long/Mixed routes first; use the automatic C2 records to compare
  total/provider timings, OSM request/retry/split counts, unresolved intervals, category
  counts, and process memory.
- Add Suburban, Rural, Junction-heavy, and Water/Bridge-heavy samples when available.
- Verify Review visibly reports partial coverage and Retry failed areas does not refetch
  successful intervals.

Urban Dense and Long/Mixed have real evidence in the project history. Suburban, Rural,
Junction-heavy, and Water/Bridge-heavy remain optional future coverage profiles rather than
blocking B1/B1.1.

### 8. Generic PEA Assets — COMPLETE (Milestone B1)

- Profile-driven parsing recognizes `DS_Transformer` and `DS_Switch`; unsupported `DS_*`
  sheets remain visible for later profiles.
- Source-neutral `PEAAsset` records retain raw attributes, audit row, optional normalized
  values, coordinate QC, and source-ID-based stable identity with a deterministic content
  fingerprint fallback when the source ID is absent.
- Asset-to-pole matching is deterministic and proposal-only. It keeps multiple candidates,
  distinguishes unmatched/suggested/ambiguous/confirmed states, and never auto-confirms.
- Excluded A2 poles remain visible as audit/manual candidates but are not silently suggested.
- Manual confirmations survive ordinary recalculation and stable reimport. Missing source
  assets remain auditable rather than being deleted.
- `.prs` schema v1 stores assets, candidates, and explicit review state additively. Old
  projects load empty collections.
- No asset CAD symbols or synchronization are part of B1.

No local workbook containing real `DS_Transformer` / `DS_Switch` data was available during
B1 implementation. Real header coverage, counts, distance distributions, ambiguity, reopen,
and reimport must therefore be validated separately before treating the profiles as complete
field evidence.

### 8A. Real PEA Asset Validation — COMPLETE (Milestone B1.1)

- Both B003 workbooks were validated independently through the normal MainWindow import path.
- Real PEA GIS aliases were added for pole TAG, transformer PEANO, switch equipment code,
  rating, phase, subtype, status, and feeder fields while all raw attributes remain available.
- Conductor and Meter sheets are explicitly classified as intentionally excluded; they do not
  create point assets or enter matching/review counts.
- Exact source coordinates remain unchanged. Route projections and same/opposite/uncertain
  side evidence are derived separately; `POLE_OFFSET` is never a coordinate correction.
- The 0.5 m route-centerline dead band and persisted side evidence do not affect ranking or
  confirmation. All B003 nearest candidates were same-side, so the evidence is useful for
  review but did not justify a ranking rule.
- The initial 5/15/50 m distance policy remains unchanged. Four real switches between roughly
  15 and 45 m remain unmatched instead of widening policy merely to increase match rate.
- Separate local projects passed manual confirmation, alternate-candidate override,
  save/reopen, same-workbook reimport, no-duplicate, and missing-source audit checks.

### 8B. PEA Asset Visual QC — COMPLETE (Milestone B2)

- `Check PEA Assets in Google Earth` atomically regenerates a deterministic
  `<project>_PEA_ASSET_QC.kml` beside the saved `.prs` and opens it through the Windows KML
  association shared with A3.
- The KML is a read-only, disposable QC view of the effective Main Route, START/END, reviewed
  poles, Transformer/Switch source points, current match state, canonical distance/side
  evidence, and candidate/confirmed relationship lines. It never recomputes or confirms a
  match and never uses projected/CAD/`POLE_OFFSET` coordinates for geographic points.
- B003 A/B projects generated successfully. A exposed confirmed, suggested, ambiguous, and
  unmatched evidence (including weak far-switch links); B exposed its three reviewed assets.
  Google Earth loaded both artifacts and aligned their route/pole/asset overlays at route
  overview. Fine-grained field acceptance remains a user QC decision, not an automated claim.

### 8C. Recommended next milestone — B3 Confirmed PEA Asset CAD Integration

- Consume only reviewed/confirmed Transformer/Switch relationships.
- Reuse canonical physical-pole identity, managed optional Pole Overlay, and locked AutoCAD
  target without rebuilding Base CAD.
- Do not start B3 automatically; B2.1 visual refinement remains appropriate if field review
  finds label/style usability problems.

### 9. Overture Places design notes

- Reuse the existing source-neutral context/provenance architecture.
- Add useful landmarks such as hospitals, schools, universities, places of worship,
  markets, fuel stations, malls, government sites, and important landmarks.
- Filter by route corridor, category, and importance, with review before acceptance.
- Apply stricter filtering to generic shops/restaurants so CAD output does not become
  cluttered.
- Keep existing OSM roads/sois/bridges/water and supplemental Overture Buildings.
- Do not add Overture Transportation in this phase.

### 10. Later CAD integration of confirmed PEA data

- Reuse canonical physical-pole IDs, optional Pole Overlay, locked AutoCAD connection,
  metadata, and readback services.
- Update confirmed poles/assets without rebuilding Base CAD or destroying manual edits
  and accepted surroundings.
- Carry confirmed stationing, coordinates, PEA asset relationships, and stable identity
  into CAD metadata, symbols, reports, and the later sheet workflow.
- Do not create a competing CAD synchronization architecture.

## Validation evidence, not product constants

A real validation route was approximately 5.78 km with 106 ordered poles. Its largest
observed offset was approximately 14.82 m at order 64 and was visually checked in Google
Earth Pro near a curve/intersection. These values demonstrate the workflow only. Never
hard-code them in production logic, UI, tests presented as general rules, or defaults.

## Explicitly deferred

- An embedded map viewer; Google Earth Pro remains the current QC tool.
- MapLibre + OpenFreeMap viewer integration.
- Overture Transportation, land cover/land use, bathymetry, or administrative divisions.
- A NOSTRA clone, satellite imagery, a full basemap engine, or a GIS field-collection system.
- Replacing the existing AutoCAD connection, Base CAD, or optional Pole Overlay architecture.
