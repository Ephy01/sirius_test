"""Scoring of the final ``done`` / ``impossible`` answer and interaction aggregates."""

from __future__ import annotations

from ..family import State
from .common import FAMILY_KEY, GENERATOR_VERSION

DONE_ANSWERS = frozenset({'done', 'готово', 'готов'})
IMPOSSIBLE_ANSWERS = frozenset({'impossible', 'недостижимо', 'невозможно'})
FALSE_IMPOSSIBLE_FREEZE_SECONDS = 15


def telemetry_aggregates(private_state: State) -> State:
    interaction = private_state.get('interaction') or {}
    apply_count = int(interaction.get('apply_count') or 0)
    min_len_value = private_state.get('min_len')
    min_len = (
        int(min_len_value) if isinstance(min_len_value, int) and not isinstance(min_len_value, bool) else None
    )
    return {
        'first_action_latency_ms': interaction.get('first_action_latency_ms'),
        'undo_count': int(interaction.get('undo_count') or 0),
        'reset_count': int(interaction.get('reset_count') or 0),
        'revisited_states': (
            int(interaction.get('revisited_count') or 0) / apply_count if apply_count else 0.0
        ),
        'len_ratio': (apply_count / min_len if min_len is not None and min_len > 0 else None),
        'actual_length': apply_count,
    }


def _verdict(
    base: State, *, accepted: bool, score: float, reason: str, feedback: str, false_impossible: bool = False
) -> State:
    """An accepted answer is correct and closes the task; a false ``impossible`` freezes the input."""

    return {
        **base,
        'accepted': accepted,
        'correct': accepted,
        'should_finalize': accepted,
        'evidence': 1 if accepted else 0,
        'continuous_score': score,
        'false_impossible': false_impossible,
        'freeze_seconds': FALSE_IMPOSSIBLE_FREEZE_SECONDS if false_impossible else 0,
        'reason': reason,
        'feedback': feedback,
    }


def _path_score(private_state: State, actual_length: int) -> float:
    min_len = int(private_state['min_len'])
    return min(1.0, 0.6 + 0.4 * min_len / max(min_len, actual_length))


def _done_verdict(base: State, private_state: State) -> State:
    if private_state['current'] != private_state['target']:
        return _verdict(
            base, accepted=False, score=0.0, reason='not_at_target', feedback='Задача ещё не завершена.'
        )
    score = _path_score(private_state, int(base['actual_length']))
    return _verdict(base, accepted=True, score=score, reason='target_reached', feedback='Ответ принят.')


def _impossible_verdict(base: State, private_state: State) -> State:
    if not bool(private_state['reachable']):
        return _verdict(base, accepted=True, score=1.0, reason='correct_impossible', feedback='Ответ принят.')
    return _verdict(
        base,
        accepted=False,
        score=0.0,
        reason='false_impossible',
        feedback=f'Ответ не принят. Повторите попытку через {FALSE_IMPOSSIBLE_FREEZE_SECONDS} секунд.',
        false_impossible=True,
    )


def evaluate_machine_answer(*, answer: str, private_state: State) -> State:
    """Evaluate ``done``/``impossible`` and return API integration hints."""

    normalized = answer.strip().casefold()
    aggregates = telemetry_aggregates(private_state)
    base = {
        'family': FAMILY_KEY,
        'generator_version': GENERATOR_VERSION,
        'difficulty': int(private_state['difficulty']),
        **aggregates,
    }
    if normalized in DONE_ANSWERS:
        return _done_verdict(base, private_state)
    if normalized in IMPOSSIBLE_ANSWERS:
        return _impossible_verdict(base, private_state)
    return _verdict(
        base,
        accepted=False,
        score=0.0,
        reason='invalid_answer',
        feedback='Используйте ответ done или impossible.',
    )
