import os
import numpy as np
import pytest

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


@pytest.fixture(scope="session")
def fixtures_dir():
    return FIX


def canvas(w=400, h=300):
    return np.full((h, w), 255, np.uint8)
