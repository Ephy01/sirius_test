from __future__ import annotations

import pytest

from app.tasks.modules import load_task_modules


@pytest.fixture(autouse=True)
def _forget_task_modules():
    """Families loaded from modules live in a process-wide registry; drop them after each test."""

    yield
    load_task_modules(None)
