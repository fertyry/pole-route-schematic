# PoleRoute Schematic — Project Context

> Canonical handoff document for Codex/ChatGPT sessions and development computers.
> Read this file, `README.md`, `CHANGELOG.md`, `git status`, and recent commits before
> discussing or changing the project. Update it when architecture, workflow, or a
> product invariant materially changes.

## Project memory contract

GitHub `main` is the source of truth shared by development computers and ChatGPT/Codex
sessions. Use these documents together:

- [`PROJECT_CONTEXT.md`](PROJECT_CONTEXT.md) — durable architecture, implemented baseline,
  approved workflows, decisions, and invariants.
- [`CURRENT_WORK.md`](CURRENT_WORK.md) — short-lived Next Implementation and milestone order.
- [`AGENTS.md`](AGENTS.md) — repository rules for Codex and other AI agents.
- [`docs/architecture/PEA_GIS_FREE_CONTEXT_WORKFLOW.md`](docs/architecture/PEA_GIS_FREE_CONTEXT_WORKFLOW.md)
  — approved PEA GIS, Pole QC, asset, free-context, Google Earth QC, and later CAD design.

Documentation can describe planned work. Inspect source and tests before claiming that a
documented feature is implemented.

## Repository state at this handoff

- Repository: `https://github.com/fertyry/pole-route-schematic`
- Primary branch: `main`
- Last main baseline verified on 2026-08-28: `769975d`
- Baseline subject: `Document AutoCAD overlay and surroundings workflow`
- Python package version: `0.1.0.dev0`
- Project file schema: `.prs` version `1`
- Primary environment: Windows and Python 3.13
- Local repository: `D:\Dev\pole-route-schematic`

Untracked local artifacts such as `ErrorReports/`, screenshots, generated DXF/PDF/XLSX,
and user test projects are not source code. Do not add, remove, or commit them without
the owner's explicit approval.

## Product purpose

PoleRoute Schematic turns geographic route and utility-pole data into editable schematic
drawings. It accepts KML/KMZ LineStrings and Excel/CSV pole records, builds metric road
geometry, adds reviewed OpenStreetMap surroundings, supports editable schematic/CAD
workflows, and produces Excel or DXF output.

The final drawing is intentionally **not on scale**, but route order, relative station,
junctions, sois, structures, pole ownership, and sheet continuity must remain meaningful.

## External-tool product principle

PoleRoute does not need to create every supporting capability itself. When a trustworthy,
free external tool or service already satisfies a non-core need, use it through a clear,
replaceable provider boundary.

PoleRoute's core value is data integration, geometry, matching, stationing/ordering,
review, project persistence, CAD integration/generation, and reports. Satellite imagery,
a full map/basemap engine, an Earth viewer, and a GIS field-collection system are not
current core products. Google Earth Pro remains the present Pole QC viewer; a future
MapLibre + OpenFreeMap viewer remains possible without making the basemap authoritative.

## Technology

- Python 3.11+; Python 3.13 is used on the main computer
- PySide6 and Qt Graphics View
- Shapely and pyproj
- openpyxl plus Windows COM (`pywin32`) for editable Excel objects
- ezdxf for metric Model Space and Paper Space output
- XML/ZIP parsing for KML/KMZ
- pytest and pytest-qt
- PyInstaller is planned for Windows packaging

```powershell
.\.venv\Scripts\Activate.ps1
python -m pole_route
python -m pytest
```

## Architecture

```text
src/pole_route/
├── domain/       Routes, poles, context, schematic, and block concepts
├── importers/    KML/KMZ, Excel/CSV, OpenStreetMap, edited-DXF inspection
├── geometry/     Projection, road networks, junctions, schematic layout
├── ui/           Qt windows, dialogs, renderers, commands, background worker
├── exporters/    Editable Excel and DXF/CAD output
├── project/      Portable .prs serialization and Qt scene restoration
├── main.py       QApplication startup
└── __main__.py   `python -m pole_route` entry point
```

### Dependency rules

- `domain` is the data vocabulary and should not depend on Qt UI behavior.
- `importers` turn external data into domain objects or validated snapshots.
- `geometry` consumes domain objects and returns deterministic geometric/domain results.
- `ui` owns confirmations, workflow state, Qt scenes, and user interaction.
- `exporters` consume approved geometry/snapshots/settings. Export previews must not
  mutate their source scene or project.
- `project/storage.py` is the `.prs` portability boundary. Persistent changes require
  backward-safe defaults or an explicit schema migration/version decision.

### Stable identities

- A pole record is a work record; it is not always one physical pole.
- `same_pole_groups` represent one physical pole with multiple work items/accessories.
- `transformer_rack_groups` represent a two-leg transformer rack.
- Installed quantity does not determine physical-pole count.
- CAD pole identity is stored in block attributes, never inferred from visible text or XY.

## Current implemented workflow (legacy baseline before the next workflow change)

1. Create/open a portable `.prs` project and enter project information.
2. Import one or more KML/KMZ LineStrings.
3. Classify each selected line as Main route, Road/Soi, Cross road/Large intersection,
   or T-junction; set width, pole-line creation, offset, and Reverse.
