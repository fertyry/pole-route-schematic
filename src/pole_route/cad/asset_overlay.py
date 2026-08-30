"""Plan and reconcile confirmed GIS assets in a locked CAD drawing."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from math import cos, isclose, radians, sin
from typing import Protocol

from pole_route.cad.readback import CadManagedPole, CadReadbackError
from pole_route.domain.pea_asset import (
    AssetMatchState,
    PEAAsset,
    PEAAssetMatch,
    PEAAssetType,
)

ASSET_BLOCKS = {
    PEAAssetType.TRANSFORMER: "PRS_ASSET_TRANSFORMER",
    PEAAssetType.SWITCH: "PRS_ASSET_SWITCH",
}


@dataclass(frozen=True, slots=True)
class AssetPoleResolution:
    """Map a reviewed pole source key to the canonical active CAD pole."""

    pole_source_key: str
    physical_pole_id: str | None
    included: bool = True


@dataclass(frozen=True, slots=True)
class CadManagedAsset:
    stable_asset_id: str
    asset_type: PEAAssetType
    confirmed_pole_id: str
    source_provider: str
    source_asset_id: str
    x: float
    y: float
    rotation_degrees: float

    @property
    def block_name(self) -> str:
        return ASSET_BLOCKS[self.asset_type]

    @property
    def layer_name(self) -> str:
        return self.block_name


@dataclass(frozen=True, slots=True)
class CadAssetDiagnostic:
    asset_id: str
    reason: str


@dataclass(frozen=True, slots=True)
class CadAssetPlan:
    assets: tuple[CadManagedAsset, ...]
    confirmed_count: int
    diagnostics: tuple[CadAssetDiagnostic, ...]


@dataclass(frozen=True, slots=True)
class CadAssetUpdateResult:
    confirmed_count: int
    created: int
    updated: int
    removed: int
    unchanged: int
    diagnostics: tuple[CadAssetDiagnostic, ...]


class CadAssetGateway(Protocol):
    def managed_poles(self) -> tuple[CadManagedPole, ...]: ...
    def managed_assets(self) -> tuple[CadManagedAsset, ...]: ...
    def create_managed_asset(self, asset: CadManagedAsset) -> None: ...
    def update_managed_asset(
        self, existing: CadManagedAsset, desired: CadManagedAsset
    ) -> None: ...
    def delete_managed_asset(self, asset: CadManagedAsset) -> None: ...


def build_asset_overlay_plan(
    assets: Iterable[PEAAsset],
    matches: Iterable[PEAAssetMatch],
    pole_resolutions: Iterable[AssetPoleResolution],
    cad_poles: Iterable[CadManagedPole],
) -> CadAssetPlan:
    """Build deterministic CAD presentation from confirmed relationships only."""

    asset_by_id = {item.stable_id: item for item in assets}
    resolution_by_key = {item.pole_source_key: item for item in pole_resolutions}
    cad_by_physical: dict[str, CadManagedPole] = {}
    for pole in cad_poles:
        for physical_id in pole.physical_ids:
            if physical_id in cad_by_physical:
                raise CadReadbackError(
                    f"Physical pole identity appears more than once in CAD: {physical_id}"
                )
            cad_by_physical[physical_id] = pole

    confirmed_count = 0
    diagnostics: list[CadAssetDiagnostic] = []
    eligible: list[tuple[PEAAsset, AssetPoleResolution, CadManagedPole]] = []
    for match in sorted(matches, key=lambda item: item.asset_id):
        asset = asset_by_id.get(match.asset_id)
        if match.state is not AssetMatchState.CONFIRMED:
            continue
        confirmed_count += 1
        if asset is None:
            diagnostics.append(CadAssetDiagnostic(match.asset_id, "asset record is missing"))
            continue
        if not match.included:
            diagnostics.append(CadAssetDiagnostic(asset.stable_id, "asset is excluded"))
            continue
        if not asset.source_present:
            diagnostics.append(CadAssetDiagnostic(asset.stable_id, "asset is missing from source"))
            continue
        if asset.asset_type not in ASSET_BLOCKS:
            diagnostics.append(CadAssetDiagnostic(asset.stable_id, "asset type is unsupported for CAD"))
            continue
        if not match.confirmed_pole_key:
            diagnostics.append(CadAssetDiagnostic(asset.stable_id, "confirmed pole reference is missing"))
            continue
        resolution = resolution_by_key.get(match.confirmed_pole_key)
        if resolution is None or not resolution.physical_pole_id:
            diagnostics.append(CadAssetDiagnostic(asset.stable_id, "confirmed pole cannot be resolved"))
            continue
        if not resolution.included:
            diagnostics.append(CadAssetDiagnostic(asset.stable_id, "confirmed pole is excluded"))
            continue
        cad_pole = cad_by_physical.get(resolution.physical_pole_id)
        if cad_pole is None:
            diagnostics.append(CadAssetDiagnostic(asset.stable_id, "confirmed pole is not present in CAD"))
            continue
        eligible.append((asset, resolution, cad_pole))

    grouped: dict[str, list[tuple[PEAAsset, AssetPoleResolution, CadManagedPole]]] = {}
    for item in eligible:
        grouped.setdefault(item[1].physical_pole_id or "", []).append(item)

    planned: list[CadManagedAsset] = []
    for physical_id in sorted(grouped):
        ordered = sorted(grouped[physical_id], key=lambda item: (item[0].asset_type.value, item[0].stable_id))
        for slot, (asset, resolution, pole) in enumerate(ordered):
            distance = 3.0 + slot * 2.5
            angle = radians(pole.rotation_degrees)
            planned.append(CadManagedAsset(
                asset.stable_id,
                asset.asset_type,
                resolution.physical_pole_id or "",
                asset.source_provider,
                asset.source_asset_id,
                pole.x - sin(angle) * distance,
                pole.y + cos(angle) * distance,
                pole.rotation_degrees,
            ))
    return CadAssetPlan(
        tuple(sorted(planned, key=lambda item: item.stable_asset_id)),
        confirmed_count,
        tuple(diagnostics),
    )


def update_managed_assets(
    gateway: CadAssetGateway,
    plan: CadAssetPlan,
) -> CadAssetUpdateResult:
    """Incrementally reconcile only PoleRoute-managed asset entities."""

    desired = {item.stable_asset_id: item for item in plan.assets}
    if len(desired) != len(plan.assets):
        raise CadReadbackError("Asset CAD plan contains duplicate stable identities.")
    current_items = gateway.managed_assets()
    current: dict[str, CadManagedAsset] = {}
    for item in current_items:
        if not item.stable_asset_id or item.stable_asset_id in current:
            raise CadReadbackError("Managed CAD asset metadata is missing or duplicated.")
        current[item.stable_asset_id] = item

    created = updated = removed = unchanged = 0
    diagnostics = list(plan.diagnostics)
    for stable_id in sorted(desired):
        wanted = desired[stable_id]
        existing = current.get(stable_id)
        try:
            if existing is None:
                gateway.create_managed_asset(wanted)
                created += 1
            elif _same_managed_asset(existing, wanted):
                unchanged += 1
            else:
                gateway.update_managed_asset(existing, wanted)
                updated += 1
        except CadReadbackError as error:
            diagnostics.append(CadAssetDiagnostic(stable_id, f"CAD update failed: {error}"))

    for stable_id in sorted(set(current) - set(desired)):
        try:
            gateway.delete_managed_asset(current[stable_id])
            removed += 1
        except CadReadbackError as error:
            diagnostics.append(CadAssetDiagnostic(stable_id, f"CAD removal failed: {error}"))

    return CadAssetUpdateResult(
        plan.confirmed_count, created, updated, removed, unchanged, tuple(diagnostics)
    )


def _same_managed_asset(existing: CadManagedAsset, desired: CadManagedAsset) -> bool:
    """Compare managed state while tolerating harmless COM float round-trips."""

    return (
        existing.stable_asset_id == desired.stable_asset_id
        and existing.asset_type == desired.asset_type
        and existing.confirmed_pole_id == desired.confirmed_pole_id
        and existing.source_provider == desired.source_provider
        and existing.source_asset_id == desired.source_asset_id
        and isclose(existing.x, desired.x, rel_tol=0.0, abs_tol=1e-7)
        and isclose(existing.y, desired.y, rel_tol=0.0, abs_tol=1e-7)
        and isclose(existing.rotation_degrees, desired.rotation_degrees, rel_tol=0.0, abs_tol=1e-7)
    )
