"""Task modules: families that live outside the platform and are picked up from a directory.

Reading and checking a module is the job of ``sirius_gate.loading``. This module
adds the loaded families to the registry of the platform.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path

from sirius_gate.loading import LoadedModule, load_directory

from .registry import register_module_families, unregister_module_families

logger = logging.getLogger(__name__)


def _registered(module: LoadedModule) -> LoadedModule:
    if module.error is None:
        try:
            register_module_families(module.families, module.name)
        except ValueError as error:
            module = replace(module, families=(), error=f'{type(error).__name__}: {error}')
    if module.error:
        logger.warning('Task module %s was not loaded: %s', module.name, module.error)
    return module


def load_task_modules(directory: str | None) -> list[LoadedModule]:
    """Replace the families of previously loaded modules with the ones found in ``directory``.

    A module that fails is reported and skipped, so one broken module does not
    take the platform down.
    """

    unregister_module_families()
    if not directory:
        return []
    root = Path(directory).expanduser()
    if not root.is_dir():
        logger.warning('Task modules directory %s does not exist', root)
        return []
    return [_registered(module) for module in load_directory(root)]
