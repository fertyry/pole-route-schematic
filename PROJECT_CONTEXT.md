# PoleRoute Schematic — Project Context

> Canonical handoff document for Codex/ChatGPT sessions and development computers.
> Read this file, `README.md`, `CHANGELOG.md`, `git status`, and recent commits before
> discussing or changing the project. Update it when architecture, workflow, or a
> product invariant materially changes.

## Repository state at this handoff

- Repository: `https://github.com/fertyry/pole-route-schematic`
- Primary branch: `main`
- Last source-code baseline verified on 2026-08-20: `014e18a`
- Baseline subject: `Fix project save stability and working directory handling`
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

## Current implemented workflow (baseline before the next CAD phase)

1. Create/open a portable `.prs` project and enter project information.
2. Import one or more KML/KMZ LineStrings.
3. Classify each selected line as Main route, Road/Soi, Cross road/Large intersection,
   or T-junction; set width, pole-line creation, offset, and Reverse.
4. Optionally fetch OpenStreetMap surroundings asynchronously and review candidates.
5. Import Excel/CSV poles through a mandatory column-mapping preview.
6. Review duplicate/near-duplicate coordinates and classify their physical meaning.
7. Build projected metric road geometry and pole placements.
8. Generate/edit a non-scale Qt schematic or export a metric CAD Master.
9. Save routes, poles, context, physical groups, scene, settings, and edited-DXF data to `.prs`.
10. Export editable multi-sheet Excel, or edit the CAD Master in AutoCAD/Map 3D.
11. Import edited DXF, validate stable IDs and sheet markers, confirm review, then use
    `Create CAD sheets` to rebuild A4 landscape Paper Space layouts.

This describes the implemented workflow through commit `014e18a`, not the final target workflow. The approved
AutoCAD execution architecture below supersedes the old assumption that sheet breaks and
Paper Space layouts should be finalized before the user finishes editing the CAD Master.

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

## CAD Master workflow clarification

The approved handoff into AutoCAD is:

```text
PoleRoute
→ Export DXF
→ Open the DXF in AutoCAD
→ Save As DWG
→ Use that DWG as the CAD Master
```

DXF remains PoleRoute's interchange/export format into AutoCAD. AutoCAD offers Save As
DWG when saving an opened DXF, and the resulting DWG is the native working CAD Master for:

- continued saves and manual CAD editing
- Connect AutoCAD
- Read Pole Positions
- Execute
- Sheet Copies
- Layouts

## Approved AutoCAD execution architecture (planned)

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

Phases 2.1 through 2.5 and the Phase 2.6A representation contract are implemented.
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

1. Do not bypass mandatory mapping/review/confirmation dialogs.
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
- Automated suite: 202 tests passed at the last verified coding session

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

Later AutoCAD integration work:

6. Implement explicit Connect AutoCAD with drawing selection, target locking, project
   validation, and disconnected-state handling.
7. Implement Read Pole Positions, Pole Report preview/export, and Same_Station review.
8. Calculate/preview/adjust Sheet Plan from the latest pole positions and only then create
   confirmed `PRS_SHEET_BREAK` markers.
9. Execute Model Space Sheet Copies with strict pole-boundary clipping, generated-object
   ownership, final labels, frames, and refreshed layouts.
10. Apply CAD block/layer specification changes and add `PRSPOLESPACE` as a utility.

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
