from pole_route import __version__


def test_development_version_is_declared() -> None:
    assert __version__ == "0.1.0.dev0"

