"""Inspect a PoleRoute CAD Master after it has been edited in AutoCAD."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import ezdxf


class EditedDxfImportError(RuntimeError):
    """The selected DXF is not a usable edited PoleRoute CAD Master."""


@dataclass(frozen=True, slots=True)
class EditedPoleBlock:
    block_name: str
    pole_ids: tuple[str, ...]
    details: tuple[str, ...]
    quantities: tuple[int, ...]
    physical_group: tuple[str, ...]
    station_metres: float
    x: float
    y: float
    rotation: float


@dataclass(frozen=True, slots=True)
class EditedSheetBreak:
    break_id: str
    pole_id: str
    station_metres: float
    sheets: str
    x: float
    y: float
    rotation: float


@dataclass(frozen=True, slots=True)
class EditedDxfInspection:
    source_path: str
    pole_blocks: tuple[EditedPoleBlock, ...]
    sheet_breaks: tuple[EditedSheetBreak, ...]
    missing_pole_ids: tuple[str, ...]
    unexpected_pole_ids: tuple[str, ...]
    duplicate_pole_ids: tuple[str, ...]

    @property
    def is_valid(self) -> bool:
        return not (
            self.missing_pole_ids
            or self.unexpected_pole_ids
            or self.duplicate_pole_ids
        )

    def to_data(self) -> dict:
        return {
            "source_path": self.source_path,
            "pole_blocks": [asdict(item) for item in self.pole_blocks],
            "sheet_breaks": [asdict(item) for item in self.sheet_breaks],
            "missing_pole_ids": list(self.missing_pole_ids),
            "unexpected_pole_ids": list(self.unexpected_pole_ids),
            "duplicate_pole_ids": list(self.duplicate_pole_ids),
        }


def inspect_edited_dxf(
    path: str | Path, expected_pole_ids: tuple[str, ...] = ()
) -> EditedDxfInspection:
    """Read PoleRoute blocks and validate their stable source identities."""
    source = Path(path)
    try:
        document = ezdxf.readfile(source)
    except (OSError, ezdxf.DXFError) as error:
        raise EditedDxfImportError(f"DXF could not be opened: {error}") from error

    poles: list[EditedPoleBlock] = []
    breaks: list[EditedSheetBreak] = []
    for entity in document.modelspace().query("INSERT"):
        name = entity.dxf.name
        if name in {"PRS_POLE", "PRS_TRANSFORMER_RACK"}:
            pole_ids = _split_text(entity.get_attrib_text("POLE_IDS"))
            if not pole_ids:
                raise EditedDxfImportError(
                    f"A {name} block is missing its POLE_IDS attribute."
                )
            try:
                quantities = tuple(
                    int(value) for value in _split_text(entity.get_attrib_text("QUANTITIES"))
                )
                station = float(entity.get_attrib_text("STATION_M"))
            except ValueError as error:
                raise EditedDxfImportError(
                    f"Pole block {' / '.join(pole_ids)} has invalid numeric metadata."
                ) from error
            poles.append(
                EditedPoleBlock(
                    name,
                    pole_ids,
                    _split_text(entity.get_attrib_text("DETAILS"), keep_empty=True),
                    quantities,
                    _split_text(entity.get_attrib_text("PHYSICAL_GROUP")),
                    station,
                    float(entity.dxf.insert.x),
                    float(entity.dxf.insert.y),
                    float(entity.dxf.get("rotation", 0.0)),
                )
            )
        elif name == "PRS_SHEET_BREAK":
            try:
                breaks.append(
                    EditedSheetBreak(
                        entity.get_attrib_text("BREAK_ID"),
                        entity.get_attrib_text("POLE_ID"),
                        float(entity.get_attrib_text("STATION_M")),
                        entity.get_attrib_text("SHEETS"),
                        float(entity.dxf.insert.x),
                        float(entity.dxf.insert.y),
                        float(entity.dxf.get("rotation", 0.0)),
                    )
                )
            except ValueError as error:
                raise EditedDxfImportError(
                    "A PRS_SHEET_BREAK block has invalid numeric metadata."
                ) from error

    if not poles:
        raise EditedDxfImportError(
            "No PRS_POLE or PRS_TRANSFORMER_RACK blocks were found. "
            "Export a new CAD Master from this version before importing it."
        )

    actual = [pole_id for block in poles for pole_id in block.pole_ids]
    expected = set(expected_pole_ids)
    actual_set = set(actual)
    duplicates = sorted({pole_id for pole_id in actual if actual.count(pole_id) > 1})
    return EditedDxfInspection(
        str(source.resolve()),
        tuple(poles),
        tuple(sorted(breaks, key=lambda item: item.station_metres)),
        tuple(sorted(expected - actual_set)),
        tuple(sorted(actual_set - expected)) if expected else (),
        tuple(duplicates),
    )


def _split_text(value: str, *, keep_empty: bool = False) -> tuple[str, ...]:
    values = tuple(part.strip() for part in (value or "").split("|"))
    return values if keep_empty else tuple(part for part in values if part)
