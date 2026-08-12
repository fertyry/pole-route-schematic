# PoleRoute Schematic

PoleRoute Schematic is an early-stage Windows desktop application for turning route and utility-pole data into an editable schematic drawing.

> Project status: Sprint 3 in progress. Confirmed imports, metric road geometry, and an editable non-scale schematic foundation are implemented. Project persistence and export are not implemented yet.

## Problem

Utility-pole route drawings are often assembled manually from a road alignment and pole-coordinate list. That work is repetitive, difficult to revise, and easy to make inconsistent. A map that is geographically accurate is also not always the clearest drawing for field or documentation use.

## Approach

The planned application will:

1. Read a KML/KMZ `LineString` exported from Google Earth Pro as the road centerline.
2. Read Excel or CSV pole data containing Pole No., Latitude, Longitude, Detail, and Side.
3. Use configurable road width and pole offset values to derive road edges and pole offset lines.
4. Project each pole coordinate to the nearest point on the appropriate pole offset line.
5. Produce a deliberately non-scale schematic whose drawing objects can be selected and edited.
6. Later export the finished drawing to PDF or PNG.

The source data remains geographic, while the final schematic prioritizes clarity and editability over map scale.

## V0.1 scope

Planned for V0.1:

- Windows desktop application built with Python and PySide6/Qt
- KML/KMZ road-centerline import
- Excel/CSV pole-data import
- Road-width and pole-offset settings
- Road-edge and pole-offset geometry
- Nearest-point projection of poles
- Editable, non-scale schematic using Qt Graphics View
- PDF and PNG export

Explicitly out of scope for V0.1:

- OpenStreetMap or another background map
- Screenshot analysis
- Automatic buildings or side roads
- Span-distance-based placement
- Advanced sheet cutting

## Current implementation

Sprint 0 established the application foundation. Sprint 1 added confirmed Excel/CSV pole import and KML/KMZ LineString selection. Sprint 2 added local UTM projection, road edges, pole offset lines, and nearest-point placement. Sprint 3 adds a deliberately non-scale layout: poles remain in source-route order but use equal visual spacing, and road/pole/label objects can be selected and moved independently. Project persistence and export are not implemented yet.

## Project structure

```text
pole-route-schematic/
├── docs/
├── samples/
├── src/pole_route/
│   ├── domain/
│   ├── geometry/
│   ├── importers/
│   ├── project/
│   └── ui/
└── tests/
```

Each folder has one responsibility: `ui` displays and edits, `domain` holds project concepts, `geometry` will perform spatial calculations, `importers` will read source files, and `project` will manage saved application projects.

## Run from VS Code on Windows

### 1. Install prerequisites

Install Python 3.11 or 3.12 from [python.org](https://www.python.org/downloads/windows/). During setup, select **Add Python to PATH**. Install VS Code and its official Python extension if they are not already installed.

### 2. Open the repository

In VS Code, choose **File → Open Folder** and select the `pole-route-schematic` folder. Open **Terminal → New Terminal**.

### 3. Create an isolated Python environment

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If Python 3.12 is unavailable, use `py -3.11` instead.

### 4. Install the project

```powershell
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

### 5. Select Python in VS Code

Press `Ctrl+Shift+P`, choose **Python: Select Interpreter**, then select the interpreter inside `.venv`.

### 6. Start the application

```powershell
python -m pole_route
```

You should see the PoleRoute Schematic window with an empty schematic-canvas placeholder.

### 7. Run tests

```powershell
pytest
```

## Technology direction

Python, PySide6/Qt, Shapely, pyproj, openpyxl, XML-based KML parsing, pytest, and PyInstaller. Dependencies needed in later sprints are recorded now, but their features are not implemented in Sprint 0.

## Portfolio note

This repository documents an incremental product-development process. Claims in this README distinguish planned behavior from implemented behavior so screenshots, releases, and Git history remain honest.

## License

No open-source license has been selected yet. See [LICENSE](LICENSE). Until a license is chosen, reuse and redistribution are not granted.
