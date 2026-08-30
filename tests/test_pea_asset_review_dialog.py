from __future__ import annotations

from pole_route.domain.pea_asset import AssetMatchState, PEAAsset, PEAAssetType
from pole_route.domain.pea_gis import PEAPoleRecord
from pole_route.geometry.pea_asset_matching import match_pea_assets
from pole_route.ui.pea_asset_review_dialog import PEAAssetReviewDialog


def _data():
    asset = PEAAsset("DS_Switch:sw-1", "DS_Switch", 2, PEAAssetType.SWITCH,
                     "SW-1", 13.0, 100.0)
    poles = [
        PEAPoleRecord("A", "DS_Pole", 2, 13.0, 100.0),
        PEAPoleRecord("B", "DS_Pole", 3, 13.0, 100.00001),
    ]
    return asset, poles


def test_review_lists_assets_and_does_not_auto_confirm(qtbot):
    asset, poles = _data(); matches = match_pea_assets([asset], poles)
    dialog = PEAAssetReviewDialog([asset], matches, poles)
    qtbot.addWidget(dialog)
    assert dialog.table.rowCount() == 1
    assert dialog.matches()[0].state is not AssetMatchState.CONFIRMED


def test_review_confirms_changes_and_clears_candidate(qtbot):
    asset, poles = _data(); matches = match_pea_assets([asset], poles)
    dialog = PEAAssetReviewDialog([asset], matches, poles)
    qtbot.addWidget(dialog); dialog.table.selectRow(0)
    selector = dialog._selectors[asset.stable_id]
    selector.setCurrentIndex(2)
    dialog._confirm_selected()
    confirmed = dialog.matches()[0]
    assert confirmed.state is AssetMatchState.CONFIRMED
    assert confirmed.confirmed_pole_key == poles[1].source_key
    assert confirmed.manual_override
    dialog.table.selectRow(0); dialog._clear_selected()
    assert dialog.matches()[0].state is AssetMatchState.UNMATCHED


def test_review_filters_asset_types_without_losing_review_state(qtbot):
    asset, poles = _data()
    transformer = PEAAsset(
        "DS_Transformer:tx-1", "DS_Transformer", 3,
        PEAAssetType.TRANSFORMER, "TX-1", 13.0, 100.0,
    )
    assets = [asset, transformer]
    matches = match_pea_assets(assets, poles)
    dialog = PEAAssetReviewDialog(assets, matches, poles)
    qtbot.addWidget(dialog)

    assert dialog.table.rowCount() == 2
    dialog.type_filter.setCurrentIndex(dialog.type_filter.findData("switch"))
    assert dialog.table.rowCount() == 1
    assert dialog.table.item(0, 2).text() == "switch"
    assert len(dialog.matches()) == 2
