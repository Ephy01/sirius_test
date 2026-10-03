"""Generator: a random wiring with either a reachable target or three exam chords."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

from .panel import (
    CHORD_BUDGET,
    EXAM_CHORD_COUNT,
    FAMILY_KEY,
    GENERATOR_VERSION,
    PREDICT_VARIANT,
    PUBLIC_KIND,
    REACH_VARIANT,
    chord_effects,
    chord_indicator,
    in_span,
    lamp_list,
    reach_certificate,
)

GENERATION_ATTEMPTS = 512
WIRING_HINT_CATEGORIES = {
    'sparse_wiring': 'каждая кнопка переключает не больше двух ламп',
    'dense_wiring': 'есть кнопка, переключающая три и более ламп',
}

PROMPT_INTRO = 'Дано несколько ламп, часть из них включена. Кнопки срабатывают только парами. '
REACH_PROMPT = (
    PROMPT_INTRO + 'Твоя задача — подобрать комбинацию из двух кнопок, чтобы получить целевой узор.'
)
REACH_RESPONSE_HINT = 'Нажимайте комбинации: /op b1+b2. Панель завершится сама, когда лампы совпадут с целью.'
PREDICT_PROMPT = PROMPT_INTRO + (
    'Изучите проводку пробами, затем предскажите, какие лампы '
    'переключит каждая из трёх экзаменационных комбинаций.'
)


@dataclass(frozen=True)
class _Panel:
    """A sampled wiring: what every button and every chord toggles, and the lamps lit at the start."""

    lamp_count: int
    button_count: int
    columns: list[int]
    effects: dict[str, int]
    start: int

    @property
    def chords(self) -> list[str]:
        return sorted(self.effects)


def _panel_shape(rng: random.Random, difficulty: int) -> tuple[int, int]:
    if difficulty <= 2:
        return 4, 4
    if difficulty == 3:
        return 5, rng.choice((4, 5))
    return 6, 5


def _sample_matrix(rng: random.Random, lamp_count: int, button_count: int) -> list[int] | None:
    """Sample non-degenerate columns: no zero and no duplicate columns."""

    columns = [rng.randrange(1, 1 << lamp_count) for _ in range(button_count)]
    if len(set(columns)) != button_count:
        return None
    return columns


def _variant(rng: random.Random, difficulty: int) -> str:
    if difficulty <= 2:
        return REACH_VARIANT
    if difficulty >= 4:
        return PREDICT_VARIANT
    return rng.choice((REACH_VARIANT, PREDICT_VARIANT))


def _sample_panel(rng: random.Random, lamp_count: int, button_count: int) -> _Panel | None:
    columns = _sample_matrix(rng, lamp_count, button_count)
    if columns is None:
        return None
    effects = chord_effects(columns)
    if any(effect == 0 for effect in effects.values()):
        return None
    return _Panel(lamp_count, button_count, columns, effects, start=rng.randrange(1 << lamp_count))


def _exam_chords(rng: random.Random, panel: _Panel) -> list[str] | None:
    """Chords withheld from probing whose effects still follow from the chords left on the panel."""

    exam_chords = sorted(rng.sample(panel.chords, EXAM_CHORD_COUNT))
    allowed_indicators = [
        chord_indicator(chord, panel.button_count) for chord in panel.chords if chord not in exam_chords
    ]
    if not all(
        in_span(chord_indicator(chord, panel.button_count), allowed_indicators) for chord in exam_chords
    ):
        return None
    return exam_chords


def _reach_goal(rng: random.Random, panel: _Panel) -> tuple[int, list[str]] | None:
    """A target pattern a few chords away and the shortest chord sequence that reaches it."""

    chords = panel.chords
    chord_sample = rng.sample(chords, rng.randint(2, min(4, len(chords))))
    delta = 0
    for chord in chord_sample:
        delta ^= panel.effects[chord]
    if delta == 0:
        return None
    target = panel.start ^ delta
    certificate = reach_certificate(
        effects=panel.effects, allowed_chords=chords, start=panel.start, target=target
    )
    if not certificate or len(certificate) > CHORD_BUDGET:
        return None
    return target, certificate


def _chord_buttons(chords: list[str]) -> list[dict[str, str]]:
    return [
        {'id': chord, 'label': (f'Кнопки {chord.split("+")[0][1:]} и {chord.split("+")[1][1:]}')}
        for chord in chords
    ]


def _predict_response_hint(lamp_count: int) -> str:
    return (
        'Пробы: /op b1+b2. Ответ — три битовые строки по лампам '
        f'(1 — переключится), например: /answer {"1" * lamp_count} '
        f'{"0" * lamp_count} {"1" + "0" * (lamp_count - 1)}.'
    )


def _public_state(
    panel: _Panel, variant: str, allowed_chords: list[str], prompt: str, response_hint: str
) -> dict[str, Any]:
    return {
        'kind': PUBLIC_KIND,
        'family': FAMILY_KEY,
        'variant': variant,
        'prompt': prompt,
        'legend': 'Кнопки срабатывают только парами.',
        'lamp_count': panel.lamp_count,
        'button_count': panel.button_count,
        'ops': _chord_buttons(allowed_chords),
        'start': lamp_list(panel.start, panel.lamp_count),
        'current': lamp_list(panel.start, panel.lamp_count),
        'chord_budget': CHORD_BUDGET,
        'chords_remaining': CHORD_BUDGET,
        'free_training_probe': True,
        'observations': [],
        'response_hint': response_hint,
    }


def _private_state(panel: _Panel, difficulty: int, variant: str, allowed_chords: list[str]) -> dict[str, Any]:
    dense = any(column.bit_count() >= 3 for column in panel.columns)
    return {
        'family': FAMILY_KEY,
        'generator_version': GENERATOR_VERSION,
        'difficulty': difficulty,
        'variant': variant,
        'hint_category': WIRING_HINT_CATEGORIES['dense_wiring' if dense else 'sparse_wiring'],
        'lamp_count': panel.lamp_count,
        'button_count': panel.button_count,
        'columns': panel.columns,
        'chord_effects': panel.effects,
        'allowed_chords': allowed_chords,
        'start': panel.start,
        'current': panel.start,
        'chord_budget': CHORD_BUDGET,
        'chords_used': 0,
        'observed_chords': [],
        'processed_actions': {},
    }


def _reach_task(
    panel: _Panel, difficulty: int, target: int, certificate: list[str]
) -> tuple[dict[str, Any], dict[str, Any]]:
    public = _public_state(panel, REACH_VARIANT, panel.chords, REACH_PROMPT, REACH_RESPONSE_HINT)
    public['target'] = lamp_list(target, panel.lamp_count)
    private = _private_state(panel, difficulty, REACH_VARIANT, panel.chords)
    private.update({'target': target, 'certificate': certificate, 'min_len': len(certificate)})
    return public, private


def _predict_task(
    panel: _Panel, difficulty: int, exam_chords: list[str]
) -> tuple[dict[str, Any], dict[str, Any]]:
    allowed_chords = [chord for chord in panel.chords if chord not in exam_chords]
    response_hint = _predict_response_hint(panel.lamp_count)
    public = _public_state(panel, PREDICT_VARIANT, allowed_chords, PREDICT_PROMPT, response_hint)
    public['exam_chords'] = _chord_buttons(exam_chords)
    private = _private_state(panel, difficulty, PREDICT_VARIANT, allowed_chords)
    private.update(
        {'exam_chords': exam_chords, 'exam_effects': [panel.effects[chord] for chord in exam_chords]}
    )
    return public, private


def _task_on(
    rng: random.Random, panel: _Panel, variant: str, difficulty: int
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    if variant == PREDICT_VARIANT:
        exam_chords = _exam_chords(rng, panel)
        return None if exam_chords is None else _predict_task(panel, difficulty, exam_chords)
    goal = _reach_goal(rng, panel)
    return None if goal is None else _reach_task(panel, difficulty, *goal)


def generate_hidden_wiring_task(*, seed: int, difficulty: int) -> tuple[dict[str, Any], dict[str, Any]]:
    if isinstance(difficulty, bool) or not 1 <= difficulty <= 5:
        raise ValueError('hidden_wiring difficulty must be from 1 to 5')
    rng = random.Random(seed)
    lamp_count, button_count = _panel_shape(rng, difficulty)
    variant = _variant(rng, difficulty)
    for _ in range(GENERATION_ATTEMPTS):
        panel = _sample_panel(rng, lamp_count, button_count)
        task = _task_on(rng, panel, variant, difficulty) if panel is not None else None
        if task is not None:
            return task
    raise RuntimeError(f'Unable to generate hidden_wiring at difficulty {difficulty}')


def validate_hidden_wiring_instance(public_state: dict[str, Any], private_state: dict[str, Any]) -> None:
    """Self-check used by tests: solvability certificates hold."""

    effects = {str(chord): int(effect) for chord, effect in private_state['chord_effects'].items()}
    columns = [int(column) for column in private_state['columns']]
    assert len(set(columns)) == len(columns)
    assert all(column != 0 for column in columns)
    assert all(effect != 0 for effect in effects.values())
    if str(private_state.get('variant')) == REACH_VARIANT:
        certificate = [str(chord) for chord in private_state['certificate']]
        state = int(private_state['start'])
        for chord in certificate:
            state ^= effects[chord]
        assert state == int(private_state['target'])
        assert 1 <= len(certificate) <= CHORD_BUDGET
        assert len(certificate) == int(private_state['min_len'])
    else:
        button_count = int(private_state['button_count'])
        allowed = [chord_indicator(str(chord), button_count) for chord in private_state['allowed_chords']]
        for chord in private_state['exam_chords']:
            assert str(chord) not in {str(item) for item in private_state['allowed_chords']}
            assert in_span(chord_indicator(str(chord), button_count), allowed)
