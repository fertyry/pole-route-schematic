# Changelog

All notable changes to PoleRoute Schematic will be documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project intends to use semantic versioning after its first release.

## [Unreleased]

### Fixed

- Schematic spacing confirmation returns a stable spacing mode with PySide6
- Block placement ignores clicks and very short drags without repeated errors

### Added

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
