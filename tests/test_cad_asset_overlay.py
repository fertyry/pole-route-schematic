from dataclasses import dataclass, field, replace

import pytest
from PySide6.QtWidgets import QMenu

from pole_route.cad.asset_overlay import (
    AssetPoleResolution,
    CadAssetPlan,
    CadManagedAsset,
    build_asset_overlay_plan,
    update_managed_assets,
)
from pole_route.cad.com_gateway import ComCadGateway
from pole_route.cad.readback import CadManagedPole
from pole_route.domain.pea_asset import (
    AssetMatchState,
    PEAAsset,
    PEAAssetMatch,
    PEAAssetType,
)
from pole_route.project.storage import (
    load_project_file,
    pea_asset_matches_from_data,
    pea_asset_matches_to_data,
    pea_assets_from_data,
    pea_assets_to_data,
    save_project_file,
)


def _asset(identifier="T001", kind=PEAAssetType.TRANSFORMER, **changes):
    asset = PEAAsset(
        identifier, "Assets", 2, kind, identifier, 13.0, 100.0,
        source_provider="TEST", source_file="assets.xlsx",
    )
    return replace(asset, **changes)


def _match(identifier="T001", state=AssetMatchState.CONFIRMED, pole="KEY:P010", **changes):
    match = PEAAssetMatch(
        identifier, state=state,
        confirmed_pole_key=pole if state is AssetMatchState.CONFIRMED else None,
    )
    return replace(match, **changes)


def _cad_pole(identifier="P010", x=10.0, y=20.0, rotation=0.0):
    return CadManagedPole("PRS_POLE", (identifier,), (identifier,), ("P1",), x, y, rotation)


def _plan(assets, matches, resolutions=None, poles=None):
    return build_asset_overlay_plan(
        assets,
        matches,
        resolutions or (AssetPoleResolution("KEY:P010", "P010"),),
        poles or (_cad_pole(),),
    )


@pytest.mark.parametrize(
    ("kind", "block"),
    [
        (PEAAssetType.TRANSFORMER, "PRS_ASSET_TRANSFORMER"),
        (PEAAssetType.SWITCH, "PRS_ASSET_SWITCH"),
    ],
)
def test_only_confirmed_supported_assets_are_cad_eligible(kind, block) -> None:
    plan = _plan([_asset(kind=kind)], [_match()])
    assert len(plan.assets) == 1
    assert plan.assets[0].block_name == block
    assert plan.assets[0].confirmed_pole_id == "P010"
    assert plan.assets[0].source_provider == "TEST"
    assert plan.assets[0].source_asset_id == "T001"


@pytest.mark.parametrize(
    "state",
    [AssetMatchState.SUGGESTED, AssetMatchState.AMBIGUOUS, AssetMatchState.UNMATCHED],
)
def test_unconfirmed_asset_is_not_cad_eligible(state) -> None:
    assert _plan([_asset()], [_match(state=state)]).assets == ()


def test_unsupported_missing_excluded_and_inactive_assets_are_diagnostic() -> None:
    assets = [
        _asset("OTHER", PEAAssetType.OTHER),
        _asset("MISSING"),
        _asset("EXCLUDED"),
        _asset("INACTIVE", source_present=False),
    ]
    matches = [
        _match("OTHER"),
        _match("MISSING", pole="KEY:MISSING"),
        _match("EXCLUDED", pole="KEY:EXCLUDED"),
        _match("INACTIVE"),
        _match("NO_RECORD"),
    ]
    resolutions = (
        AssetPoleResolution("KEY:P010", "P010"),
        AssetPoleResolution("KEY:EXCLUDED", "P011", included=False),
    )
    plan = _plan(assets, matches, resolutions, (_cad_pole(),))
    assert plan.assets == ()
    reasons = {item.asset_id: item.reason for item in plan.diagnostics}
    assert reasons == {
        "EXCLUDED": "confirmed pole is excluded",
        "INACTIVE": "asset is missing from source",
        "MISSING": "confirmed pole cannot be resolved",
        "NO_RECORD": "asset record is missing",
        "OTHER": "asset type is unsupported for CAD",
    }


