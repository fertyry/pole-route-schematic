# PEA GIS and Free Context Workflow

## Status

This is the approved architecture and requirements for upcoming work. It is not a claim
that the PEA workbook, pole QC, generic asset, Google Earth KML, or Overture Places features
are already implemented. See `../../CURRENT_WORK.md` for implementation order and
`../../PROJECT_CONTEXT.md` for the implemented baseline.

## Product principle

PoleRoute does not need to build every supporting tool itself. When a trustworthy free
external tool or service already solves a non-core need, integrate it behind a replaceable
boundary.

PoleRoute's core value is:

- data integration and normalization;
- deterministic geometry, matching, stationing, and ordering;
- user review and explicit confirmation;
- portable project persistence;
- CAD integration and CAD generation;
- reports and auditable metadata.

PoleRoute does not currently need to build satellite imagery, a full map/basemap engine,
an Earth viewer, or a GIS field-collection system.

## Phase A — PEA GIS workbook and Pole QC

### Target flow

```text
Import PEA GIS Data
→ Discover supported sheets
→ Read DS_Pole
→ Normalize and apply reviewable filters
→ Project/match poles to the Main Route LineString
→ Calculate Station and Offset
→ Auto-sort START to END
→ Review and manually override when necessary
→ Generate/update KML
→ Open Google Earth Pro and confirm
→ Save the approved state in .prs
```

The current generic importer reads CSV/XLSX and uses the active XLSX worksheet. Multi-sheet
discovery and PEA profiles are new work.

### Geographic ordering

Excel row order is not authoritative. A pole is a geographic point and the Main Route is
a directed LineString. For every candidate pole:

1. project the point onto the Main Route;
2. calculate `station`, the distance along the route from START;
3. calculate `offset`, the point-to-route distance;
4. sort by station;
5. assign order 1, 2, 3, ...;
6. confirm START direction or reverse the route and recalculate.

The service must be deterministic. A manual order is an explicit override and must not be
silently replaced by later auto-sorting.

### Validation evidence

One real route was approximately 5.78 km and produced 106 ordered poles. The maximum
observed offset was approximately 14.82 m at order 64 and was visually verified in Google
Earth Pro near a curve/intersection. These values are evidence, not constants or universal
limits.

### Voltage normalization and default inclusion

Preserve both the raw voltage text and optional normalized bounds:

```text
raw_voltage
voltage_min_kv
voltage_max_kv
```

The parser must tolerate V/kV, ranges, slash-separated or single values, and reasonable
case/whitespace variation. It must not depend on an exact observed string such as
`22-33 kV`.

Initial default inclusion policy:

```text
height >= 12 m OR voltage_max_kv >= 22
```

This includes 12 m low-voltage poles and shorter poles carrying at least 22 kV, while an
8 m 400/230 V pole is excluded by default. Exclusion does not mean deletion. Contradictory
or uncertain data must remain visible with warning/review state.

The voltage filter must remain extensible, initially supporting All, 22–33 kV, 69–115 kV,
at least 22 kV, and custom rules.

### Pole review UI

Use a data-manager table rather than building a map viewer now. Suggested columns:

```text
Order | Pole ID | Latitude | Longitude | Height | Raw Voltage
Normalized Voltage | Station | Offset from Route | QC Status
```

Required review actions include Move Up, Move Down, Reverse, Set/Confirm Start Direction,
Exclude, Restore Auto Sort/Re-sort, Accept/Confirm, and explicit Manual Override.

Offset is a QC warning rather than a hard exclusion. Keep thresholds in one policy/config
location. Initial tunable guidance is up to 10 m normal, 10–15 m review, and above 15 m a
stronger review.

### Google Earth Pro QC

The `Check in Google Earth` flow exports a real KML file into the project folder and opens
it with Google Earth Pro. Regeneration must reflect current Route and Pole QC data.

KML should include the Main Route and pole points with order, Pole ID, height, raw/normalized
voltage, station, and offset. Confirmed transformers, switches, and other assets may be added
later. KML is a QC artifact and Google Earth Pro is not the primary data editor; `.prs`
remains authoritative.

## Phase B — Generic PEA assets

`DS_Transformer` and `DS_Switch` are known examples, not a closed schema. Use a profile-
driven framework:

```text
Supported coordinate-bearing DS_* worksheet
→ mapping/profile
→ normalized source-neutral asset record
```

The record should preserve source sheet, source/asset ID, asset type, latitude, longitude,
raw attributes, and only necessary normalized attributes. Transformer examples include
PEANO, kVA, phase, and owner. Switch examples include Fuse Dropout, Disconnecting Switch,
Open/Close, and Feeder.

Asset-to-pole matching is advisory:

```text
Asset coordinate
→ find likely pole candidates
→ calculate distance/matching evidence
→ show automatic suggestions
→ review
→ confirm
→ persist the relationship
```

Never auto-confirm. Asset coordinates can be several metres inaccurate and multiple poles
may be plausible.

## Phase C — free surroundings and Overture Places

The goal is useful utility context, not a NOSTRA clone and not a new map viewer.

Retain existing reviewed OSM roads, sois, bridges, rivers, canals, and semantic context.
Retain supplemental Overture Buildings through the existing source-neutral provenance and
conflation pipeline.

Add Overture Places for useful landmarks such as hospitals, schools, universities, places
of worship/temples, markets, fuel stations, malls, government sites, and other important
landmarks. Filter by corridor distance, category, and importance; require review before
acceptance. Apply a stricter filter to generic shops, restaurants, and businesses. Do not
label every shop or building.

Do not add Overture Transportation now: available evidence suggests it would largely
duplicate OSM and does not justify a second road pipeline. Land cover/land use, bathymetry,
and administrative divisions are also outside the current core requirement.

## Phase D — CAD integration

After pole order and asset relationships are confirmed, reuse the existing optional Pole
Overlay, canonical physical-pole mapping, locked AutoCAD target, stable metadata, and
readback services.

Confirmed PEA data can feed overlay updates, CAD asset symbols/relationships, metadata,
station and coordinate readback, reports, and sheets. It must not rebuild Base CAD
unnecessarily, destroy manual CAD edits or accepted surroundings, replace stable identities,
or introduce a competing CAD synchronization architecture.

## Future viewer architecture

An eventual viewer may use MapLibre with OpenFreeMap as the basemap and overlay Route,
Accepted Surround, Buildings, Places, PEA Poles, and PEA Assets. OpenFreeMap would be a
viewer/basemap only—not the source of truth and not a substitute for OSM/Overture source
records. Current architecture must not prevent this later addition. Google Earth Pro remains
the main QC tool for the current phase.

## Persistence direction

Prefer additive optional `.prs` fields with safe defaults for normalized PEA pole metadata,
confirmed order, station, offset, raw and normalized voltage, filter/review state, manual
overrides, generic assets, confirmed asset-to-pole relationships, and Overture Places with
provenance.

The current project schema is version 1 and already uses backward-safe defaults in several
areas. If a future implementation truly requires a schema-version bump, stop and explain
the reason before implementing it. Generated KML is not the project database.

