"""Deterministic generators for the ``machine_reach`` task family.

The package deliberately has no database or HTTP dependencies.  A generated
task is a pair of JSON-compatible dictionaries.  State changes are expressed
as pure transitions, while persistence and authorization stay in the API
layer.

Each sub-kind lives in its own module with its generator, the effect of one
operation and the check of its unreachability certificate; ``operations`` and
``validation`` list them.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sirius_gate.family import (
    FamilyCard,
    State,
    TaskFamily,
    Transition,
    Variant,
    latency_ms,
    optional_text,
    required_text,
)

from .common import (
    CHESS_KIND,
    DISTANCE_RANGES,
    FAMILY_KEY,
    GENERATOR_VERSION,
    LAMPS_GF2,
    LEAPER_BOARD,
    MACHINE_PANEL_KIND,
    MAX_GENERATION_ATTEMPTS,
    NUMERIC_MACHINE,
    PERM_PUZZLE,
    REACHABLE_SHARE,
    READABLE_VERSIONS,
    STEPS_SOFT_CAP,
    SUB_KINDS,
    Operation,
)
from .evaluation import evaluate_machine_answer, telemetry_aggregates
from .lamps import LAMPS_DISTANCE_RANGES, generate_lamps_gf2_task
from .leaper import generate_leaper_board_task
from .numeric import generate_numeric_machine_task
from .permutations import generate_perm_puzzle_task
from .transitions import transition_machine_action
from .validation import (
    shortest_witness,
    simulate_witness,
    validate_machine_instance,
    validate_unreachable_certificate,
)

__all__ = [
    'AI_VISIBLE_KEYS',
    'CHESS_KIND',
    'DISTANCE_RANGES',
    'FAMILY',
    'FAMILY_KEY',
    'GENERATORS',
    'GENERATOR_VERSION',
    'LAMPS_DISTANCE_RANGES',
    'LAMPS_GF2',
    'LEAPER_BOARD',
    'MACHINE_PANEL_KIND',
    'MAX_GENERATION_ATTEMPTS',
    'NUMERIC_MACHINE',
    'PERM_PUZZLE',
    'REACHABLE_SHARE',
    'READABLE_VERSIONS',
    'STEPS_SOFT_CAP',
    'SUB_KINDS',
    'Operation',
    'evaluate_machine_answer',
    'generate_lamps_gf2_task',
    'generate_leaper_board_task',
    'generate_machine_reach_task',
    'generate_numeric_machine_task',
    'generate_perm_puzzle_task',
    'shortest_witness',
    'simulate_witness',
    'telemetry_aggregates',
    'transition_machine_action',
    'validate_machine_instance',
    'validate_unreachable_certificate',
]

GENERATORS: dict[str, Callable[..., tuple[dict[str, Any], dict[str, Any]]]] = {
    LAMPS_GF2: generate_lamps_gf2_task,
    NUMERIC_MACHINE: generate_numeric_machine_task,
    PERM_PUZZLE: generate_perm_puzzle_task,
    LEAPER_BOARD: generate_leaper_board_task,
}


def generate_machine_reach_task(
    *, seed: int, difficulty: int, sub_kind: str | None = None
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Generate one deterministic task.

    When ``sub_kind`` is omitted it is selected deterministically from the
    task seed, allowing the registry to expose one family with four variants.
    """

    selected = sub_kind or SUB_KINDS[seed % len(SUB_KINDS)]
    try:
        generator = GENERATORS[selected]
    except KeyError as error:
        raise ValueError(f'Unsupported machine sub-kind: {selected!r}') from error
    return generator(seed=seed, difficulty=difficulty)


AI_VISIBLE_KEYS = (
    'sub_kind',
    'ops',
    'start',
    'current',
    'target',
    'steps_soft_cap',
    'steps_taken',
    'lamp_count',
    'working_range',
    'card_count',
    'rows',
    'cols',
    'blocked',
    'jump',
    'board',
)


def _generate(seed: int, difficulty: int, context: State) -> tuple[State, State]:
    configured = context.get('sub_kinds')
    candidates = (
        [item for item in configured if isinstance(item, str)] if isinstance(configured, list) else []
    )
    sub_kind = candidates[seed % len(candidates)] if candidates else None
    return generate_machine_reach_task(seed=seed, difficulty=difficulty, sub_kind=sub_kind)


def _action(action_type: str) -> Callable[[State, State, State], Transition]:
    def apply(payload: State, public_state: State, private_state: State) -> Transition:
        return transition_machine_action(
            action_type=action_type,
            public_state=public_state,
            private_state=private_state,
            client_action_id=required_text(
                payload, 'client_action_id', 'Machine action requires client_action_id'
            ),
            op_id=optional_text(payload, 'op_id', 'Machine op_id must be a string'),
            first_action_latency_ms=latency_ms(payload),
        )

    return apply


def _reference_answer(private_state: State) -> tuple[str, list[str]]:
    if not private_state.get('reachable'):
        return 'impossible', []
    commands = [f'/op {op_id}' for op_id in private_state.get('witness', [])]
    return 'Примените операции и завершите ответом done:', [*commands, 'done']


def _debug_details(private_state: State) -> list[str]:
    details = [f'Подвид: {private_state.get("sub_kind")}']
    if private_state.get('reachable'):
        details.append(
            f'Цель достижима, кратчайший путь ({private_state.get("min_len")} шагов): '
            + ' → '.join(private_state.get('witness', []))
        )
        return details
    certificate = private_state.get('certificate') or {}
    details.append('Цель недостижима; сертификат: ' + str(certificate.get('kind', certificate)))
    return details


def _one_based(point: Any) -> Any:
    if not isinstance(point, dict) or 'row' not in point or 'col' not in point:
        return point
    return {**point, 'row': point['row'] + 1, 'col': point['col'] + 1}


def _ai_context(public_state: State) -> State:
    context = {key: public_state.get(key) for key in AI_VISIBLE_KEYS if key in public_state}
    if public_state.get('sub_kind') != LEAPER_BOARD:
        return context
    for key in ('start', 'current', 'target'):
        if key in context:
            context[key] = _one_based(context[key])
    if isinstance(context.get('blocked'), list):
        context['blocked'] = [_one_based(cell) for cell in context['blocked']]
    context['coordinate_note'] = 'Координаты в формате (строка, столбец), нумерация с 1, строка 1 — верхняя.'
    return context


FAMILY = TaskFamily(
    key=FAMILY_KEY,
    version=GENERATOR_VERSION,
    card=FamilyCard(
        title='Машины и инварианты',
        description=(
            'Лампы, числовые операции, перестановки и прыгуны: достигните цели или докажите недостижимость.'
        ),
        weight=12,
        skin='machine_panel',
        variants={
            LAMPS_GF2: Variant('Лампы'),
            NUMERIC_MACHINE: Variant('Числовая машина'),
            PERM_PUZZLE: Variant('Перестановки'),
            LEAPER_BOARD: Variant('Прыгун'),
        },
    ),
    readable_versions=READABLE_VERSIONS,
    generate=_generate,
    evaluate=lambda answer, private_state: evaluate_machine_answer(
        answer=answer, private_state=private_state
    ),
    actions={name: _action(name) for name in ('apply_op', 'undo', 'reset')},
    aliases=('machine-reach',),
    sub_kinds=SUB_KINDS,
    tracks_first_action=True,
    reference_answer=_reference_answer,
    debug_details=_debug_details,
    ai_context=_ai_context,
)
