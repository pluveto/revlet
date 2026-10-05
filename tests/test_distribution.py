"""Check the type information shipped with the installed package."""

from importlib.resources import files

import pytest


@pytest.mark.parametrize("filename", ["__init__.pyi", "py.typed"])
def test_type_information_is_available(filename: str) -> None:
    assert files("revlet").joinpath(filename).is_file()
