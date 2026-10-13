"""Scene of a task assembled from ready-made blocks.

The web client draws a ``blocks`` scene by itself, so a module that uses it needs
no client code. A clickable element carries the chat command it sends, for
example ``/op press:2:3`` or ``/answer 7``.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Sequence
from typing import Any

State = dict[str, Any]

KIND = 'blocks'
TONES = ('plain', 'accent', 'muted', 'good', 'bad')
COMMANDS = ('probe', 'hint', 'op', 'undo', 'reset', 'done')
SHAPES = ('point', 'line', 'polygon', 'circle', 'ellipse', 'sector', 'arc', 'label')
DRAG_NAME = re.compile(r'[A-Za-z0-9_]{1,24}')
BARE_ANSWERS = ('done', 'impossible')


def text(value: str) -> State:
    """A paragraph. Line breaks in ``value`` are kept."""

    return {'type': 'text', 'text': str(value)}


def table(columns: Sequence[str], rows: Iterable[Sequence[Any]]) -> State:
    header = [str(column) for column in columns]
    body = [[str(value) for value in row] for row in rows]
    if any(len(row) != len(header) for row in body):
        raise ValueError('в каждой строке таблицы должно быть столько же значений, сколько столбцов')
    return {'type': 'table', 'columns': header, 'rows': body}


def _chat_command(command: str) -> str:
    """A click sends this text to the chat, so it must be a command and not a message to the assistant."""

    text = str(command).strip()
    if not text.startswith('/') and text not in BARE_ANSWERS:
        raise ValueError(
            f'команда {text!r} должна начинаться с "/" или быть одним из слов {", ".join(BARE_ANSWERS)}'
        )
    return text


def _tone(tone: str) -> str:
    if tone not in TONES:
        raise ValueError(f'оттенок должен быть одним из {", ".join(TONES)}')
    return tone


def _action(command: str | None) -> str | None:
    return None if command is None else _chat_command(command)


def _grip(drag: str | None) -> str | None:
    """Name under which a shape is reported when the participant drags it to a new place."""

    if drag is not None and not (isinstance(drag, str) and DRAG_NAME.fullmatch(drag)):
        raise ValueError('имя переносимого объекта пишется латинскими буквами, цифрами и знаком "_"')
    return drag


def _handles(command: str | None, drag: str | None) -> State:
    return {'command': _action(command), 'drag': _grip(drag)}


def cell(label: Any = '', *, tone: str = 'plain', command: str | None = None) -> State:
    """One cell of a grid. With ``command`` the cell becomes a button."""

    return {'text': str(label), 'tone': _tone(tone), 'command': _action(command)}


def grid(cells: Iterable[Iterable[State | Any]], *, caption: str | None = None) -> State:
    """A rectangular field. A value that is not a ``cell(...)`` becomes a plain cell."""

    rows = [[item if isinstance(item, dict) else cell(item) for item in row] for row in cells]
    if not rows or any(len(row) != len(rows[0]) for row in rows):
        raise ValueError('поле должно быть непустым прямоугольником')
    return {'type': 'grid', 'caption': caption, 'cells': rows}


def button(label: str, command: str) -> State:
    if not str(label).strip():
        raise ValueError('у кнопки должна быть подпись')
    return {'label': str(label), 'command': _chat_command(command)}


def buttons(items: Iterable[State]) -> State:
    return {'type': 'buttons', 'items': list(items)}


def facts(*items: str) -> State:
    """Short status lines such as counters and limits."""

    return {'type': 'facts', 'items': [str(item) for item in items]}


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'{name} должно быть числом')
    return value


def _positive(value: Any, name: str) -> float:
    if _number(value, name) <= 0:
        raise ValueError(f'{name} должно быть больше нуля')
    return value


def point(
    x: float,
    y: float,
    *,
    label: str = '',
    tone: str = 'accent',
    command: str | None = None,
    drag: str | None = None,
) -> State:
    """A point with an optional name next to it.

    With ``command`` the point becomes a button. With ``drag`` the participant can
    move it, and the task type receives the name and the new coordinates.
    """

    return {
        'shape': 'point',
        'x': _number(x, 'x'),
        'y': _number(y, 'y'),
        'label': str(label),
        'tone': _tone(tone),
        **_handles(command, drag),
    }


def line(x1: float, y1: float, x2: float, y2: float, *, tone: str = 'plain', dashed: bool = False) -> State:
    """A segment from ``(x1, y1)`` to ``(x2, y2)``."""

    ends = {name: _number(value, name) for name, value in (('x1', x1), ('y1', y1), ('x2', x2), ('y2', y2))}
    return {'shape': 'line', **ends, 'dashed': bool(dashed), 'tone': _tone(tone)}


def polygon(
    points: Iterable[Sequence[float]],
    *,
    tone: str = 'plain',
    filled: bool = True,
    command: str | None = None,
    drag: str | None = None,
) -> State:
    """A polygon through the given vertices, in order. A dragged polygon reports its first vertex."""

    vertices = [[_number(x, 'x'), _number(y, 'y')] for x, y in points]
    if len(vertices) < 3:
        raise ValueError('у многоугольника должно быть не меньше трёх вершин')
    return {
        'shape': 'polygon',
        'points': vertices,
        'filled': bool(filled),
        'tone': _tone(tone),
        **_handles(command, drag),
    }


def circle(
    x: float,
    y: float,
    radius: float,
    *,
    tone: str = 'plain',
    filled: bool = False,
    command: str | None = None,
    drag: str | None = None,
) -> State:
    return {
        'shape': 'circle',
        'x': _number(x, 'x'),
        'y': _number(y, 'y'),
        'radius': _positive(radius, 'radius'),
        'filled': bool(filled),
        'tone': _tone(tone),
        **_handles(command, drag),
    }


def ellipse(
    x: float,
    y: float,
    radius_x: float,
    radius_y: float,
    *,
    tone: str = 'plain',
    filled: bool = False,
    command: str | None = None,
    drag: str | None = None,
) -> State:
    """An ellipse with its axes along the coordinate axes."""

    return {
        'shape': 'ellipse',
        'x': _number(x, 'x'),
        'y': _number(y, 'y'),
        'radius_x': _positive(radius_x, 'radius_x'),
        'radius_y': _positive(radius_y, 'radius_y'),
        'filled': bool(filled),
        'tone': _tone(tone),
        **_handles(command, drag),
    }


def _round_part(shape: str, x: float, y: float, radius: float, start: float, end: float, tone: str) -> State:
    return {
        'shape': shape,
        'x': _number(x, 'x'),
        'y': _number(y, 'y'),
        'radius': _positive(radius, 'radius'),
        'start': _number(start, 'start'),
        'end': _number(end, 'end'),
        'tone': _tone(tone),
    }


def sector(
    x: float,
    y: float,
    radius: float,
    start: float,
    end: float,
    *,
    tone: str = 'accent',
    command: str | None = None,
    drag: str | None = None,
) -> State:
    """A filled part of a disc. Angles are in degrees, counted counterclockwise from the x axis."""

    return {**_round_part('sector', x, y, radius, start, end, tone), **_handles(command, drag)}


def arc(x: float, y: float, radius: float, start: float, end: float, *, tone: str = 'plain') -> State:
    """A part of a circle. Angles are in degrees, counted counterclockwise from the x axis."""

    return _round_part('arc', x, y, radius, start, end, tone)


def label(x: float, y: float, text: Any, *, tone: str = 'plain', drag: str | None = None) -> State:
    """A short text centred at a point of the drawing."""

    return {
        'shape': 'label',
        'x': _number(x, 'x'),
        'y': _number(y, 'y'),
        'text': str(text),
        'tone': _tone(tone),
        'drag': _grip(drag),
    }


def _range(bounds: Sequence[float], name: str) -> list[float]:
    low, high = (_number(value, name) for value in bounds)
    if low >= high:
        raise ValueError(f'в диапазоне {name} левая граница должна быть меньше правой')
    return [low, high]


def picture(
    shapes: Iterable[State],
    *,
    x: Sequence[float] = (0, 10),
    y: Sequence[float] = (0, 10),
    grid: bool = False,
    snap: float | None = 1,
    caption: str | None = None,
) -> State:
    """A drawing on the coordinate plane, built from points, lines, polygons and round shapes.

    ``x`` and ``y`` are the visible ranges of the coordinates, the y axis points up.
    With ``grid`` the lines of integer coordinates are drawn under the shapes.
    A dragged shape lands on coordinates that are multiples of ``snap``, on whole
    numbers by default. ``snap=None`` lets it land anywhere.
    """

    drawn = list(shapes)
    if any(not isinstance(shape, dict) or shape.get('shape') not in SHAPES for shape in drawn):
        raise ValueError(f'рисунок собирается из фигур: {", ".join(SHAPES)}')
    return {
        'type': 'picture',
        'x': _range(x, 'x'),
        'y': _range(y, 'y'),
        'grid': bool(grid),
        'snap': None if snap is None else _positive(snap, 'snap'),
        'caption': caption,
        'shapes': drawn,
    }


def scene(
    prompt: str,
    content: Iterable[State],
    *,
    commands: Iterable[str] = (),
    help_lines: Iterable[str] = (),
    response_hint: str | None = None,
    answer_guide: str | None = None,
) -> State:
    """Public state of a task: the statement, the blocks and the chat commands it accepts.

    ``response_hint`` is the answer format shown in the input field, ``answer_guide`` is
    the sentence under the statement that tells how to answer.
    """

    allowed = list(commands)
    if any(command not in COMMANDS for command in allowed):
        raise ValueError(f'команды задачи выбираются из {", ".join(COMMANDS)}')
    state: State = {
        'kind': KIND,
        'prompt': str(prompt),
        'blocks': list(content),
        'commands': allowed,
        'help': [str(line) for line in help_lines],
    }
    if response_hint is not None:
        state['response_hint'] = str(response_hint)
    if answer_guide is not None:
        state['answer_guide'] = str(answer_guide)
    return state


def for_assistant(public_state: State) -> State:
    """What the assistant is shown: the same blocks the participant sees, without click commands."""

    def visible(block: State) -> State:
        if block.get('type') == 'grid':
            rows = [
                [{'text': item.get('text'), 'tone': item.get('tone')} for item in row]
                for row in block['cells']
            ]
            return {'type': 'grid', 'caption': block.get('caption'), 'cells': rows}
        if block.get('type') == 'buttons':
            return {'type': 'buttons', 'items': [item.get('label') for item in block['items']]}
        if block.get('type') == 'picture':
            handles = ('command', 'drag')
            shapes = [
                {key: value for key, value in shape.items() if key not in handles}
                for shape in block['shapes']
            ]
            return {**block, 'shapes': shapes}
        return block

    content = public_state.get('blocks') if isinstance(public_state.get('blocks'), list) else []
    return {
        'blocks': [visible(block) for block in content if isinstance(block, dict)],
        'commands': public_state.get('commands'),
    }
