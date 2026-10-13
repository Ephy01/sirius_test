"""What the text of a plugin may use: a few standard modules and the ``sirius_gate`` package.

The check reads the text without running it. It stops honest mistakes and plain
misuse, and it is not a sandbox: a plugin reaches the shared platform only after
an organizer has read it.
"""

from __future__ import annotations

import ast
from pathlib import Path

from .errors import PluginError

ALLOWED_MODULES = frozenset(
    {
        'bisect',
        'cmath',
        'collections',
        'copy',
        'dataclasses',
        'decimal',
        'enum',
        'fractions',
        'functools',
        'heapq',
        'itertools',
        'json',
        'math',
        'numbers',
        'operator',
        'random',
        're',
        'statistics',
        'string',
        'textwrap',
        'typing',
        'sirius_gate',
    }
)
FORBIDDEN_NAMES = frozenset(
    {
        'open',
        'eval',
        'exec',
        'compile',
        'input',
        'breakpoint',
        'globals',
        'locals',
        'vars',
        'getattr',
        'setattr',
    }
)


def _hidden(name: str) -> bool:
    return name.startswith('__')


def _imported(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if isinstance(node, ast.ImportFrom) and node.level == 0:
        return [node.module or '']
    return []


def _problem(node: ast.AST) -> str | None:
    for module in _imported(node):
        if module.split('.')[0] not in ALLOWED_MODULES:
            allowed = ', '.join(sorted(ALLOWED_MODULES - {'sirius_gate'}))
            return (
                f'модуль {module} в плагине использовать нельзя. '
                f'Разрешены пакет sirius_gate и стандартные модули: {allowed}'
            )
    name = node.id if isinstance(node, ast.Name) else node.attr if isinstance(node, ast.Attribute) else ''
    if isinstance(node, ast.Name) and name in FORBIDDEN_NAMES:
        return f'функцию {name} в плагине использовать нельзя'
    if _hidden(name):
        return f'имя {name} в плагине использовать нельзя'
    return None


def check_source(source: str, filename: str) -> None:
    """Raise ``PluginError`` with the line of the first thing a plugin is not allowed to use."""

    for node in ast.walk(ast.parse(source, filename)):
        problem = _problem(node)
        if problem:
            raise PluginError(f'{problem}\n{Path(filename).name}, строка {node.lineno}')
