"""Task modules: families that live outside the platform and are picked up from a directory.

A module is either ``<name>.py`` or a folder ``<name>/`` with ``task.py`` inside. It
defines ``FAMILY`` (or ``FAMILIES``) with ``TaskFamily`` records and may declare the
interface version it was written for as ``API = 1``.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import re
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

from sirius_gate.family import TaskFamily

from .registry import register_module_family, unregister_module_families

API_VERSION = 1
PACKAGE = 'sirius_gate_modules'
KEY_PATTERN = re.compile(r'[a-z][a-z0-9_]{2,39}')
SMOKE_SEED = 1

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LoadedModule:
    name: str
    path: str
    families: tuple[str, ...] = ()
    error: str | None = None


def _candidates(directory: Path) -> list[tuple[str, Path]]:
    found = []
    for entry in sorted(directory.iterdir()):
        if entry.name.startswith(('.', '_')):
            continue
        if entry.is_file() and entry.suffix == '.py':
            found.append((entry.stem, entry))
        elif entry.is_dir() and (entry / 'task.py').is_file():
            found.append((entry.name, entry / 'task.py'))
    return found


@contextmanager
def _without_bytecode_cache() -> Iterator[None]:
    """Keeps compiled files out of the authors' folder.

    The cache is checked by the second of the last change and the file size, so an
    edit of the same length made right after a reload would run the old code.
    """

    previous, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        yield
    finally:
        sys.dont_write_bytecode = previous


def _import(name: str, path: Path) -> ModuleType:
    qualified = f'{PACKAGE}.{name}'
    search = [str(path.parent)] if path.name == 'task.py' else None
    spec = importlib.util.spec_from_file_location(qualified, path, submodule_search_locations=search)
    module = importlib.util.module_from_spec(spec)
    sys.modules[qualified] = module
    try:
        with _without_bytecode_cache():
            spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(qualified, None)
        raise
    return module


def _declared_families(module: ModuleType) -> list[TaskFamily]:
    declared = getattr(module, 'FAMILIES', None)
    families = list(declared) if declared is not None else [getattr(module, 'FAMILY', None)]
    if not families or any(not isinstance(family, TaskFamily) for family in families):
        raise ValueError('the module must define FAMILY (or FAMILIES) built with TaskFamily')
    return families


def _smoke_test(family: TaskFamily) -> None:
    """One generated task must be a reproducible pair of JSON objects the client can open."""

    first = family.generate(SMOKE_SEED, 1, {})
    if not (isinstance(first, tuple) and len(first) == 2 and all(isinstance(part, dict) for part in first)):
        raise ValueError('generate must return (public_state, private_state) as two dicts')
    encoded = json.dumps(first, ensure_ascii=False, allow_nan=False)
    if json.dumps(family.generate(SMOKE_SEED, 1, {}), ensure_ascii=False, allow_nan=False) != encoded:
        raise ValueError('generate must return the same task for the same seed and difficulty')
    public_state = first[0]
    if not isinstance(public_state.get('kind'), str) or not isinstance(public_state.get('prompt'), str):
        raise ValueError('public_state must contain text fields "kind" and "prompt"')


def _check(module: ModuleType, families: list[TaskFamily]) -> None:
    api = getattr(module, 'API', API_VERSION)
    if api != API_VERSION:
        raise ValueError(
            f'the module is written for interface version {api}, the platform provides {API_VERSION}'
        )
    keys = [family.key for family in families]
    if len(set(keys)) != len(keys):
        raise ValueError('family keys inside the module must differ')
    for family in families:
        if not KEY_PATTERN.fullmatch(family.key):
            raise ValueError(
                f'family key {family.key!r} must be 3 to 40 lowercase latin letters, digits or "_"'
            )
        _smoke_test(family)


def _load(name: str, path: Path) -> LoadedModule:
    try:
        module = _import(name, path)
        families = _declared_families(module)
        _check(module, families)
        for family in families:
            register_module_family(family, name)
    except Exception as error:
        logger.warning('Task module %s was not loaded: %s', name, error)
        return LoadedModule(name=name, path=str(path), error=f'{type(error).__name__}: {error}')
    return LoadedModule(name=name, path=str(path), families=tuple(family.key for family in families))


def load_task_modules(directory: str | None) -> list[LoadedModule]:
    """Replace the families of previously loaded modules with the ones found in ``directory``.

    A module that fails is reported and skipped, so one broken module does not
    take the platform down.
    """

    unregister_module_families()
    for qualified in [name for name in sys.modules if name.startswith(f'{PACKAGE}.')]:
        del sys.modules[qualified]
    if not directory:
        return []
    root = Path(directory).expanduser()
    if not root.is_dir():
        logger.warning('Task modules directory %s does not exist', root)
        return []
    return [_load(name, path) for name, path in _candidates(root)]
