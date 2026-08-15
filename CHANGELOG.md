# Changelog

## Unreleased

- Replaced outline CAD pole markers with reusable solid `PRS_POLE` and
  `PRS_TRANSFORMER_RACK` blocks carrying invisible source-record identity, detail,
  installed-quantity, physical-group, station, and type attributes.
- Made the CAD pole-offset layer non-plotting and clipped ordinary soi centerlines
  at joined structural-road surfaces to keep road mouths open without line overrun.
- Added mandatory duplicate-coordinate review after pole import, distinguishing one
  physical pole with multiple work items, transformer racks, separate poles needing
  coordinate correction, and accessory records.
- Added persisted transformer-rack groups and an editable two-pole rack symbol in the
  schematic while retaining every imported work-item label.
- Expanded duplicate-coordinate review with pole number/detail and installed-quantity
  columns so physical interpretations can be confirmed from the source work records.

- Added optional installed-quantity import mapping, project persistence, UI display,
  and quantity columns in Excel/CAD pole schedules.
- Fixed Thai header alias matching so combining vowel and tone marks do not prevent
  automatic mapping of fields such as `จำนวนที่ติดตั้ง`.
- Added explicit `Cross road / Large intersection` and `T-junction branch` route types.
- Added confirmation-based snapping for manual junction LineStrings with gaps up to 5 metres.
- T-junction routes may cross the Main route; they are trimmed at the junction and retain
  the longer approach arm.
- Added dedicated editable CAD layers for large cross roads and T-junction branches.
- Suppressed duplicate OpenStreetMap roads near manually classified large junctions in DXF export.
- Joined Main, Cross-road, and T-junction road surfaces before deriving DXF road
  outlines, so large junction mouths are open and their corners form one clean network.
- Treat manual Cross-road and T-junction LineStrings as location/direction guides and
  use matching nearby OpenStreetMap carriageways for the DXF junction outline when available.
- Preserve every road/soi explicitly accepted in the surroundings review during DXF
  export instead of silently removing nearby or same-named roads.
- Added automatic A4 landscape CAD sheet planning from true Main-route length, with
  boundaries moved to nearby poles, a common display scale, project information,
  continuation labels, north arrows, and per-sheet pole-detail tables.
- Fixed valid sois disappearing when their OSM centerline ended at the edge of a wide
  divided road, 4–15 metres from the user-drawn Main centerline.

## Unreleased

- Add metric DXF export for AutoCAD Map 3D with dedicated road, offset, pole,
  and label layers plus a reusable 1 m square pole block.
- Filter OpenStreetMap surroundings to roads that genuinely connect to the Main
  route, remove low-value path types, de-duplicate split junction candidates,
  and explain automatic recommendations in the review table.
- Extend only the overall first and last Excel sheet beyond their terminal poles;
  internal sheet boundaries continue to meet exactly at a shared pole.
- Add an explicit OpenStreetMap surroundings review after importing a Main route.
- Discover nearby connecting roads/sois and named landmarks along a metric route corridor.
- Preselect only named local roads; major and unnamed roads remain available for manual review.
- Limit fetched and imported surroundings to 15 m from the Main route, clipping each road
  to approximately 15 m on either side of its nearest connection point.
- Add Select all and Clear all controls to the surroundings review.
- Extend each accepted context road approximately 35 m from its nearest Main-route
  connection while retaining the 15 m OSM search corridor.
- Fetch OpenStreetMap surroundings on a background thread with an indeterminate progress
  dialog so the main application window remains responsive.

All notable changes to PoleRoute Schematic will be documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project intends to use semantic versioning after its first release.

## [Unreleased]

- Replaced Canvas-X sheet cutting with START-to-END Main-route station cutting for
  newly generated schematics, rotating each sheet's content to a horizontal road axis.
- Kept pole markers and their labels on the same sheet and added previous/next sheet
  continuation arrows plus a north arrow adjusted for each sheet's content rotation.
- Persisted Main-route export metadata in saved projects so reopened schematics retain
  route-aware sheet cutting.

- Stabilized Excel export review for large drawings by reusing one preview scene,
  coalescing rapid settings changes, and preventing overlapping redraws.

