"""Small COM adapter for PoleRoute's locked AutoCAD document."""

from __future__ import annotations

from math import degrees, radians
from time import sleep

from pole_route.cad.asset_overlay import ASSET_BLOCKS, CadManagedAsset
from pole_route.cad.readback import CadGateway, CadManagedPole, CadReadbackError
from pole_route.domain.pea_asset import PEAAssetType


class ComCadGateway(CadGateway):
    def __init__(self, document) -> None:
        self.document = document

    def polylines(self, layer: str) -> tuple[tuple[tuple[float, float], ...], ...]:
        found = []
        for entity in _collection_items(self.document.ModelSpace):
            if str(getattr(entity, "Layer", "")).casefold() != layer.casefold():
                continue
            coordinates = tuple(getattr(entity, "Coordinates", ()))
            if len(coordinates) >= 4:
                found.append(tuple((float(coordinates[i]), float(coordinates[i + 1]))
                                   for i in range(0, len(coordinates) - 1, 2)))
        return tuple(found)

    def managed_poles(self) -> tuple[CadManagedPole, ...]:
        result = []
        for entity in _collection_items(self.document.ModelSpace):
            name = str(getattr(entity, "EffectiveName", getattr(entity, "Name", "")))
            if name not in {"PRS_POLE", "PRS_TRANSFORMER_RACK"}:
                continue
            attributes = _attributes(entity)
            point = _point_tuple(entity.InsertionPoint)
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
        block_names = {
            str(block.Name) for block in _collection_items(self.document.Blocks)
        }
        missing = {pole.block_name for pole in poles} - block_names
        if missing:
            raise CadReadbackError("Locked drawing is missing block definition(s): " + ", ".join(sorted(missing)))
        existing = [entity for entity in _collection_items(self.document.ModelSpace)
                    if str(getattr(entity, "EffectiveName", getattr(entity, "Name", "")))
                    in {"PRS_POLE", "PRS_TRANSFORMER_RACK"}]
        created = []
        try:
            for pole in poles:
                entity = self.document.ModelSpace.InsertBlock(
                    _com_point(pole.x, pole.y), pole.block_name, 1.0, 1.0, 1.0,
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
                except Exception:  # noqa: BLE001, S110 - best-effort COM rollback
                    pass
            raise CadReadbackError(f"AutoCAD could not create the pole overlay: {error}") from error
        for entity in existing:
            entity.Delete()

    def managed_assets(self) -> tuple[CadManagedAsset, ...]:
        result = []
        asset_blocks = set(ASSET_BLOCKS.values())
        for entity in _collection_items(self.document.ModelSpace):
            name = str(getattr(entity, "EffectiveName", getattr(entity, "Name", "")))
            if name not in asset_blocks:
                continue
            attributes = _attributes(entity)
            try:
                asset_type = PEAAssetType(attributes.get("ASSET_TYPE", ""))
            except ValueError as error:
                raise CadReadbackError(
                    f"Managed CAD asset has invalid ASSET_TYPE metadata: {name}"
                ) from error
            point = _point_tuple(entity.InsertionPoint)
            result.append(CadManagedAsset(
                attributes.get("ASSET_ID", ""),
                asset_type,
                attributes.get("POLE_ID", ""),
                attributes.get("SOURCE", ""),
                attributes.get("SOURCE_ID", ""),
                float(point[0]),
                float(point[1]),
                degrees(float(getattr(entity, "Rotation", 0.0))),
            ))
        return tuple(result)

    def create_managed_asset(self, asset: CadManagedAsset) -> None:
        try:
            self._ensure_asset_definitions()
            entity = self.document.ModelSpace.InsertBlock(
                _com_point(asset.x, asset.y), asset.block_name, 1.0, 1.0, 1.0,
                radians(asset.rotation_degrees),
            )
            entity.Layer = asset.layer_name
            _set_asset_attributes(entity, asset)
        except Exception as error:
            raise CadReadbackError(
                f"AutoCAD could not create managed asset {asset.stable_asset_id}: {error}"
            ) from error

    def update_managed_asset(
        self, existing: CadManagedAsset, desired: CadManagedAsset
    ) -> None:
        entity = self._asset_entity(existing.stable_asset_id)
        if existing.block_name != desired.block_name:
            self.create_managed_asset(desired)
            try:
                entity.Delete()
            except Exception as error:
                # Avoid leaving two managed identities if replacement cleanup failed.
                replacement = self._asset_entity(desired.stable_asset_id, newest=True)
                try:
                    replacement.Delete()
                except Exception:  # noqa: BLE001, S110 - best-effort COM rollback
                    pass
                raise CadReadbackError(
                    f"AutoCAD could not replace managed asset {desired.stable_asset_id}: {error}"
                ) from error
            return
        try:
            entity.InsertionPoint = _com_point(desired.x, desired.y)
            entity.Rotation = radians(desired.rotation_degrees)
            entity.Layer = desired.layer_name
            _set_asset_attributes(entity, desired)
        except Exception as error:
            raise CadReadbackError(
                f"AutoCAD could not update managed asset {desired.stable_asset_id}: {error}"
            ) from error

    def delete_managed_asset(self, asset: CadManagedAsset) -> None:
        try:
            self._asset_entity(asset.stable_asset_id).Delete()
        except Exception as error:
            raise CadReadbackError(
                f"AutoCAD could not remove managed asset {asset.stable_asset_id}: {error}"
            ) from error

    def _asset_entity(self, stable_id: str, *, newest: bool = False):
        found = [
            entity for entity in _collection_items(self.document.ModelSpace)
            if str(getattr(entity, "EffectiveName", getattr(entity, "Name", "")))
            in set(ASSET_BLOCKS.values())
            and _attributes(entity).get("ASSET_ID") == stable_id
        ]
        if not found:
            raise CadReadbackError(f"Managed CAD asset was not found: {stable_id}")
        if not newest and len(found) != 1:
            raise CadReadbackError(f"Managed CAD asset identity is duplicated: {stable_id}")
        return found[-1]

    def _ensure_asset_definitions(self) -> None:
        layer_names = {
            str(layer.Name) for layer in _collection_items(self.document.Layers)
        }
        for name in ASSET_BLOCKS.values():
            if name not in layer_names:
                self.document.Layers.Add(name)
        block_names = {
            str(block.Name) for block in _collection_items(self.document.Blocks)
        }
        if ASSET_BLOCKS[PEAAssetType.TRANSFORMER] not in block_names:
            block = self.document.Blocks.Add(_com_point(0.0, 0.0), ASSET_BLOCKS[PEAAssetType.TRANSFORMER])
            block.AddCircle(_com_point(0.0, 0.0), 1.2)
            block.AddCircle(_com_point(0.0, 0.0), 0.6)
            _add_asset_attributes(block)
        if ASSET_BLOCKS[PEAAssetType.SWITCH] not in block_names:
            block = self.document.Blocks.Add(_com_point(0.0, 0.0), ASSET_BLOCKS[PEAAssetType.SWITCH])
            block.AddCircle(_com_point(0.0, 0.0), 1.0)
            block.AddLine(_com_point(-0.8, -0.8), _com_point(0.8, 0.8))
            block.AddLine(_com_point(-0.8, 0.8), _com_point(0.8, -0.8))
            _add_asset_attributes(block)


def _attributes(entity) -> dict[str, str]:
    if not _retry_com_read(lambda: bool(getattr(entity, "HasAttributes", False))):
        return {}
    attributes = _retry_com_read(entity.GetAttributes)
    return {
        _retry_com_read(lambda item=item: str(item.TagString).upper()):
        _retry_com_read(lambda item=item: str(item.TextString))
        for item in attributes
    }


def _collection_items(collection) -> tuple:
    return _retry_com_read(lambda: tuple(collection))


def _retry_com_read(operation, *, attempts: int = 8):
    """Retry read-only COM calls while AutoCAD briefly rejects incoming calls."""

    for attempt in range(attempts):
        try:
            return operation()
        except Exception as error:
            hresult = getattr(error, "hresult", error.args[0] if error.args else None)
            if hresult == -2147418111 and attempt < attempts - 1:
                sleep(0.1 * (attempt + 1))
                continue
            raise CadReadbackError(f"AutoCAD COM read failed: {error}") from error
    raise AssertionError("unreachable")


def _com_point(x: float, y: float):
    """Return the explicit SAFEARRAY AutoCAD requires for 3-D point arguments."""

    import pythoncom
    from win32com.client import VARIANT

    return VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, (float(x), float(y), 0.0))


def _point_tuple(value) -> tuple[float, ...]:
    """Normalize a COM SAFEARRAY or the VARIANT retained by a test adapter."""

    return tuple(getattr(value, "value", value))


def _split(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split("|") if item.strip())


def _add_asset_attributes(block) -> None:
    for index, tag in enumerate(
        ("MANAGED_KIND", "ASSET_ID", "ASSET_TYPE", "POLE_ID", "SOURCE", "SOURCE_ID")
    ):
        block.AddAttribute(
            0.1, 1, tag, _com_point(0.0, -2.0 - index * 0.2), tag, ""
        )


def _set_asset_attributes(entity, asset: CadManagedAsset) -> None:
    values = {
        "MANAGED_KIND": "ASSET",
        "ASSET_ID": asset.stable_asset_id,
        "ASSET_TYPE": asset.asset_type.value,
        "POLE_ID": asset.confirmed_pole_id,
        "SOURCE": asset.source_provider,
        "SOURCE_ID": asset.source_asset_id,
    }
    for attribute in entity.GetAttributes():
        tag = str(attribute.TagString).upper()
        if tag in values:
            attribute.TextString = values[tag]