@dataclass
class FakeAssetGateway:
    assets: dict[str, CadManagedAsset] = field(default_factory=dict)
    manual_entities: list[str] = field(default_factory=lambda: ["manual-line", "base-road"])
    created: int = 0
    updated: int = 0
    removed: int = 0

    def managed_assets(self):
        return tuple(self.assets.values())

    def create_managed_asset(self, asset):
        self.assets[asset.stable_asset_id] = asset
        self.created += 1

    def update_managed_asset(self, existing, desired):
        assert existing.stable_asset_id == desired.stable_asset_id
        self.assets[desired.stable_asset_id] = desired
        self.updated += 1

    def delete_managed_asset(self, asset):
        del self.assets[asset.stable_asset_id]
        self.removed += 1


def test_update_is_idempotent_and_never_touches_manual_or_base_cad() -> None:
    gateway = FakeAssetGateway()
    plan = _plan([_asset()], [_match()])
    first = update_managed_assets(gateway, plan)
    second = update_managed_assets(gateway, plan)
    assert (first.created, first.updated, first.removed) == (1, 0, 0)
    assert (second.created, second.updated, second.removed, second.unchanged) == (0, 0, 0, 1)
    assert len(gateway.assets) == 1
    assert gateway.manual_entities == ["manual-line", "base-road"]


def test_update_tolerates_harmless_com_float_round_trip_noise() -> None:
    plan = _plan([_asset()], [_match()])
    desired = plan.assets[0]
    gateway = FakeAssetGateway(
        assets={
            desired.stable_asset_id: replace(
                desired,
                x=desired.x + 1e-9,
                y=desired.y - 1e-9,
                rotation_degrees=desired.rotation_degrees + 1e-9,
            )
        }
    )

    result = update_managed_assets(gateway, plan)

    assert (result.created, result.updated, result.removed, result.unchanged) == (0, 0, 0, 1)


def test_changed_confirmation_moves_one_stable_managed_asset() -> None:
    gateway = FakeAssetGateway()
    first = _plan([_asset()], [_match()])
    update_managed_assets(gateway, first)
    second = _plan(
        [_asset()],
        [_match(pole="KEY:P011")],
        (AssetPoleResolution("KEY:P011", "P011"),),
        (_cad_pole("P011", 50.0, 60.0),),
    )
    result = update_managed_assets(gateway, second)
    assert (result.created, result.updated, result.removed) == (0, 1, 0)
    assert tuple(gateway.assets) == ("T001",)
    assert gateway.assets["T001"].confirmed_pole_id == "P011"
    assert (gateway.assets["T001"].x, gateway.assets["T001"].y) == pytest.approx((50, 63))


def test_confirmation_removal_removes_stale_managed_asset() -> None:
    gateway = FakeAssetGateway()
    update_managed_assets(gateway, _plan([_asset()], [_match()]))
    result = update_managed_assets(
        gateway, _plan([_asset()], [_match(state=AssetMatchState.SUGGESTED)])
    )
    assert result.removed == 1
    assert gateway.assets == {}


def test_multiple_assets_on_same_pole_use_stable_non_overlapping_slots() -> None:
    assets = [_asset("T001"), _asset("S001", PEAAssetType.SWITCH)]
    matches = [_match("T001"), _match("S001")]
    first = _plan(assets, matches)
    second = _plan(list(reversed(assets)), list(reversed(matches)))
    assert first == second
    by_id = {item.stable_asset_id: item for item in first.assets}
    assert (by_id["S001"].x, by_id["S001"].y) == pytest.approx((10, 23))
    assert (by_id["T001"].x, by_id["T001"].y) == pytest.approx((10, 25.5))


def test_source_coordinates_and_review_state_are_never_mutated() -> None:
    asset = _asset()
    match = _match()
    before = (asset, match)
    _plan([asset], [match])
    assert (asset, match) == before


