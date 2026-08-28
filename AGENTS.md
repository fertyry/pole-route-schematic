# PoleRoute Schematic — Agent Rules

These instructions apply to Codex and other AI agents working in this repository.

## Source of truth and startup

- GitHub `main` is the source of truth.
- Before changing code, synchronize safely and read `PROJECT_CONTEXT.md`,
  `CURRENT_WORK.md`, and every relevant document under `docs/architecture/`.
- Inspect the actual source and tests before planning a change. Documentation may describe
  planned work and is not evidence that a feature is implemented.
- When documentation and current implementation differ, report the difference explicitly.

## Architecture boundaries

- Reuse existing domain, service, geometry, persistence, context/provenance, and CAD
  foundations before creating another system.
- Domain models must not depend on Qt UI objects or behavior.
- Geometry and ordering services must be deterministic and independently testable.
- The UI owns review, manual override, confirmation, and user-facing errors.
- Exporters consume approved snapshots and must never mutate the source project or live
  Qt scene.
- `project/storage.py` is the portability boundary. Prefer additive optional fields and
  safe defaults; explain and obtain approval before changing the project schema version.
- External data providers require clear boundaries so a provider can be replaced later.

## Data integrity and review

- Preserve stable source, pole, physical-pole, asset, context, and CAD identities.
- Preserve backward compatibility with old `.prs` files.
- Never hard-code sample routes, counts, coordinates, observed pole numbers, or validation
  evidence as general product logic.
- Never silently drop user-approved data, parse failures, contradictory records, or source
  records excluded by a default filter. Surface them for warning/review.
- Never silently overwrite a manual pole order or other explicit user override.
- Never auto-confirm asset-to-pole matching.
- Keep `.prs` as the project source of truth; generated KML, DXF, DWG, XLSX, PDF, and
  screenshots are artifacts or external working files.

## CAD invariants

- Reuse the locked-target AutoCAD connection; never retarget based on the active tab.
- Optional Pole Overlay updates must not rebuild or destroy Base CAD or manual CAD edits.
- Readback and updates use stable metadata, not visible text or XY coincidence alone.
- DXF is PoleRoute's file interchange format; DWG is the recommended AutoCAD native
  working format.

## Testing and Git safety

- Add tests for parsing, normalization, deterministic geometry/order, persistence,
  backward compatibility, and regressions appropriate to the change.
- Run focused tests first and the full suite when appropriate. Fix root causes rather than
  weakening assertions.
- Inspect `git status`, `git diff`, and `git diff --check` before committing.
- Commit only intended paths. Never use `git add .` in a dirty worktree.
- Do not commit local test projects, private workbooks, screenshots, generated exports,
  error reports, caches, or diagnostics unless explicitly authorized.
- Never reset, stash, restore, checkout, delete, or discard unrelated local work.
- Update `CURRENT_WORK.md` after a milestone changes the next work.
- Update `PROJECT_CONTEXT.md` when an architecture decision, product invariant, approved
  workflow, or significant implemented baseline changes.

