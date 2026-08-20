"""Safe ownership helpers for PySide graphics-scene items."""

from collections.abc import Iterable

from PySide6.QtWidgets import QGraphicsItem, QGraphicsScene


_ITEM_REFS_ATTRIBUTE = "_pole_route_item_refs"


def clear_scene(scene: QGraphicsScene) -> None:
    """Release Python wrappers before Qt deletes their C++ graphics items."""
    retained = getattr(scene, _ITEM_REFS_ATTRIBUTE, None)
    if retained is not None:
        retained.clear()
        delattr(scene, _ITEM_REFS_ATTRIBUTE)
    scene.clear()


def retain_scene_items(
    scene: QGraphicsScene, items: Iterable[QGraphicsItem] | None = None
) -> None:
    """Keep Python item wrappers alive without changing the live Qt scene."""
    retained = list(items) if items is not None else scene.items()
    setattr(scene, _ITEM_REFS_ATTRIBUTE, retained)
