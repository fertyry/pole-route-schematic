# Changelog

All notable changes to PoleRoute Schematic will be documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project intends to use semantic versioning after its first release.

## [Unreleased]

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