def test_reconciliation_rejects_duplicate_corrupted_metadata() -> None:
    item = _plan([_asset()], [_match()]).assets[0]

    class CorruptGateway(FakeAssetGateway):
        def managed_assets(self):
            return (item, item)

    with pytest.raises(Exception, match="duplicated"):
        update_managed_assets(CorruptGateway(), CadAssetPlan((item,), 1, ()))


def test_confirmed_relationship_round_trip_rebuilds_same_cad_plan(tmp_path) -> None:
    asset, match = _asset(), _match()
    expected = _plan([asset], [match])
    path = tmp_path / "asset-cad.prs"
    save_project_file(path, {
        "pea_assets": pea_assets_to_data([asset]),
        "pea_asset_matches": pea_asset_matches_to_data([match]),
    })
    document = load_project_file(path)
    actual = _plan(
        pea_assets_from_data(document["pea_assets"]),
        pea_asset_matches_from_data(document["pea_asset_matches"]),
    )
    assert actual == expected


def test_main_window_exposes_separate_update_assets_action(qtbot) -> None:
    from pole_route.ui.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    auto_cad_menu = window.menuBar().findChild(QMenu, "autoCadMenu")
    assert window.update_cad_assets_action.text() == "Update Assets"
    assert window.update_cad_assets_action in auto_cad_menu.actions()
    assert not window.update_cad_assets_action.isEnabled()
    window.current_pea_assets = [_asset()]
    window._set_cad_actions_enabled(True)
    assert window.update_cad_assets_action.isEnabled()


class _FakeAttribute:
    def __init__(self, tag, value=""):
        self.TagString = tag
        self.TextString = value


class _FakeBlock:
    def __init__(self, name):
        self.Name = name
        self.attribute_tags = []

    def AddCircle(self, *_args):
        return None

    def AddLine(self, *_args):
        return None

    def AddAttribute(self, _height, _mode, _prompt, _point, tag, _value):
        self.attribute_tags.append(tag)


class _FakeBlocks(list):
    def Add(self, _point, name):
        block = _FakeBlock(name)
        self.append(block)
        return block


class _FakeLayers(list):
    def Add(self, name):
        layer = type("Layer", (), {"Name": name})()
        self.append(layer)
        return layer


class _FakeEntity:
    def __init__(self, owner, name, point, rotation, tags=()):
        self._owner = owner
        self.EffectiveName = name
        self.Name = name
        self.InsertionPoint = point
        self.Rotation = rotation
        self.Layer = "0"
        self.HasAttributes = bool(tags)
        self._attributes = [_FakeAttribute(tag) for tag in tags]

    def GetAttributes(self):
        return self._attributes

    def Delete(self):
        self._owner.remove(self)


class _FakeModelSpace(list):
    def __init__(self, blocks):
        super().__init__()
        self._blocks = blocks

    def InsertBlock(self, point, name, _sx, _sy, _sz, rotation):
        block = next(item for item in self._blocks if item.Name == name)
        entity = _FakeEntity(self, name, point, rotation, block.attribute_tags)
        self.append(entity)
        return entity


class _FakeDocument:
    def __init__(self):
        self.Blocks = _FakeBlocks()
        self.Layers = _FakeLayers()
        self.ModelSpace = _FakeModelSpace(self.Blocks)


def test_com_gateway_reconciles_asset_attributes_without_touching_manual_entity(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "pole_route.cad.com_gateway._com_point",
        lambda x, y: (float(x), float(y), 0.0),
    )
    document = _FakeDocument()
    manual = _FakeEntity(document.ModelSpace, "MANUAL", (1, 2, 0), 0)
    document.ModelSpace.append(manual)
    gateway = ComCadGateway(document)
    item = _plan([_asset()], [_match()]).assets[0]

    gateway.create_managed_asset(item)
    assert gateway.managed_assets() == (item,)
    moved = replace(item, x=99.0, y=88.0, confirmed_pole_id="P011")
    gateway.update_managed_asset(item, moved)
    assert gateway.managed_assets() == (moved,)
    gateway.delete_managed_asset(moved)

    assert gateway.managed_assets() == ()
    assert document.ModelSpace == [manual]
