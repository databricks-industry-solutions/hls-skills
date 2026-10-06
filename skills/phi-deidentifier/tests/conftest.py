"""Self-contained fixture: load THIS skill's scorers + objective (siblings in tests/).

No cross-skill machinery — the cohort and de-id skills each own their measurement code, so
this loads only the two modules next to it, popping any prior `scorers`/`objective` from
sys.modules first so a repo-wide `pytest` run of both skills does not collide.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent


def _load_pair():
    sys.modules.pop("scorers", None)
    sys.modules.pop("objective", None)
    sys.path.insert(0, str(_DIR))
    try:
        def _load(name: str, filename: str):
            spec = importlib.util.spec_from_file_location(name, _DIR / filename)
            mod = importlib.util.module_from_spec(spec)
            sys.modules[name] = mod  # register so objective's `from scorers import ...` resolves
            spec.loader.exec_module(mod)
            return mod
        scorers = _load("scorers", "scorers.py")
        objective = _load("objective", "objective.py")
    finally:
        sys.path.remove(str(_DIR))
    return scorers, objective


@pytest.fixture(scope="module")
def deid():
    return _load_pair()
