"""The migration lock builder is exercised through test_check_migrations."""

from __future__ import annotations

import pytest

from shearstud.tools import build_lock

pytestmark = pytest.mark.tools


def test_the_shipped_lock_is_current() -> None:
    assert build_lock.is_current()
