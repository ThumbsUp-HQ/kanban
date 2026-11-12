from database import __version__


def test_database_smoke() -> None:
    assert __version__ == "0.0.0"
