"""Participant action on the panel: press a chord of two buttons."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from ..family import State, Transition
from .panel import CHORD_BUDGET, HINT_SCORE_MULTIPLIER, REACH_VARIANT, entropy_bits, lamp_list


def _replayed_chord(
    stored: dict[str, Any], normalized: str, client_action_id: str, public_state: State, private_state: State
) -> Transition:
    if stored.get('normalized_input') != normalized:
        raise ValueError(f'client_action_id {client_action_id!r} was already used with a different chord')
    return Transition(
        public_state=public_state,
        private_state=private_state,
        accepted=bool(stored.get('accepted')),
        completed=bool(stored.get('completed')),
        reason=str(stored.get('reason')),
        message=str(stored.get('message')),
        normalized_input=normalized,
        evaluation_state=stored.get('telemetry'),
    )


def _press_chord(
    private: dict[str, Any], effects: dict[str, Any], chord: str, chords_used: int
) -> tuple[int, dict[str, Any]]:
    """Apply the chord to the hidden panel; returns its effect and the ΔH telemetry of the probe."""

    lamp_count = int(private['lamp_count'])
    entropy_before = entropy_bits(private)
    effect = int(effects[chord])
    private['current'] = int(private['current']) ^ effect
    private['chords_used'] = chords_used + 1
    observed = [str(item) for item in private.get('observed_chords', [])]
    if chord not in observed:
        private['observed_chords'] = [*observed, chord]
    entropy_after = entropy_bits(private)
    telemetry = {
        'vs_size_before': 1 << entropy_before,
        'vs_size_after': 1 << entropy_after,
        'gain_bits_actual': float(entropy_before - entropy_after),
        'gain_bits_best': float(lamp_count if entropy_before > 0 else 0),
    }
    return effect, telemetry


def _show_chord(
    public: dict[str, Any], private: dict[str, Any], chord: str, effect: int, chords_used: int
) -> None:
    lamp_count = int(private['lamp_count'])
    current = int(private['current'])
    public['current'] = lamp_list(current, lamp_count)
    if chords_used >= 1:
        public['chords_remaining'] = max(0, int(public.get('chords_remaining') or 0) - 1)
    public['observations'].append(
        {
            'chord': chord,
            'training': chords_used == 0,
            'effect': lamp_list(effect, lamp_count),
            'lamps_after': lamp_list(current, lamp_count),
        }
    )


def _target_reached(private: dict[str, Any]) -> bool:
    return str(private.get('variant')) == REACH_VARIANT and int(private['current']) == int(private['target'])


def _reach_evaluation(private: dict[str, Any], telemetry: dict[str, Any]) -> dict[str, Any]:
    min_len = max(1, int(private.get('min_len') or 1))
    used_total = int(private['chords_used'])
    hint_used = bool(private.get('hint_used'))
    raw_score = min(1.0, 0.6 + 0.4 * min_len / used_total)
    return {
        **telemetry,
        'correct': True,
        'reason': 'target_reached',
        'chords_used': used_total,
        'min_len': min_len,
        'len_ratio': used_total / min_len,
        'hint_used': hint_used,
        'continuous_score': (raw_score * HINT_SCORE_MULTIPLIER if hint_used else raw_score),
        'efficient': used_total <= min_len,
        'evidence': 1 if used_total <= min_len + 1 else 0,
    }


def transition_hidden_wiring_chord(
    *, op_id: str, public_state: dict[str, Any], private_state: dict[str, Any], client_action_id: str
) -> Transition:
    next_public = deepcopy(public_state)
    next_private = deepcopy(private_state)
    normalized = op_id.strip().lower().replace(' ', '')
    processed = next_private.setdefault('processed_actions', {})
    stored = processed.get(client_action_id)
    if stored is not None:
        return _replayed_chord(stored, normalized, client_action_id, next_public, next_private)

    def settle(
        accepted: bool, reason: str, message: str, *, completed: bool = False, evaluation: State | None = None
    ) -> Transition:
        processed[client_action_id] = {
            'normalized_input': normalized,
            'accepted': accepted,
            'completed': completed,
            'reason': reason,
            'message': message,
            'telemetry': evaluation,
        }
        return Transition(
            public_state=next_public,
            private_state=next_private,
            accepted=accepted,
            completed=completed,
            reason=reason,
            message=message,
            normalized_input=normalized,
            evaluation_state=evaluation,
        )

    effects = next_private['chord_effects']
    if normalized not in [str(chord) for chord in next_private['allowed_chords']]:
        return settle(False, 'unknown_chord', 'Такой комбинации нет на панели (или она экзаменационная).')
    chords_used = int(next_private.get('chords_used') or 0)
    if chords_used >= CHORD_BUDGET + 1:
        return settle(False, 'chord_budget_exhausted', 'Лимит комбинаций исчерпан.')

    effect, telemetry = _press_chord(next_private, effects, normalized, chords_used)
    _show_chord(next_public, next_private, normalized, effect, chords_used)
    if not _target_reached(next_private):
        return settle(True, 'accepted', 'Комбинация применена: лампы переключились.', evaluation=telemetry)
    return settle(
        True,
        'accepted',
        'Лампы совпали с целевым узором. Панель разгадана.',
        completed=True,
        evaluation=_reach_evaluation(next_private, telemetry),
    )