4. Optionally fetch OpenStreetMap surroundings asynchronously and review candidates.
5. Import Excel/CSV poles through a mandatory column-mapping preview.
6. Review duplicate/near-duplicate coordinates and classify their physical meaning.
7. Build projected metric road geometry and pole placements.
8. Generate/edit a non-scale Qt schematic or export metric CAD.
9. Save routes, poles, context, physical groups, scene, settings, and edited-DXF data to `.prs`.
10. Export editable multi-sheet Excel, or edit the exported CAD in AutoCAD/Map 3D.
11. Import edited DXF, validate stable IDs and sheet markers, confirm review, then use
    `Create CAD sheets` to rebuild A4 landscape Paper Space layouts.

This list records the legacy implemented sequence through commit `014e18a`; it is not the
authoritative target workflow. In particular, its placement of Import Pole before Build is
superseded by **Pole Import is Optional** below. The approved AutoCAD execution architecture
also supersedes the old assumption that sheet breaks and Paper Space layouts should be
finalized before the user finishes editing the CAD source drawing.

## Pole Import is Optional

Import Pole is no longer a mandatory step or a gate before building and generating base
output. PoleRoute must support a Base Map / Base CAD workflow without pole data:

```text
Import / Read Route
→ Fetch Surround
→ Build Base
→ Generate Base CAD
→ Export DXF
```

Base CAD may contain every accepted source that is available before poles are supplied,
including:

- Main Route
- Roads / Sois
- Buildings
- River / Canal
- Bridges
- POI / Fuel / Shop
- other reviewed Surround context

The absence of Pole data must not block Build Base or Generate Base CAD. Existing source
code may not yet implement this decision completely; the decision is nevertheless the
authoritative target workflow.

## Optional Pole Overlay Workflow

Pole data may be supplied later and applied as a non-destructive overlay:

```text
Import Pole
→ Create or use POLE_OFFSET
→ Project / Snap pole positions onto POLE_OFFSET
→ Calculate Station / Position / Latitude / Longitude
→ Overlay / Update pole objects in the existing CAD drawing
```

Making pole import optional does not change the pole-placement rules:

- Main Route remains the reference alignment.
- Create the offset from the pole side and the existing offset rules.
- Every projected pole must lie on `POLE_OFFSET`.
- Do not alter projection, offset, stationing, or placement logic merely because poles can
  arrive after Base CAD generation.
- Applying or updating the Pole Overlay must not damage, replace, or discard the Base Map /
  Base CAD and its reviewed surroundings.

## CAD File Workflow

PoleRoute creates DXF as its file interchange format. The normal AutoCAD handoff is:

```text
PoleRoute creates DXF
→ Open DXF in AutoCAD
→ Save As DWG
→ Use DWG as the native working/editing file in AutoCAD
```

For a file-based handoff back into PoleRoute:

```text
DWG
→ Save As DXF in AutoCAD
→ Import Edited DXF into PoleRoute
→ Continue the required PoleRoute workflow
```

The rule is deliberately simple:

- **DXF = interchange format for input to and output from PoleRoute.**
- **DWG = AutoCAD's native working/editing format.**

PoleRoute does not need to read DWG directly in the file-based workflow. DWG is the
recommended AutoCAD working format, not a mandatory PoleRoute project format.

## Existing DWG Workflow

For a DWG received from another person:

- Open the DWG in AutoCAD.
- A future Connect AutoCAD workflow may Read/Register its Main Route directly; converting
  to DXF merely to select the route in a connected AutoCAD session is unnecessary.
- To use the current file-based import path, Save As DXF in AutoCAD first and import that
  DXF into PoleRoute.

## Route from CAD without Lat/Long

When Main Route comes from an AutoCAD polyline/DWG rather than a georeferenced KML or
LineString, the user must supply both endpoint correspondences:

```text
CAD Start X,Y ↔ Start Latitude/Longitude
CAD End X,Y   ↔ End Latitude/Longitude
```

PoleRoute uses these two pairs to derive the route transformation. Only after that
transformation is validated may it fetch OSM/Overture data, calculate pole latitude and
longitude, or run other world-coordinate workflows.

- Never guess missing world coordinates.
- If either Start or End Latitude/Longitude is incomplete, block operations that require
  world coordinates, including Fetch Surround.
- Validate route distance, scale, and rotation before relying on the transformation.

## Connect AutoCAD Direction

The initial Connect AutoCAD foundation and optional pole-overlay readback are implemented.
The connection is explicit rather than real-time synchronization:

- If multiple drawings are open, require the user to select the target drawing.
- Lock the selected target and never follow the active AutoCAD tab automatically.
- Read and update only through explicit user actions.
- Implemented actions are `Read Route`, `Read Pole Offset`, `Update Poles`, and
  `Read Pole Positions`. `Execute Sheets` remains planned.
- Late-arriving pole data must be supportable by updating only the Pole Overlay in an
  already edited drawing, without rebuilding or destroying its Base CAD.

## Workflow superseding previous assumptions

This decision supersedes the previously mandatory sequence:

```text
Import Route
→ Fetch Surround
→ Import Pole
→ Build
→ Generate
→ Export DXF
→ Import Edited DXF
→ Create Sheet
```

