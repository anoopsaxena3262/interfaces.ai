from __future__ import annotations

import pytest

from interfaces_ai.schema.registry import reset_native


@pytest.fixture(autouse=True)
def _reset_ledgers() -> None:
    reset_native()
    yield
    reset_native()
