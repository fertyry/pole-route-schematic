"""AutoCAD integration boundaries."""

from pole_route.cad.asset_overlay import (
    AssetPoleResolution,
    CadAssetDiagnostic,
    CadAssetPlan,
    CadAssetUpdateResult,
    CadManagedAsset,
    build_asset_overlay_plan,
    update_managed_assets,
)
from pole_route.cad.autocad_connection import AutoCADConnection, AutoCADConnectionError
from pole_route.cad.com_gateway import ComCadGateway
from pole_route.cad.readback import (
    CadReadbackError,
    build_pole_overlay_plan,
    read_latest_pole_offset,
    read_latest_route,
    read_managed_pole_positions,
    update_managed_poles,
)

__all__ = [
    "AssetPoleResolution", "AutoCADConnection", "AutoCADConnectionError",
    "CadAssetDiagnostic", "CadAssetPlan", "CadAssetUpdateResult", "CadManagedAsset",
    "CadReadbackError", "ComCadGateway", "build_asset_overlay_plan",
    "build_pole_overlay_plan", "read_latest_pole_offset", "read_latest_route",
    "read_managed_pole_positions", "update_managed_assets", "update_managed_poles",
]