Specifically, Import Pole is no longer a gate before Build/Generate. References elsewhere
in this document to DWG or CAD Master must be read consistently with the new file contract:
DWG is the recommended native AutoCAD working format, DXF remains PoleRoute's primary
interchange format, and a file-based return from AutoCAD is made by saving the DWG as DXF.

## Phase / Implementation Note

The optional-pole base workflow, canonical physical-pole mapping, locked AutoCAD connection,
and optional pole-overlay readback are implemented. Sheet Plan/Execute, Pole Report, and
the interactive two-point calibration UI for an arbitrary ungeoreferenced CAD route remain
future work.

## Phase 1 stability status

### Phase 1A — Save stability, live canvas, and working directory: COMPLETE

- Project saving after Fetch Surroundings and after Build Geometry/Structure is stable.
- Saving is read-only with respect to the live Qt scene; it does not clear, remove, or
  re-render the canvas.
- Open, Save As, route/pole import, edited-DXF import, Excel export, and DXF export use
  a shared remembered working directory without embedding local paths in portable `.prs`
  project files.

### Phase 1B — DXF Read-only investigation: RESOLVED / NO EXPORTER FIX REQUIRED

The investigation established the following:

- DXF files produced by PoleRoute open normally with `ezdxf`.
- DXF audit passes with no structural error found.
- The Windows file attribute is not Read-only.
- Moving the file from OneDrive to a local drive did not by itself eliminate the symptom.
- Opening the file from inside AutoCAD with `OPEN` works normally.
- Starting AutoCAD from the command line with the DXF path works with both `/product ACAD`
  and `/product MAP`.
- The failure occurred when double-clicking a DXF in Windows Explorer.

The confirmed root cause was the Windows/Autodesk `.dxf` file association, not the
PoleRoute DXF exporter. The confirmed fix is to associate `.dxf` files with Autodesk
AutoCAD DWG Launcher:

```text
C:\Program Files\Common Files\Autodesk Shared\AcShellEx\AcLauncher.exe
```

After changing the association to `AcLauncher.exe`, double-clicking a DXF in Explorer
opens normally and no longer reports that the file is currently in use or read-only.

Do not change `dxf_exporter.py` to address this resolved symptom unless new evidence shows
an exporter defect. If the symptom returns, check the `.dxf` file association and
`AcLauncher.exe` first. Phase 1B is closed.

## CAD working-file clarification

The approved handoff into AutoCAD is:

```text
PoleRoute
→ Export DXF
→ Open the DXF in AutoCAD
→ Save As DWG
→ Use that DWG as the recommended AutoCAD working/editing file
```

DXF remains PoleRoute's interchange format into and out of AutoCAD. AutoCAD offers Save As
DWG when saving an opened DXF, and the resulting DWG is the recommended native working file
for:

- continued saves and manual CAD editing
- Connect AutoCAD
- Read Pole Positions
- Execute
- Sheet Copies
- Layouts

For file-based return to PoleRoute, Save As DXF from that DWG and use Import Edited DXF.
Direct DWG reading is reserved for the future connected-AutoCAD workflow and is not required
for file-based interchange.

## Approved AutoCAD execution architecture (partially implemented)

### Responsibilities and CAD target

- AutoCAD is the primary CAD target. Do not add ZWCAD support in this phase.
- PoleRoute is the **calculation and control layer**: it owns identities, coordinates,
  stationing, reports, the Sheet Plan, validation, and the execution request.
- AutoCAD is the **execution and editing layer**: the user edits the CAD Master there,
  and PoleRoute directs AutoCAD to create/refresh generated sheet objects and layouts.
- AutoLISP is no longer the primary page-cutting engine. LSP remains an optional utility
  mechanism for focused CAD operations such as pole spacing.

### Connect AutoCAD contract

`Connect AutoCAD` is an explicit connection to one open drawing; it is not real-time
synchronization.

- If AutoCAD has multiple drawings open, show the list and require the user to choose.
- Lock that chosen drawing as the target for the session. `Read` and `Execute` must keep
  operating on it even if the user activates another AutoCAD tab.
- If the target drawing is closed, transition to `Disconnected`.
- Inspect PRS blocks and project metadata and warn when the chosen drawing may belong to
  another project.
- Never silently switch to or auto-select a different drawing.

The connection/session contract above is implemented. It is covered by mock/fake tests;
real AutoCAD COM validation on a user drawing is still required.

### Implemented optional pole overlay

- `Read Route` and `Read Pole Offset` read current geometry from the locked drawing.
- `Update Poles` validates the complete update plan before replacing only PoleRoute-managed
  `PRS_POLE` and `PRS_TRANSFORMER_RACK` inserts. It preserves unrelated and manually edited
  Base CAD entities and is idempotent when rerun.
- `Read Pole Positions` maps moved inserts back through stable canonical physical-pole IDs;
  it never promotes accessory work records into independent physical poles.
- Same-physical-pole rows share one continuous P Label. A transformer rack uses explicit
  Rack Pole A/B records and consumes two consecutive P Labels.
