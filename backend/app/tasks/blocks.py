"""Scene of a task assembled from ready-made blocks.

The web client draws a ``blocks`` scene by itself, so a module that uses it needs
no client code. A clickable element carries the chat command it sends, for
example ``/op press:2:3`` or ``/answer 7``.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

State = dict[str, Any]

KIND = 'blocks'
TONES = ('plain', 'accent', 'muted', 'good', 'bad')
COMMANDS = ('probe', 'hint', 'op', 'undo', 'reset', 'done')
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


def cell(label: Any = '', *, tone: str = 'plain', command: str | None = None) -> State:
    """One cell of a grid. With ``command`` the cell becomes a button."""

    if tone not in TONES:
        raise ValueError(f'оттенок клетки должен быть одним из {", ".join(TONES)}')
    return {'text': str(label), 'tone': tone, 'command': None if command is None else _chat_command(command)}


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


def scene(
    prompt: str,
    content: Iterable[State],
    *,
    commands: Iterable[str] = (),
    help_lines: Iterable[str] = (),
    response_hint: str | None = None,
) -> State:
    """Public state of a task: the statement, the blocks and the chat commands it accepts."""

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
        return block

    content = public_state.get('blocks') if isinstance(public_state.get('blocks'), list) else []
    return {
        'blocks': [visible(block) for block in content if isinstance(block, dict)],
        'commands': public_state.get('commands'),
    }
