"""Scoring of the final answer: every target covered at the optimal cost."""

from __future__ import annotations

from typing import Any

from .board import interaction_counts, placement_state

_DONE = frozenset({'done', 'готово', 'готов', 'решено'})


def evaluate_chess_coverage_answer(*, answer: str, private_state: dict[str, Any]) -> dict[str, Any]:
    parsed = answer.strip().casefold() in _DONE
    state = placement_state(private_state.get('placements') or [], private_state)
    optimal_cost = int(private_state['optimal_cost'])
    correct = bool(parsed and state['all_covered'] and state['total_cost'] == optimal_cost)
    return {
        'accepted': True,
        'parsed': parsed,
        'correct': correct,
        'should_finalize': True,
        'continuous_score': 1.0 if correct else 0.0,
        'placements': state['placements'],
        'selected_cost': int(state['total_cost']),
        'optimal_cost': optimal_cost,
        'cost_regret': max(0, int(state['total_cost']) - optimal_cost),
        'covered_count': int(state['covered_count']),
        'target_count': int(state['target_count']),
        'all_covered': bool(state['all_covered']),
        **interaction_counts(private_state.get('interaction') or {}),
    }