- Transformer-rack leg center-to-center spacing is exactly 3.0 m in the managed overlay.
- Exported pole/rack metadata includes the canonical physical IDs and P Labels needed for
  auditable readback.
- Two-point similarity-transform calculation and validation exist at the service layer.
  The UI does not yet collect Start/End calibration for an arbitrary ungeoreferenced drawing;
  such a route must not be treated as world-referenced until that UI is implemented.

### Approved workflow after Generate

```text
Generate CAD Master
→ Open CAD Master in AutoCAD
→ Connect AutoCAD
→ User edits the CAD Master
→ Reposition poles if necessary
→ Read Pole Positions
→ PoleRoute recalculates Station / Latitude / Longitude
→ Calculate Sheet Plan
→ Preview and adjust Sheet Plan
→ Create PRS_SHEET_BREAK from the confirmed latest pole positions
→ Execute
→ AutoCAD creates Sheet Copies in Model Space
→ Create each sheet frame
→ Create/Refresh Layouts
→ Inspect drawings
→ Publish/Plot PDF
```

`PRS_SHEET_BREAK` must therefore not become a permanent boundary before the user has
finished repositioning poles and PoleRoute has read the latest block positions.

### Sheet Plan ownership

- PoleRoute is the only owner/calculator of the Sheet Plan. AutoCAD and LSP must not
  calculate a competing plan.
- Start with a target of about 350 m of Main route per A4 Landscape sheet.
- Every boundary must be at a pole position.
- When the target distance is reached, choose the next/suitable pole while balancing
  sheet lengths as closely as practical.
- The user must preview and may adjust boundaries before Execute.
- A confirmed `PRS_SHEET_BREAK` is the contract representing the accepted Sheet Plan.

### Sheet Copies in Model Space

After Execute, keep the complete CAD Master intact and create generated copies named
Sheet 01, Sheet 02, Sheet 03, and so on, arranged as framed drawings in Model Space.

- Each Sheet Copy contains only geometry belonging to its interval.
- Pole blocks and pole labels from the previous/next interval must not appear.
- Context such as roads, buildings, canals, rivers, and bridges may retain a small margin
  outside the interval when necessary for legibility.
- Objects outside the confirmed left/right boundary poles must not leak into a sheet.
- Re-running Execute refreshes only PoleRoute-generated sheet objects and never damages
  the CAD Master or user-edited source objects.
- Generated objects require dedicated layers and/or metadata so they can be replaced safely.

### Sheet labels and plotting

- Generate a new visible Pole No. sequence `P1`, `P2`, ... for the final sheets.
- Rename the original imported pole number concept to **Pole ID**.
- Draw the red P number above the pole block.
- Move Detail text outside the carriageway on the pole's side.
- Final text should use a frame and/or wipeout where needed for readability.
- Remove the editing text identified by the user with a cross in Comment1 from final output.
- Generate final print labels again from metadata during sheet creation. Do not damage or
  overwrite CAD Master editing labels.

### CAD block specification changes

- Change `PRS_POLE` nominal size from 100 to 200.
- Change `PRS_TRANSFORMER_RACK` nominal size from 100 to 200.
- Add a red equilateral triangle of size 600 to `PRS_TRANSFORMER_RACK`, positioned 100
  above the rack.
- Render `SOI-EDGE` in white.

### Read-back, numbering, and Pole Report

Planned actions are `Read Pole Positions`, `Preview Pole Report`, and
`Export Pole Report`.

`Read Pole Positions` reads the latest PRS pole-block insertion positions from the locked
AutoCAD drawing. PoleRoute then recalculates station, latitude, and longitude; AutoCAD does
not own those calculations.

The report/table must contain ruled columns for:

- Pole No. (`P1`, `P2`, ...)
- Pole ID
- Details
- Station
- Position X
- Position Y
- Latitude
- Longitude

The report workflow must support Same_Station review.

### Transformer Rack with two different source coordinates

- Do not add automatic detection logic for this case.
- Let the user explicitly select which records form a Transformer Rack, even when their
  coordinates differ.
- Use the first record coordinate as the rack insertion/reference point.
- Keep the existing `PRS_TRANSFORMER_RACK` behavior; do not place its second leg using the
  second record coordinate.
- Preserve the second record as rack work/detail metadata.

### PRSPOLESPACE CAD utility

Working command name: `PRSPOLESPACE`, with behavior similar to ARRAY PATH:

```text
Select the existing pole blocks
→ Select the green POLE_OFFSET path
→ Enter spacing (for example 40 m)
→ Move the selected original blocks along the path
```

For five blocks at 40 m, target stations are `0, 40, 80, 120, 160`. The utility must
**move the existing blocks**, never clone/copy them, because every block carries unique
attributes and identity. PoleRoute recalculates station and coordinates after Read-back.

## Major product decisions

### Import and confirmation

- Pole column mapping is always shown even when all headers are detected.
- Use Arabic numerals in application controls and progress dialogs.
- Never silently interpret duplicate pole coordinates.
- A user-selected OSM road/soi is authoritative and must not be silently discarded later.
- Correct LineString direction with `Reverse` during route import, not downstream hacks.

### Route and road geometry

