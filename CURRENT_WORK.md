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

### 7. Real Surround validation profiles — NEXT

- Run Urban Dense and Long/Mixed routes first; use the automatic C2 records to compare
  total/provider timings, OSM request/retry/split counts, unresolved intervals, category
  counts, and process memory.
- Add Suburban, Rural, Junction-heavy, and Water/Bridge-heavy samples when available.
- Verify Review visibly reports partial coverage and Retry failed areas does not refetch
  successful intervals.

### 8. Generic PEA Assets — after real fetch validation (Milestone B1)

- Add profile-driven parsing for coordinate-bearing `DS_*` worksheets.
- Begin with `DS_Transformer` and `DS_Switch`, while using a source-neutral asset record
  that permits later worksheet types.
- Suggest nearby pole matches using distance and other evidence.
- Require user review and confirmation; never auto-confirm asset-to-pole relationships.
- Persist raw attributes, normalized essentials, source identity, and confirmed links.

Before implementing B1, validate A1–A3 with a real PEA GIS workbook and Google Earth Pro:
confirm route direction, visual pole sequence, high-offset/curve cases, Pole ID metadata,
excluded records, and regeneration after changing order/inclusion/direction.

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
