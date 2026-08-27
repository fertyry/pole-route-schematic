"""AutoCAD integration boundaries."""

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
    "AutoCADConnection", "AutoCADConnectionError", "CadReadbackError", "ComCadGateway",
    "build_pole_overlay_plan", "read_latest_pole_offset", "read_latest_route",
    "read_managed_pole_positions", "update_managed_poles",
]
