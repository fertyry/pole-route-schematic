"""Source-neutral PEA GIS assets and explicit pole-match review state."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any


class PEAAssetType(StrEnum):
    TRANSFORMER = "transformer"
    SWITCH = "switch"


class AssetMatchState(StrEnum):
    UNMATCHED = "unmatched"
    SUGGESTED = "suggested"
    AMBIGUOUS = "ambiguous"
    CONFIRMED = "confirmed"


class AssetSideRelation(StrEnum):
    SAME_SIDE = "same_side"
    OPPOSITE_SIDE = "opposite_side"
    UNCERTAIN = "uncertain"


@dataclass(frozen=True, slots=True)
class PEAAsset:
    """One auditable source asset; normalized fields remain optional."""

    stable_id: str
    source_sheet: str
    source_row: int
    asset_type: PEAAssetType
    source_asset_id: str = ""
    latitude: float | None = None
    longitude: float | None = None
    raw_attributes: Mapping[str, Any] = field(default_factory=dict)
    name: str | None = None
    raw_voltage: Any = None
    voltage_min_kv: float | None = None
    voltage_max_kv: float | None = None
    rating: str | None = None
    phase: str | None = None
    equipment_subtype: str | None = None
    status: str | None = None
    feeder_reference: str | None = None
    qc_warnings: tuple[str, ...] = ()
    source_present: bool = True

    @property
    def coordinate_valid(self) -> bool:
        return self.latitude is not None and self.longitude is not None

    @property
    def source_key(self) -> str:
        return self.stable_id


@dataclass(frozen=True, slots=True)
class AssetPoleCandidate:
    pole_source_key: str
    pole_id: str
    distance_metres: float
    pole_order: int | None = None
    pole_included: bool | None = None
    pole_qc: str = ""
    strength: str = "weak"
    side_relation: AssetSideRelation = AssetSideRelation.UNCERTAIN
    asset_route_offset_metres: float | None = None
    pole_route_offset_metres: float | None = None


@dataclass(frozen=True, slots=True)
class PEAAssetMatch:
    asset_id: str
    state: AssetMatchState = AssetMatchState.UNMATCHED
    candidates: tuple[AssetPoleCandidate, ...] = ()
    suggested_pole_key: str | None = None
    confirmed_pole_key: str | None = None
    manual_override: bool = False
    included: bool = True

    def confirm(self, pole_source_key: str) -> PEAAssetMatch:
        if pole_source_key not in {item.pole_source_key for item in self.candidates}:
            raise ValueError("Confirmed pole must be one of the reviewed candidates")
        return replace(
            self,
            state=AssetMatchState.CONFIRMED,
            confirmed_pole_key=pole_source_key,
            manual_override=pole_source_key != self.suggested_pole_key,
        )

    def clear(self) -> PEAAssetMatch:
        return replace(
            self,
            state=AssetMatchState.UNMATCHED,
            suggested_pole_key=None,
            confirmed_pole_key=None,
            manual_override=True,
        )


@dataclass(frozen=True, slots=True)
class PEAAssetMergeResult:
    assets: tuple[PEAAsset, ...]
    matches: tuple[PEAAssetMatch, ...]
    added: int
    updated: int
    missing_from_source: int


def merge_pea_assets(
    existing_assets: list[PEAAsset] | tuple[PEAAsset, ...],
    existing_matches: list[PEAAssetMatch] | tuple[PEAAssetMatch, ...],
    imported_assets: list[PEAAsset] | tuple[PEAAsset, ...],
    *,
    imported_sheets: set[str],
) -> PEAAssetMergeResult:
    """Refresh source data while preserving explicit reviewed relationships."""

    old_assets = {asset.stable_id: asset for asset in existing_assets}
    imported = {asset.stable_id: asset for asset in imported_assets}
    old_matches = {match.asset_id: match for match in existing_matches}
    merged: dict[str, PEAAsset] = {
        key: asset
        for key, asset in old_assets.items()
        if asset.source_sheet not in imported_sheets
    }
    merged.update(imported)
    missing = 0
    for key, asset in old_assets.items():
        if asset.source_sheet in imported_sheets and key not in imported:
            missing += 1
            warnings = tuple(dict.fromkeys((*asset.qc_warnings, "Not present in latest import")))
            merged[key] = replace(asset, source_present=False, qc_warnings=warnings)
    ordered = tuple(sorted(merged.values(), key=lambda item: item.stable_id))
    matches = tuple(
        old_matches.get(asset.stable_id, PEAAssetMatch(asset.stable_id))
        for asset in ordered
    )
    return PEAAssetMergeResult(
        ordered,
        matches,
        sum(key not in old_assets for key in imported),
        sum(key in old_assets for key in imported),
        missing,
    )
