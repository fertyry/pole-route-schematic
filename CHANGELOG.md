# Changelog

All notable changes to PoleRoute Schematic will be documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project intends to use semantic versioning after its first release.

## [Unreleased]

### Added

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