- Added a per-LineString `Reverse` option during route import. It reverses the
  coordinate order before confirmation and updates START/END in the preview.
- Added clear START and END markers for selected routes and each Main route in the
  combined import preview.

- Added multi-sheet export review with a configurable sheet count and Previous/Next
  navigation; Excel export now creates one print-ready worksheet per reviewed sheet.
- Added automatic horizontal route-span splitting with repeated continuation road
  lines, per-sheet frames, and `Sheet n / total` numbering.

- Added portable `.prs` project files with New, Open, Save, and Save As actions.
- Saved projects retain imported route and pole data, per-road geometry settings,
  same-pole groups, editable canvas object hierarchy, positions, and styling.
- Added unsaved-change indicators and Save/Discard/Cancel confirmation before
  starting another project, opening a project, or closing the application.
- Fixed project saving from the metric-preview stage by supporting its rich text labels.

- Fixed the live canvas disappearing as soon as Export Excel was clicked by retaining
  PySide graphics-item wrappers on their source scene before snapshot collection.

- Fully isolated the export-review dialog from the live canvas scene so closing or
  editing the review can never delete source drawing objects.

- Fixed confirmed Excel exports incorrectly re-reading an empty canvas; export now uses
  the exact styled object snapshot approved in the preview.

- Fixed export-preview objects disappearing during setting changes by snapshotting the
  source canvas and swapping fully rendered preview scenes atomically.

- Added a live Excel export preview with project information, A4/A3 paper and
  orientation controls, monochrome styling, frame/footer, compass, centerline mode,
  and pole symbol size in millimetres.

- Added Windows-only editable Excel export using native Line, Shape, and Text Box
  objects rather than a flattened image.

- Square pole markers are now automatically aligned with the local road direction
  during schematic generation.

- Changed pole markers from circles to simple square symbols.

- Added view-only canvas navigation: wheel scrolls vertically, Shift+wheel scrolls
  horizontally, Ctrl+wheel zooms, and the middle mouse button is ignored.

### Fixed

- Schematic spacing confirmation returns a stable spacing mode with PySide6
- Block placement ignores clicks and very short drags without repeated errors

### Added

- Dedicated Edit canvas mode that expands the drawing workspace and restores the data view
- Explicit Same pole grouping for multiple equipment records on one physical pole
- Network, straight equal-spacing, and straight relative-spacing generation choices
- Unified road-surface boundaries that clean up side-road, T-junction, and crossroad mouths
- Multi-LineString KML/KMZ classification with per-line Use, Type, and Width settings
- Main route validation plus multiple retained context routes
- Shift-modified angle snapping for semantic Blocks
- Non-destructive junction-mouth masks over the main-road edge
- Extensible Blocks menu with Side road, T-junction, Crossroad, Vehicle bridge, and Footbridge
- Two-point semantic block placement with automatic main-road anchor snapping and Alt override
- Shift-modified 45-degree angle snapping for the Line tool
- Confirmed Equal spacing or Projected station spacing schematic generation modes
- Select, Line, Rectangle, Ellipse, and Text canvas tools
- Undoable creation of movable and deletable drawing objects
- Undo/Redo for moved, deleted, and reset schematic objects
- Delete selection and confirmed Reset layout editor actions with keyboard shortcuts
- Uniformly spaced non-scale schematic generation ordered by source route station
- Selectable and movable road, pole, and label graphics objects
- Decimal-degree and DMS pole-coordinate parsing with degree symbols and N/S/E/W
- Metric UTM road geometry preview with road edges and left/right pole offset lines
- Nearest-point projection of known-side poles onto their designated pole line
- Confirmed Road Width and Pole Offset settings before every geometry build
- KML/KMZ LineString inspection with route selection, details, shape preview, and confirmation
- Column-mapping confirmation dialog shown before every import, with a five-row preview
- Automatic header-row detection and common English/Thai column aliases
- Sprint 1 Pole and Route domain data contracts
- CSV/XLSX pole import with header, coordinate, and Side validation
- Pole-data table and enabled Import poles action in the desktop application
- Sprint 0 repository and package structure
- PySide6 Windows application shell with a placeholder schematic canvas
- Initial project documentation, dependency declarations, and tests

### Changed

- Geometry settings use Arabic digits regardless of the Windows display locale