- Multiple Main-route LineStrings are allowed.
- Every classified route owns road width, pole-line creation, and offset settings.
- Offset is measured outward from the road edge. Offset `0` means the road edge; it does
  not disable projection. Pole-line creation is a separate setting.
- Large intersections are explicit Cross-road or T-junction guide LineStrings. Matching
  OSM carriageways may refine them; manual geometry is the fallback.
- Structural road surfaces are unioned before producing open boundaries.
- Ordinary sois must be clipped at the joined road surface, never cross the Main carriageway.

### OpenStreetMap context

- OSM is supporting context, not a background basemap or unquestioned truth.
- Recommend genuinely connected candidates. Keep major/unnamed/service roads available
  for manual review and de-duplicate split ways at the same junction.
- Display-length presets are Short 15 m, Medium 20 m, Long 25 m, and Custom.
- Fetching must be asynchronous and visibly show progress.

Fetched candidates and accepted surroundings are separate states. `Review surroundings`
reopens the last complete candidate snapshot without a network request, while
`Refresh surroundings` explicitly fetches a new snapshot. Failed or cancelled refreshes
leave both the previous candidates and accepted surroundings unchanged. Candidate roads,
places, features, warnings, metrics, and available provenance persist in `.prs`; older
projects without this field load with no candidates.

### OpenStreetMap Surround V2 (planned online phase)

Do not implement Offline Thailand OSM in this phase. Continue using online OSM and expand
the reviewed categories to:

- Roads / Sois
- Road Bridge only when it is a real bridge crossing a river, canal, or another road;
  ordinary `highway=*` is not sufficient
- Footbridge
- River
- Canal / Waterway
- Building footprint and optional real building name
- Fuel station, mall, shop, and important POI

Draw meaningful geometry, not labels alone. Use an OSM name only when a real `name` exists;
never invent a name. Buildings use footprints; waterways and bridges retain geometry long
enough to communicate the crossing; POIs use a symbol or footprint as appropriate.

Surround Review must allow category visibility, candidate selection, and an adjustable
building/POI corridor beginning around 100 m on each side of the Main route. Roads/sois may
keep the existing short context-length behavior. Do not shorten rivers/canals until the
crossing becomes unintelligible, and never silently remove accepted candidates.

Avoid visual clutter by not labeling every shop/building. Proposed semantic layers are:

```text
PRS_OSM_BRIDGE            PRS_OSM_BRIDGE_NAME
PRS_OSM_FOOTBRIDGE
PRS_OSM_RIVER             PRS_OSM_RIVER_NAME
PRS_OSM_CANAL             PRS_OSM_CANAL_NAME
PRS_BUILDING              PRS_BUILDING_NAME
PRS_OSM_FUEL              PRS_OSM_FUEL_NAME
PRS_OSM_SHOP              PRS_OSM_SHOP_NAME
PRS_OSM_POI               PRS_OSM_POI_NAME
```

### Online OSM Surround V2 implementation status

Phases 2.1 through 2.5 and Phases 2.6A through 2.6C are implemented.
Accepted OSM features retain stable
`(osm_type, osm_id)` identity, category, geometry kind, multipart geometry, polygon holes,
real OSM names, normalized tags, recommendation metadata, and source path through project
save/reload. The review workflow owns accepted-feature state independently from legacy
Roads/Sois.

Accepted features render in route preview, metric geometry preview, and editable network or
straight schematic canvases. Rendering is additive and does not enter road-network geometry,
pole projection, road offsets, or pole-line calculations. Only a real accepted OSM `name` is
drawn; technical identities and invented fallback labels are not user-visible labels.

DXF export supports POINT, LINESTRING, MULTILINESTRING, POLYGON (including holes), and
MULTIPOLYGON on the semantic `PRS_OSM_*` layers above. Fuel, shop, and POI name layers are
intentional additions so symbols and optional real names remain independently controllable.
Invalid accepted geometry raises an identity-rich export error instead of being silently
dropped. Creating layouts from an edited CAD Master preserves these Model Space layers and
entities.

### Phase 2.6A — multi-source Surround → AutoCAD representation contract

The context-feature model is source-neutral and additive. OpenStreetMap remains the
primary semantic/context source. Overture Maps is the approved default supplemental
building source for a future phase; direct Microsoft GlobalML Building Footprints fetching
is not part of the default product workflow. No supplemental fetch or cross-source
conflation is implemented in Phase 2.6A.

The A005 100 m corridor benchmark that informed this decision found approximately:

- OpenStreetMap: 1 building footprint
- Microsoft GlobalML Building Footprints: 404 building footprints
- Overture Maps Buildings: 612 building footprints

Context features preserve a generic `(source, source_id)` identity plus optional release,
version, provider, dataset, resource, record ID, update time, confidence, license,
provenance contributors, conflation status, and matched source IDs. Existing OSM identity
`(osm_type, osm_id)` remains intact and derives `source=OpenStreetMap` and a stable generic
source ID when an older project lacks the new fields. Old `.prs` files therefore load
without a forced schema migration. Future Overture records must use their stable Overture
record ID as `source_id`, not a fabricated OSM identity.

