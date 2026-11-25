from __future__ import annotations

import pytest

from sra.lab.study import build_world, load_json


@pytest.fixture(scope="session")
def product() -> dict:
    return load_json("product.json")


@pytest.fixture(scope="session")
def world(product):
    return build_world(7, "test", product)
