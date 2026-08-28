# PoleRoute Schematic — Current Work

> Short-lived execution memory for the next implementation milestones.
> Read `PROJECT_CONTEXT.md`, `AGENTS.md`, and the linked architecture documents before
> changing code. GitHub `main` is the source of truth. Move durable decisions to
> `PROJECT_CONTEXT.md`; update this file as milestones finish.

## Current objective

Build a reviewed PEA GIS data pipeline and useful free geographic context without
replacing the geometry, persistence, or CAD foundations already implemented.

This document describes **planned work**, not completed features.

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

### 2. Pole QC / Ordering — NEXT (Milestone A2)

- Project each geographic pole point onto the confirmed Main Route.
- Calculate station from START and offset from the route; sort by station rather than
  Excel row order.
- Confirm or reverse route direction before accepting the order.
- Provide table-based QC with explicit Move Up, Move Down, Reverse, Exclude, Restore Auto
  Sort, and Accept actions.
- Preserve manual ordering as explicit state; auto-sort must never overwrite it silently.
- Treat offset thresholds as tunable warnings, initially: up to 10 m normal, 10–15 m
  review, above 15 m stronger review.
- Generate a persistent project-folder KML for Google Earth Pro QC. `.prs`, not KML,
  remains the source of truth.

### 3. Generic PEA Assets

- Add profile-driven parsing for coordinate-bearing `DS_*` worksheets.
- Begin with `DS_Transformer` and `DS_Switch`, while using a source-neutral asset record
  that permits later worksheet types.
- Suggest nearby pole matches using distance and other evidence.
- Require user review and confirmation; never auto-confirm asset-to-pole relationships.
- Persist raw attributes, normalized essentials, source identity, and confirmed links.

### 4. Overture Places

- Reuse the existing source-neutral context/provenance architecture.
- Add useful landmarks such as hospitals, schools, universities, places of worship,
  markets, fuel stations, malls, government sites, and important landmarks.
- Filter by route corridor, category, and importance, with review before acceptance.
- Apply stricter filtering to generic shops/restaurants so CAD output does not become
  cluttered.
- Keep existing OSM roads/sois/bridges/water and supplemental Overture Buildings.
- Do not add Overture Transportation in this phase.

### 5. Later CAD integration of confirmed PEA data

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
