import copy
import json
from pathlib import Path

import pytest

EXAMPLES = Path(__file__).resolve().parents[1] / "spec" / "examples"


def example(name: str) -> dict:
    """A parsed copy of one canonical example record, safe to mutate."""
    return copy.deepcopy(json.loads((EXAMPLES / name).read_bytes()))


@pytest.fixture
def child() -> dict:
    return example("fbm_recon.tif.gprv")


@pytest.fixture
def parent() -> dict:
    return example("fbm_roi.npz.gprv")