CAD representation is semantic-first: building footprints from every source export to
`PRS_BUILDING`, with real names on `PRS_BUILDING_NAME`. The old
`PRS_OSM_BUILDING`/`PRS_OSM_BUILDING_NAME` layers remain recognized as legacy CAD content
and must survive CAD Master/sheet handoff, but new exports use the canonical layers. Other
implemented OSM feature layers retain their current names and visual behavior in this
phase.

Every exported context-feature geometry part, polygon ring, and optional label carries
registered `POLEROUTE` XData. Minimum fields are `prs_object_type`, `prs_feature_key`,
`category`, `source`, and `source_id`. Available names, releases, providers, datasets,
OSM type/ID, confidence, and multipart part/ring roles are also retained. The same stable
feature key connects all CAD entities belonging to one semantic candidate.

Attribution is data, not an invented label. Project persistence retains provider/dataset,
license, release/version, and detailed provenance so a future export UI/title block can
produce source attribution. Phase 2.6A does not yet render attribution into CAD sheets.

Future semantic symbol block names should be stable and source-neutral (for example
`PRS_FOOTBRIDGE`, `PRS_FUEL`, `PRS_SHOP`, and `PRS_POI`). Their final symbols are not
implemented here; existing visual output remains unchanged except for the canonical
building-layer transition.

### Phase 2.6C — water context and bridge/footbridge CAD representation

River and canal features now retain two distinct geometries. Their authoritative source
geometry remains unchanged in project data, while an optional derived display geometry is
used by Surround Review, Qt rendering, and DXF export. Linear water display geometry keeps
every relevant span intersecting the configured Main-route corridor and extends 175 m along
the waterway beyond the corridor on each end. Polygon water is clipped to the expanded
corridor and preserves surviving interior rings. This policy is water-only: legacy
Roads/Sois short-context clipping and all road-network/pole calculations are unchanged.

Road bridges remain real source geometry. Footbridges export as deterministic
`PRS_FOOTBRIDGE` block inserts on `PRS_OSM_FOOTBRIDGE`, positioned at the midpoint of the
longest rendered line part and oriented to its local tangent. A legacy footbridge block
alias remains defined for older CAD workflows. Geometry and inserts carry the existing
source-neutral `POLEROUTE` XData contract.

Bridge-to-water relationships are conservative metadata, not inferred labels. A bridge or
footbridge records `crosses_category`, stable feature key/source identity, and a real water
name only when exactly one river/canal candidate intersects it (or is within the strict
0.25 m topology tolerance). Zero or multiple candidates remain unassigned rather than being
guessed. These relationship and display fields persist additively; old `.prs` files load
with empty values and derive display context after a Main route is available.

Real-project regression checks preserve the accepted feature inventory: A005 keeps 612
buildings; A006 keeps 128 buildings plus 7 canals, 15 footbridges, and 11 road bridges; the
Lat Ya fixture keeps 1,123 buildings, 4 rivers, 4 footbridges, and 2 road bridges. These
checks supplement synthetic tests for long/parallel/crossing water, polygon holes,
ambiguous bridge relationships, persistence, and deterministic footbridge orientation.

### Qt schematic and editing

- The drawing remains editable objects, not a flattened image.
- Pole symbols are square and road-aligned.
- Same-pole records draw one marker and retain every work label.
- Transformer racks draw two square legs and a joining rack line.
- Wheel scrolls vertically; Shift+wheel horizontally; Ctrl+wheel zooms; middle button does
  nothing.
- Preview/export must never reparent, clear, delete, or mutate live canvas items.

### Excel output

- Use editable native Office shapes/text, monochrome plot styling, open road ends, optional
  thin dashed centerline, frame, project info, compass, sheet links, and pole schedules.
- Break pages at pole positions; adjacent pages may share the boundary pole.
- All pages use a common display scale and schematic placement principles.
- Long operations show progress and keep the UI responsive.

### Existing CAD Master and edited-DXF implementation

- DXF is metric UTM CAD interchange. Model Space is the editable full-length source.
- Keep semantic layers separate: road components, contexts, offset, poles, labels,
  junctions, frames/tables/viewports, and sheet breaks.
- Editing/construction layers configured as non-plot include `POLE_OFFSET`, `POLE_LABELS`,
  `SHEET_BREAK`, and `SHEET_VIEWPORT`.
- Ordinary poles use solid `PRS_POLE`; transformer racks use `PRS_TRANSFORMER_RACK`.
- Each physical-pole insert carries invisible `POLE_IDS`, `DETAILS`, `QUANTITIES`,
  `PHYSICAL_GROUP`, `STATION_M`, and `KIND` attributes.
- Moving a block must not break ownership. Final labels/schedules come from metadata,
  not visible editing text.
- CAD Master labels stay horizontal for editing. Sheet labels are regenerated after
  viewport alignment.
- The current `PRS_SHEET_BREAK` implementation stores break ID, pole ID, Main-route
  station, and adjacent pages. This remains useful metadata, but its creation timing and
  downstream use must be migrated to the approved AutoCAD execution workflow above.
- The existing Paper Space sheet builder is a baseline/reference implementation. The
  approved target creates clean Sheet Copies in Model Space first, then creates/refreshes
  layouts from those copies.

