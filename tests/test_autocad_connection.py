from types import SimpleNamespace

import pytest

from pole_route.cad.autocad_connection import AutoCADConnection, AutoCADConnectionError


def _doc(name):
    return SimpleNamespace(Name=name, FullName=f"D:/CAD/{name}")


def test_connection_locks_selected_drawing_not_active_document() -> None:
    first, second = _doc("one.dwg"), _doc("two.dwg")
    app = SimpleNamespace(Documents=[first, second], ActiveDocument=first)
    connection = AutoCADConnection(app)
    connection.select(second.FullName)
    app.ActiveDocument = first
    assert connection.target_document is second


def test_closed_target_disconnects_safely() -> None:
    target = _doc("one.dwg")
    app = SimpleNamespace(Documents=[target])
    connection = AutoCADConnection(app)
    connection.select(target.FullName)
    app.Documents.clear()
    assert not connection.connected
    with pytest.raises(AutoCADConnectionError):
        connection.target_document
