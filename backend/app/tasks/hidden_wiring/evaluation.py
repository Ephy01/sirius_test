"""Scoring of the exam: predicted effects of the three withheld chords."""

from __future__ import annotations

from typing import Any

from .panel import (
    CHORD_BUDGET,
    FAMILY_KEY,
    GENERATOR_VERSION,
    HINT_SCORE_MULTIPLIER,
    REACH_VARIANT,
    lamp_list,
)

REACH_ANSWER_FEEDBACK = (
    'Панель завершается автоматически, когда лампы совпадут с целью. Продолжайте нажимать комбинации.'
)


def _parse_prediction(answer: str, lamp_count: int, exam_count: int) -> list[int] | None:
    tokens = [token for token in answer.replace('/answer', ' ').replace(',', ' ').split() if token]
    bit_tokens = [token for token in tokens if len(token) == lamp_count and set(token) <= {'0', '1'}]
    if len(bit_tokens) != exam_count:
        return None
    return [sum(1 << index for index, char in enumerate(token) if char == '1') for token in bit_tokens]


def _open_verdict(base: dict[str, Any], *, parsed: bool, reason: str, feedback: str) -> dict[str, Any]:
    """An answer that scores nothing and leaves the task open."""

    return {
        **base,
        'correct': False,
        'parsed': parsed,
        'should_finalize': False,
        'reason': reason,
        'continuous_score': 0.0,
        'evidence': 0,
        'feedback': feedback,
    }


def _prediction_verdict(
    base: dict[str, Any], private_state: dict[str, Any], predictions: list[int], expected: list[int]
) -> dict[str, Any]:
    lamp_count = int(private_state['lamp_count'])
    unused = max(0, CHORD_BUDGET + 1 - int(base['chords_used']))
    total_bits = lamp_count * len(expected)
    correct_bits = sum(
        lamp_count - (prediction ^ target).bit_count()
        for prediction, target in zip(predictions, expected, strict=True)
    )
    accuracy = correct_bits / total_bits
    exact = correct_bits == total_bits
    hint_used = bool(private_state.get('hint_used'))
    raw_score = max(0.0, accuracy - 0.5) * 2
    return {
        **base,
        'correct': exact,
        'parsed': True,
        'predicted': [lamp_list(prediction, lamp_count) for prediction in predictions],
        'bit_accuracy': accuracy,
        'correct_bits': correct_bits,
        'total_bits': total_bits,
        'unused_chords': unused,
        'hint_used': hint_used,
        'continuous_score': (raw_score * HINT_SCORE_MULTIPLIER if hint_used else raw_score),
        'efficient': exact and unused > 0,
        'evidence': 1 if exact else -1,
    }


def evaluate_hidden_wiring_answer(*, answer: str, private_state: dict[str, Any]) -> dict[str, Any]:
    lamp_count = int(private_state['lamp_count'])
    chords_used = int(private_state.get('chords_used') or 0)
    base = {
        'family': FAMILY_KEY,
        'generator_version': GENERATOR_VERSION,
        'difficulty': int(private_state['difficulty']),
        'variant': str(private_state.get('variant')),
        'chords_used': chords_used,
    }
    if str(private_state.get('variant')) == REACH_VARIANT:
        reached = int(private_state['current']) == int(private_state['target'])
        reason = 'target_reached' if reached else 'target_not_reached'
        return _open_verdict(base, parsed=True, reason=reason, feedback=REACH_ANSWER_FEEDBACK)
    expected = [int(value) for value in private_state['exam_effects']]
    predictions = _parse_prediction(answer, lamp_count, len(expected))
    if predictions is None:
        example = ' '.join('0' * lamp_count for _ in expected)
        feedback = f'Ответьте тремя битовыми строками по числу ламп, например: /answer {example}.'
        return _open_verdict(base, parsed=False, reason='invalid_answer', feedback=feedback)
    return _prediction_verdict(base, private_state, predictions, expected)