## Rules that must not change without explicit product discussion

1. When pole data is imported, do not bypass its mandatory mapping/review/confirmation dialogs.
2. Do not infer physical-pole count from installed quantity.
3. Do not merge work records or discard detail/quantity metadata.
4. Do not identify moved CAD poles by nearest coordinate or visible label; use block IDs.
5. Do not use `PRS_SHEET_BREAK` XY for viewport angle or center.
6. Do not mutate the live Qt scene during preview/export.
7. Do not silently drop approved OSM surroundings.
8. Do not reintroduce road end caps or soi lines across the Main road.
9. Do not flatten Excel output while editable-object export is required.
10. Do not commit local projects, screenshots, exports, or error reports without consent.
11. Layout work requires a real `.prs`/DXF visual check, not only synthetic tests.
12. Do not finalize `PRS_SHEET_BREAK` before reading the user's latest AutoCAD pole positions.
13. Do not let AutoCAD/LSP calculate a Sheet Plan that competes with PoleRoute.
14. Do not silently switch the locked AutoCAD target drawing.
15. Do not clone/copy identity-bearing pole blocks in spacing tools; move the originals.
16. Do not destroy or rewrite the CAD Master when Execute refreshes generated sheets.
17. Do not invent OSM names or silently delete surroundings accepted by the user.

## Current status after Phase 1

## Phase 2.7 — Surround performance and reliability

Online Surround fetching now uses distance-based route batches shared by OSM and Overture:

- Core batch length: 3,000 m.
- Internal overlap: 150 m on either side of a batch boundary.
- Accepted objects are deduplicated by stable semantic/source identity after merge; overlap must
  not create duplicate roads, places, or features.
- OSM and Overture remain independent sources. A failed Overture request never discards OSM,
  and a failed OSM interval does not discard successful intervals.
- OSM retries each batch once and its existing endpoint list provides ordered fallback. Partial
  warnings identify source, batch number, and metric route interval.
- Progress reports preparation, source and batch, cached Overture results, conflation, review
  preparation, and completion. Cancellation is cooperative at source/batch boundaries and must
  leave the previously accepted context unchanged.
- Overture cache keys include release, request bounds, and corridor. Cache writes are atomic,
  malformed entries are ignored, and only the eight most recent JSON entries are retained.
- Fetch metrics include route length, batch count, source elapsed time, retry/failed-batch counts,
  cache hits/misses, raw/corridor counts, conflation counts, and total elapsed time.

Real-file validation on 2026-08-22:

- A005: 2,199 m, 1 batch, 11.61 s, 612 buildings, no warnings, Overture cache hit.
- A006: 3,561 m, 2 batches, 438.53 s, 901 buildings. OSM batch 2 failed after retry;
  successful OSM plus Overture results were retained with an interval-specific partial warning.
- Lad Ya: 17,494 m, 6 batches, 1,438.45 s, 1,123 buildings, 4 rivers, 4 footbridges,
  and 2 road bridges. OSM batch 3 failed after retry and other batches were retained.

These measurements prove bounded progress and partial recovery, not faster upstream service.
During validation the Overture STAC endpoint repeatedly reported an `aws-s3` index error and
consumed most wall time (1,287.53 s on Lad Ya) despite ultimately returning data. Provider-side
latency remains a known risk; do not describe batching itself as a network speed improvement.

### Working and tested

- KML/KMZ classification, reversing, multiple routes, and junction validation
- CSV/XLSX mapping, decimal/DMS coordinates, Thai aliases, installed quantity
- UTM road geometry, pole lines, nearest placement, network schematic
- Duplicate-coordinate review, same-pole and transformer-rack handling
- Reviewed OSM fetching and road-name retention
- Online OSM Surround V2 review, accepted-feature persistence, canvas rendering, and semantic
  DXF export for bridges, waterways, buildings, fuel, shops, and important POIs
- Portable `.prs` save/open and editable scene restoration
- Editable Excel preview/export and multi-page schedules
- Metric DXF Master, semantic pole blocks/metadata, sheet markers
- Edited-DXF validation and persistence
- A4 CAD Paper Space generation from edited poles with common scale and schedules
- Canonical physical-pole/P Label mapping and explicit transformer-rack leg assignment
- Locked AutoCAD target selection plus tested Route/Offset/Pole readback service and managed
  pole-overlay update path
- Separate fetched Surround candidates and accepted surroundings, cached review without a
  network call, explicit refresh, bulk selection actions, and backward-compatible persistence
- Automated suite: 256 tests passed at the last verified coding session

### Active visual defects reported after the CAD-sheet baseline

These remain unresolved until a later commit fixes and visually verifies them:

1. CAD sheets plot both Model Space editing labels and regenerated Paper Space labels.
   Editing labels (yellow-marked in screenshots) must not plot; final pole detail belongs
   only at the agreed lower/perpendicular position.
2. Sheet viewports expose route objects beyond intended left/right boundary poles. Current
   station membership controls schedules/labels but viewport centering is not true clipping.
3. The regenerated Thai Main-road name appears as `???????????`; this is an encoding/font
   defect, not meaningful source text.
