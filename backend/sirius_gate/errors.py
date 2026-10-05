"""Telling a task author what went wrong in the code of a task."""

from __future__ import annotations

import sysconfig
import traceback
from pathlib import Path

_LIBRARIES = (
    str(Path(__file__).resolve().parent),
    *{sysconfig.get_paths()[name] for name in ('stdlib', 'platstdlib', 'purelib', 'platlib')},
)


def _in_task_code(frame: traceback.FrameSummary) -> bool:
    name = frame.filename
    return not (name.startswith('<') or name.startswith(_LIBRARIES) or '.zip' in name)


def explain(error: BaseException) -> str:
    """The error with the place in the task file it came from."""

    summary = f'{type(error).__name__}: {error}'
    if isinstance(error, SyntaxError) and error.lineno:
        return (
            f'{type(error).__name__}: {error.msg}\n{Path(error.filename or "").name}, строка {error.lineno}'
        )
    frames = [frame for frame in traceback.extract_tb(error.__traceback__) if _in_task_code(frame)]
    if not frames:
        return summary
    place = frames[-1]
    return f'{summary}\n{Path(place.filename).name}, строка {place.lineno}, функция {place.name}'
