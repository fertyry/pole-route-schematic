"""Semantic definitions for reusable schematic blocks."""

from dataclasses import dataclass
from enum import StrEnum


class BlockType(StrEnum):
    SIDE_ROAD = "side_road"
    T_JUNCTION = "t_junction"
    CROSSROAD = "crossroad"
    VEHICLE_BRIDGE = "vehicle_bridge"
    FOOTBRIDGE = "footbridge"


@dataclass(frozen=True, slots=True)
class BlockDefinition:
    type: BlockType
    label: str
    category: str
    snap_to_road: bool


BLOCK_CATALOG = (
    BlockDefinition(BlockType.SIDE_ROAD, "Side road", "Road", True),
    BlockDefinition(BlockType.T_JUNCTION, "T-junction", "Road", True),
    BlockDefinition(BlockType.CROSSROAD, "Crossroad", "Road", True),
    BlockDefinition(BlockType.VEHICLE_BRIDGE, "Vehicle bridge", "Crossing", False),
    BlockDefinition(BlockType.FOOTBRIDGE, "Footbridge", "Crossing", False),
)


def block_definition(block_type: BlockType) -> BlockDefinition:
    return next(definition for definition in BLOCK_CATALOG if definition.type is block_type)