4. Place one clean Main-road name below the carriageway and suppress its Model Space duplicate.
5. Reconfirm compass direction after each page transformation against geographic north.

## Planned implementation order

### Approved next product workflow

The next implementation sequence is the PEA GIS and free-context workflow maintained in
[`CURRENT_WORK.md`](CURRENT_WORK.md) and specified in
[`docs/architecture/PEA_GIS_FREE_CONTEXT_WORKFLOW.md`](docs/architecture/PEA_GIS_FREE_CONTEXT_WORKFLOW.md):

1. multi-sheet PEA GIS workbook import, beginning with `DS_Pole`;
2. route-based Pole QC, station/offset ordering, manual review, and Google Earth Pro KML;
3. generic coordinate-bearing PEA assets, beginning with `DS_Transformer` and `DS_Switch`;
4. reviewed Overture Places for useful landmarks; and
5. later CAD integration of the confirmed PEA pole/asset data through the existing
   canonical identity, optional Pole Overlay, and locked-target foundations.

This approved sequence supersedes using the later AutoCAD items below as the immediate
next implementation work. Those items remain valid deferred architecture unless a later
decision explicitly changes them. The validation route measurements documented in the
architecture file are evidence only and must never become production constants.

Completed stability work:

1. Phase 1A: save stability, live-canvas preservation, and shared working-directory handling.
2. Phase 1B: DXF read-only investigation, resolved as a Windows/Autodesk file-association issue.

Completed Online OSM work:

3. Phases 2.1-2.5: reviewed **Online OSM Surround V2** domain, persistence, parsing, accepted
   state, canvas rendering, and semantic DXF export. Offline Thailand OSM remains explicitly
   outside the current implementation.
4. Phase 2.6A: source-neutral context identity/provenance, canonical building CAD layers,
   and per-entity AutoCAD XData contract.
5. Phase 2.6B: Overture Buildings is an optional online supplement to OSM. Fetching is
   bounded to the 100 m Main-route corridor, keeps full intersecting footprints, and uses
   conservative OSM-first spatial conflation. Confident matches keep OSM geometry and merge
   provenance; ambiguous and unmatched Overture footprints remain separately reviewable.
   The Building review shows OSM, Overture, or OSM + Overture source state. Accepted features
   continue to persist through `.prs` and export to the canonical `PRS_BUILDING` /
   `PRS_BUILDING_NAME` layers with source and conflation XData. A failed Overture request must
   never discard a successful OSM result. Users can disable supplemental Overture fetching
   from the Data menu; the preference is local application state, not project state.
6. Phase 2.6C: waterways keep authoritative source geometry plus a derived 100 m corridor
   display with 175 m along-water context; bridge/water relationships are conservative;
   footbridges export as deterministic semantic blocks with XData. Roads/Sois and pole
   placement behavior remain unchanged.
7. Phase 2.7: distance batching, overlap dedupe, partial-source recovery, bounded Overture
   cache, truthful progress/cancellation, and structured fetch metrics.

Completed AutoCAD foundation and Surround finalization:

8. Canonical physical-pole mapping, continuous P Labels, explicit transformer-rack legs,
   and auditable CAD metadata.
9. Explicit locked AutoCAD connection plus `Read Route`, `Read Pole Offset`, `Update Poles`,
   and `Read Pole Positions` service/UI paths. Real AutoCAD COM validation remains required.
10. Separate fetched Surround candidates from accepted surroundings; persist candidate
    snapshots; reopen review without network; refresh explicitly; support deterministic
    Select All, Clear All, and Select Recommended actions.

Later AutoCAD integration work:

11. Add the interactive two-point calibration UI for arbitrary CAD routes without world
    coordinates, then implement Pole Report preview/export and Same_Station review.
12. Calculate/preview/adjust Sheet Plan from the latest pole positions and only then create
   confirmed `PRS_SHEET_BREAK` markers.
13. Execute Model Space Sheet Copies with strict pole-boundary clipping, generated-object
   ownership, final labels, frames, and refreshed layouts.
14. Add `PRSPOLESPACE` as a utility and complete remaining visual/plot validation.

No later-phase item is considered implemented merely because it is documented here.

## External regression files

- `D:\TestFile\A002\A002.prs`
- `D:\TestFile\A002\A0021.prs`
- `D:\TestFile\A003\A003.kml`
- `D:\TestFile\A003\A0031.prs`
- `D:\TestFile\A004\A004latlong.xlsx`
- `D:\TestFile\A004\A0043.prs`
- Recent A004 edited/master/sheet DXFs under `D:\TestFile\A004\`
- `C:\Users\ferty\Downloads\Master A3\editpageno.lsp`
- `C:\Users\ferty\Downloads\Master A3\editpageno2.lsp`

They are local references and are not part of a fresh clone.

## Git and cross-chat handoff

```powershell
git switch main
git pull origin main
git status
git log -5 --oneline
```

After an authorized change: run focused/full tests, inspect the diff, commit only intended
paths, push, and update this document if decisions/status changed.

For planning, give the other chat the repository and ask it to read this file first. For
coding, provide this chat an already-decided task or GitHub issue; it should implement,
test, commit/push when authorized, and report the commit plus test artifact.
