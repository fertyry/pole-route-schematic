"""Small COM adapter for PoleRoute's locked AutoCAD document."""

from __future__ import annotations

from math import degrees, radians

from pole_route.cad.readback import CadGateway, CadManagedPole, CadReadbackError


class ComCadGateway(CadGateway):
    def __init__(self, document) -> None:
        self.document = document

    def polylines(self, layer: str) -> tuple[tuple[tuple[float, float], ...], ...]:
        found = []
        for entity in self.document.ModelSpace:
            if str(getattr(entity, "Layer", "")).casefold() != layer.casefold():
                continue
            coordinates = tuple(getattr(entity, "Coordinates", ()))
            if len(coordinates) >= 4:
                found.append(tuple((float(coordinates[i]), float(coordinates[i + 1]))
                                   for i in range(0, len(coordinates) - 1, 2)))
        return tuple(found)

    def managed_poles(self) -> tuple[CadManagedPole, ...]:
        result = []
        for entity in self.document.ModelSpace:
            name = str(getattr(entity, "EffectiveName", getattr(entity, "Name", "")))
            if name not in {"PRS_POLE", "PRS_TRANSFORMER_RACK"}:
                continue
            attributes = _attributes(entity)
            point = tuple(entity.InsertionPoint)
            result.append(CadManagedPole(
                name,
                _split(attributes.get("POLE_IDS", "")),
                _split(attributes.get("PHYSICAL_IDS", attributes.get("PHYSICAL_GROUP", ""))),
                _split(attributes.get("P_LABELS", "")),
                float(point[0]), float(point[1]),
                degrees(float(getattr(entity, "Rotation", 0.0))),
            ))
        return tuple(result)

    def replace_managed_poles(self, poles: tuple[CadManagedPole, ...]) -> None:
        # Validate block definitions before deleting anything.  This makes a missing
        # PRS block a safe failure instead of a partially destructive update.
        block_names = {str(block.Name) for block in self.document.Blocks}
        missing = {pole.block_name for pole in poles} - block_names
        if missing:
            raise CadReadbackError("Locked drawing is missing block definition(s): " + ", ".join(sorted(missing)))
        existing = [entity for entity in self.document.ModelSpace
                    if str(getattr(entity, "EffectiveName", getattr(entity, "Name", "")))
                    in {"PRS_POLE", "PRS_TRANSFORMER_RACK"}]
        created = []
        try:
            for pole in poles:
                entity = self.document.ModelSpace.InsertBlock(
                    (pole.x, pole.y, 0.0), pole.block_name, 1.0, 1.0, 1.0,
                    radians(pole.rotation_degrees)
                )
                values = {
                    "POLE_IDS": "|".join(pole.source_ids),
                    "PHYSICAL_GROUP": "|".join(pole.physical_ids),
                    "PHYSICAL_IDS": "|".join(pole.physical_ids),
                    "P_LABELS": "|".join(pole.p_labels),
                }
                for attribute in entity.GetAttributes():
                    tag = str(attribute.TagString).upper()
                    if tag in values:
                        attribute.TextString = values[tag]
                created.append(entity)
        except Exception as error:
            for entity in created:
                try:
                    entity.Delete()
                except Exception:
                    pass
            raise CadReadbackError(f"AutoCAD could not create the pole overlay: {error}") from error
        for entity in existing:
            entity.Delete()


def _attributes(entity) -> dict[str, str]:
    if not bool(getattr(entity, "HasAttributes", False)):
        return {}
    return {str(item.TagString).upper(): str(item.TextString) for item in entity.GetAttributes()}


def _split(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split("|") if item.strip())
