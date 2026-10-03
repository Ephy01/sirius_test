"""hidden_wiring: recover a hidden GF(2) wiring through paired button chords.

A panel has L lamps and B buttons. The wiring is a matrix M over GF(2):
column j lists which lamps button j toggles. Buttons only fire in chords
of two (UI legend: «кнопки срабатывают только парами»), so one probe
reveals the XOR of two columns.

Design note, for the record of this decision: with single presses one
probe would expose a full column of M and the mechanic trivializes into
B lookups. Chords turn recovery into solving a linear system over GF(2)
— the hypothesis space is an affine subspace of matrices consistent with
the observed chords, its dimension in bits is the exact entropy H, and
ΔH per probe is computed from the rank of the chord-indicator span. That
per-probe ΔH is the measurable reasoning signal.

The first chord is a free training probe (highlighted in the UI); the
budget counts from the second chord onwards.
"""

from __future__ import annotations

from ..family import State, TaskFamily, Transition, required_text
from ..zendo.engine import transition_zendo_hint
from .evaluation import evaluate_hidden_wiring_answer
from .generation import WIRING_HINT_CATEGORIES, generate_hidden_wiring_task, validate_hidden_wiring_instance
from .panel import (
    CHORD_BUDGET,
    EXAM_CHORD_COUNT,
    FAMILY_KEY,
    GENERATOR_VERSION,
    HINT_SCORE_MULTIPLIER,
    PREDICT_VARIANT,
    PUBLIC_KIND,
    REACH_VARIANT,
)
from .transitions import transition_hidden_wiring_chord

__all__ = [
    'CHORD_BUDGET',
    'EXAM_CHORD_COUNT',
    'FAMILY',
    'FAMILY_KEY',
    'GENERATOR_VERSION',
    'HINT_SCORE_MULTIPLIER',
    'PREDICT_VARIANT',
    'PUBLIC_KIND',
    'REACH_VARIANT',
    'WIRING_HINT_CATEGORIES',
    'evaluate_hidden_wiring_answer',
    'generate_hidden_wiring_task',
    'transition_hidden_wiring_chord',
    'validate_hidden_wiring_instance',
]


def _lamps(effect: int, lamp_count: int) -> str:
    return ', '.join(str(lamp + 1) for lamp in range(lamp_count) if effect >> lamp & 1)


def _chord(payload: State, public_state: State, private_state: State) -> Transition:
    return transition_hidden_wiring_chord(
        op_id=required_text(payload, 'op_id', 'Wiring chord requires op_id'),
        public_state=public_state,
        private_state=private_state,
        client_action_id=required_text(payload, 'client_action_id', 'Wiring chord requires client_action_id'),
    )


def _hint(payload: State, public_state: State, private_state: State) -> Transition:
    return transition_zendo_hint(
        public_state=public_state, private_state=private_state, category=str(private_state['hint_category'])
    )


def _reference_answer(private_state: State) -> tuple[str, list[str]]:
    if private_state.get('variant') == REACH_VARIANT:
        commands = [f'/op {chord}' for chord in private_state.get('certificate', [])]
        return 'Панель завершится сама после этих комбинаций:', commands
    lamp_count = int(private_state.get('lamp_count') or 0)
    predictions = (
        ''.join('1' if int(effect) >> index & 1 else '0' for index in range(lamp_count))
        for effect in private_state.get('exam_effects', [])
    )
    return '/answer ' + ' '.join(predictions), []


def _debug_details(private_state: State) -> list[str]:
    lamp_count = int(private_state.get('lamp_count') or 0)
    reach = private_state.get('variant') == REACH_VARIANT
    details = [
        'Вариант: '
        + ('совладай (привести лампы к цели)' if reach else 'пойми (экзамен: предсказать аккорды)'),
        'Проводка (скрытая матрица):',
    ]
    for index, column in enumerate(private_state.get('columns', []), start=1):
        details.append(f'  кнопка {index} переключает лампы: {_lamps(int(column), lamp_count)}')
    effects = private_state.get('chord_effects') or {}
    details.append('Эффекты комбинаций:')
    for chord in sorted(effects):
        details.append(f'  {chord} → лампы {_lamps(int(effects[chord]), lamp_count)}')
    if reach:
        details.append(
            'Кратчайшее решение: '
            + ' → '.join(private_state.get('certificate', []))
            + f' (длина {private_state.get("min_len")})'
        )
        return details
    chords = [str(item) for item in private_state.get('exam_chords', [])]
    exam_effects = [int(item) for item in private_state.get('exam_effects', [])]
    for chord, effect in zip(chords, exam_effects, strict=False):
        details.append(
            f'Экзаменационная комбинация {chord} переключит лампы: '
            + (_lamps(effect, lamp_count) or 'ни одной')
        )
    return details


def _ai_context(public_state: State) -> State:
    return {
        'legend': public_state.get('legend'),
        'variant': public_state.get('variant'),
        'lampCount': public_state.get('lamp_count'),
        'buttonCount': public_state.get('button_count'),
        'availableChords': public_state.get('ops'),
        'startLamps': public_state.get('start'),
        'currentLamps': public_state.get('current'),
        'targetLamps': public_state.get('target'),
        'examChords': public_state.get('exam_chords'),
        'observations': public_state.get('observations'),
        'limits': {
            'chordsRemaining': public_state.get('chords_remaining'),
            'chordBudget': public_state.get('chord_budget'),
            'firstChordIsFreeTraining': public_state.get('free_training_probe'),
        },
    }


FAMILY = TaskFamily(
    key=FAMILY_KEY,
    version=GENERATOR_VERSION,
    generate=lambda seed, difficulty, context: generate_hidden_wiring_task(seed=seed, difficulty=difficulty),
    evaluate=lambda answer, private_state: evaluate_hidden_wiring_answer(
        answer=answer, private_state=private_state
    ),
    actions={'apply_op': _chord, 'hint': _hint},
    probe_action='apply_op',
    aliases=('hidden-wiring',),
    reference_answer=_reference_answer,
    debug_details=_debug_details,
    ai_context=_ai_context,
)
