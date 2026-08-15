# PoleRoute Schematic — Project Context

> This file is the handoff document for a new Codex/ChatGPT session or a second
> development computer. Read it together with `README.md`, `CHANGELOG.md`, and the
> current Git history before changing the application.

## Product purpose

PoleRoute Schematic is a Windows desktop application and portfolio project for
creating editable, deliberately non-scale utility-pole route drawings.

The application combines:

- a KML/KMZ route from Google Earth Pro;
- Excel/CSV pole records;
- metric road and pole-offset geometry;
- optional OpenStreetMap surroundings; and
- an editable Qt Graphics View canvas.

The intended result is a clear schematic suitable for review and export to Excel,
where drawing elements remain editable objects.

## Current technology

- Python 3.13 on the primary development computer
- PySide6 / Qt Graphics View
- Shapely and pyproj
- openpyxl
- XML-based KML/KMZ parsing
- pytest
- Git and GitHub

Run the application from the repository root with:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pole_route
```

Run validation with:

```powershell
pytest
```

## Implemented workflow

1. Create or open a portable `.prs` project.
2. Import one or more KML/KMZ LineStrings.
3. Classify routes, set road width and pole-offset behavior, and reverse an
   incorrectly drawn LineString when required.
4. Optionally fetch nearby roads and road names from OpenStreetMap.
5. Import Excel/CSV pole data through an explicit column-mapping confirmation.
6. Build projected road geometry and place poles against the selected offset line.
7. Generate and edit a non-scale schematic.
8. Mark records that represent equipment on the same physical pole.
9. Save the complete project as `.prs`.
10. Review page layout and export editable Excel sheets.
11. After building geometry, optionally export a metric DXF for AutoCAD Map 3D.
    The DXF keeps the complete metric Model Space and adds automatic A4 landscape
    Paper Space layouts cut at pole positions.

## Important product decisions

- Column mapping must always be shown before confirming pole import, even when
  headers can be detected automatically.
- Multiple LineStrings may be main routes. Each route owns its road-width and
  pole-offset settings.
- Pole offset is measured outward from the road edge. A route can explicitly opt
  out of generating a pole-offset line.
- LineString direction matters. Reverse it during route import instead of adding
  compensating logic later in the workflow.
- Large intersections are supplied explicitly as Cross-road or T-junction
  LineStrings. They act as location and direction guides: DXF export uses matching
  nearby OpenStreetMap carriageways when available, falls back to the manual geometry,
  and unions the result with the Main road before deriving a shared road outline.
- Roads/sois accepted in the OpenStreetMap review are authoritative and must not be
  silently removed by a later exporter.
- CAD sheet planning uses a target Main-route span of about 350 metres per A4
  landscape sheet. A saved sheet count of 1 means automatic planning for DXF;
  explicit values above 1 are respected. Model-Space-only and sheet-layout DXF
  exports both carry non-plotting `PRS_SHEET_BREAK` block references at the
  planned pole boundaries, with break ID, pole ID, station, and adjacent sheets.
- Two records can describe one physical pole. The canvas shows one pole symbol and
  retains the separate equipment/detail text.
- Pole symbols are square and aligned with their road.
- The schematic is not to scale, but relative station spacing and important
  features such as sois and footbridges must remain meaningful.
- Page breaks are chosen at pole positions. Sheet route lengths should be similar,
  while preserving the same placement principles used by schematic generation.
- Excel output uses black editable objects, optional thin dashed centerlines, open
  road ends, a north arrow, page frames, project information, and pole-detail
  tables.
- OpenStreetMap surroundings are supporting context, not a full background map.
  Context roads are clipped to a short configurable length. Current presets are
  Short 15 m, Medium 20 m, Long 25 m, plus Custom.
- OSM candidates must connect to the Main route within a small junction tolerance.
  Named roads are recommended automatically; unnamed and service access roads stay
  available for explicit manual review. Split OSM ways at the same junction are
  de-duplicated.
- DXF is the CAD interchange format. It retains UTM metre coordinates and separates
  Main centerlines, road edges, context roads, pole-offset lines, poles, and labels
  into CAD layers. Pole symbols use the reusable `POLE_1M` block.
- Pole labels in the full-length CAD Master stay horizontal for readable manual
  editing. Records at one coordinate are vertically staggered. Their final
  orientation and frame collision handling belong to the edited-DXF sheet-cutting
  stage, after each sheet viewport has been aligned.
- Road-name labels must stay associated with their junction, remain inside the
  sheet, and not distort page fitting.

## User interaction expectations

- Prefer visible confirmation dialogs over silent automatic decisions.
- Use Arabic numerals in application controls and progress dialogs.
- Canvas navigation: mouse wheel scrolls vertically, Shift + wheel scrolls
  horizontally, and Ctrl + wheel zooms. The middle mouse button has no action.
- Editing and export previews must never mutate or clear the source canvas.
- Long operations such as fetching surroundings and exporting Excel must show
  progress.

## Current UI direction

The V2 interface groups actions under Project, Data, Geometry, Drawing, and Output.
Primary and drawing toolbars use icons. Fetch surroundings is available after a
main route has been imported.

## Current duplicate-pole workflow

- Pole import now opens a required review when records are within 0.5 m. The user
  explicitly classifies each group as one physical pole with multiple work items,
  a two-pole transformer rack, separate poles needing coordinate correction, or an
  accessory record. Installed quantity never determines physical-pole count.
- Confirmed one-pole and accessory groups reuse the existing one-marker/many-label
  behavior. Transformer-rack groups render two editable square markers joined by a
  rack line on the schematic. Both group types persist in `.prs` files.
- Transformer-rack groups also export as one reusable `TRANSFORMER_RACK` CAD block
  with two nominally three-metre-separated legs, while retaining every work-item
  label. This preserves the physical structure during downstream CAD editing.

## Known design work still open

- Add a Sheet Plan confirmation dialog and persist user-adjusted pole boundaries;
  automatic non-plotting `PRS_SHEET_BREAK` blocks are already exported.
- Implement edited-DXF re-import, break validation, and final sheet cutting.
- Validate OSM junction recommendations on more real routes and tune the 4 m
  connection tolerance if mapped centerlines are visibly misaligned.
- Extend context slightly beyond the first and last main-route poles.
- Improve road-name side/orientation placement in difficult intersections.
- Continue evaluating the metric DXF workflow in AutoCAD Map 3D for routes around
  3–5 km and grow the reusable CAD block library only from proven drafting needs.
- Analyse the supplied AutoLISP files before deciding whether their page-numbering
  logic belongs in the CAD workflow.

## Regression and sample files

External test files currently used by the project owner:

- `D:\TestFile\A002\A002.prs`
- `D:\TestFile\A002\A0021.prs`
- `D:\TestFile\A003\A003.kml`
- `D:\TestFile\A003\A0031.prs`
- `D:\TestFile\A004\A004latlong.xlsx`
- `C:\Users\ferty\Downloads\Master A3\editpageno.lsp`
- `C:\Users\ferty\Downloads\Master A3\editpageno2.lsp`

These paths are local references and are not expected to exist in a fresh clone.
Do not commit user project data unless the owner explicitly approves it.

## Git handoff rule

The primary branch is `main`. A commit existing on one computer is not available
on another computer until it has been pushed to `origin/main`. Before switching
computers:

```powershell
git status
git push origin main
```

On the other computer:

```powershell
git switch main
git pull origin main
```

At the beginning of a new coding session, inspect this file, `git status`, recent
commits, and the relevant source/tests. Update this context whenever a product
decision materially changes.
