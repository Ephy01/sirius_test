"""Loading task modules from a folder or from the text of one module.

A module is either ``<name>.py`` or a folder ``<name>/`` with ``task.py`` inside. It
defines ``FAMILY`` (or ``FAMILIES``) with ``TaskFamily`` records and may declare the
interface version it was written for as ``API = 1``.
"""

from __future__ import annotations

import importlib.util
import json
import linecache
import re
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

from .errors import explain
from .family import API, TaskFamily

PACKAGE = 'sirius_gate_modules'
KEY_PATTERN = re.compile(r'[a-z][a-z0-9_]{2,39}')
SMOKE_SEED = 1


@dataclass(frozen=True)
class LoadedModule:
    name: str
    path: str
    families: tuple[TaskFamily, ...] = ()
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


def _run(name: str, source: str, filename: str) -> ModuleType:
    """Execute the text of a module; ``linecache`` lets a traceback quote its lines."""

    qualified = f'{PACKAGE}.{name}'
    module = ModuleType(qualified)
    module.__file__ = filename
    linecache.cache[filename] = (len(source), None, source.splitlines(keepends=True), filename)
    sys.modules[qualified] = module
    try:
        exec(compile(source, filename, 'exec'), module.__dict__)
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


def _checked_families(module: ModuleType) -> tuple[TaskFamily, ...]:
    families = _declared_families(module)
    declared = getattr(module, 'API', API)
    if declared != API:
        raise ValueError(
            f'the module is written for interface version {declared}, the platform provides {API}'
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
    return tuple(families)


def _forget_loaded() -> None:
    for qualified in [name for name in sys.modules if name.startswith(f'{PACKAGE}.')]:
        del sys.modules[qualified]


def load_source(source: str, name: str = 'task') -> LoadedModule:
    """Load a module given as text, the way the task editor holds it."""

    _forget_loaded()
    filename = f'{name}.py'
    try:
        return LoadedModule(
            name=name, path=filename, families=_checked_families(_run(name, source, filename))
        )
    except Exception as error:
        return LoadedModule(name=name, path=filename, error=explain(error))


def load_directory(directory: Path) -> list[LoadedModule]:
    """Load every module of a folder. A module that fails is reported and skipped."""

    _forget_loaded()
    loaded = []
    for name, path in _candidates(directory):
        try:
            loaded.append(
                LoadedModule(name=name, path=str(path), families=_checked_families(_import(name, path)))
            )
        except Exception as error:
            loaded.append(LoadedModule(name=name, path=str(path), error=explain(error)))
    return loaded
