"""Answer parsing and reference-answer helpers shared by several families."""

from __future__ import annotations

from sirius_gate.answers import integer as parse_integer
from sirius_gate.answers import text as strip_answer_command
from sirius_gate.family import State

__all__ = [
    'parse_integer',
    'probability_debug_details',
    'probability_reference_answer',
    'strip_answer_command',
]


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
