"""Answer parsing and reference-answer helpers shared by several families."""

from __future__ import annotations

import re

from .family import State


def strip_answer_command(answer: str) -> str:
    return re.sub(r'^\s*/?answer\b', '', answer.strip().casefold()).strip()


def parse_integer(answer: str) -> int | None:
    """The integer a participant sent, with or without the ``/answer`` command."""

    text = strip_answer_command(answer).replace('\u2212', '-').replace(' ', '')
    return int(text) if re.fullmatch(r'[+-]?\d{1,18}', text) else None


def probability_reference_answer(private_state: State) -> tuple[str, list[str]]:
    probability = private_state.get('probability') or {}
    return f'/answer {probability.get("numerator")}/{probability.get("denominator")}', []


def probability_debug_details(private_state: State) -> list[str]:
    probability = private_state.get('probability') or {}
    favorable = private_state.get('favorable_faces') or private_state.get('favorable_outcomes')
    total = private_state.get('total_faces') or private_state.get('total_outcomes')
    details = [f'Вероятность: {probability.get("numerator")}/{probability.get("denominator")}']
    if favorable is not None and total is not None:
        details.append(f'Благоприятных исходов: {favorable} из {total}')
    return details
