"""chess_coverage: cover the marked cells with custom leaping pieces at minimal cost."""

from __future__ import annotations

from ..family import State, TaskFamily, Transition, latency_ms, optional_text, required_text
from .board import CUSTOM_PIECES, FAMILY_KEY, GENERATOR_VERSION, PUBLIC_KIND, READABLE_VERSIONS
from .evaluation import evaluate_chess_coverage_answer
from .generation import generate_chess_coverage_task
from .transitions import transition_chess_coverage_action

__all__ = [
    'CUSTOM_PIECES',
    'FAMILY',
    'FAMILY_KEY',
    'GENERATOR_VERSION',
    'PUBLIC_KIND',
    'READABLE_VERSIONS',
    'evaluate_chess_coverage_answer',
    'generate_chess_coverage_task',
    'transition_chess_coverage_action',
]


def _action(action_type: str):
    def apply(payload: State, public_state: State, private_state: State) -> Transition:
        return transition_chess_coverage_action(
            action_type=action_type,
            public_state=public_state,
            private_state=private_state,
            client_action_id=required_text(
                payload, 'client_action_id', 'Chess coverage action requires client_action_id'
            ),
            op_id=optional_text(payload, 'op_id', 'Chess coverage op_id must be a string'),
            first_action_latency_ms=latency_ms(payload),
        )

    return apply


def _reference_answer(private_state: State) -> tuple[str, list[str]]:
    commands = [
        f'/op place:{item["piece"]}:{item["row"]}:{item["col"]}'
        for item in private_state.get('optimal_placements') or []
    ]
    return 'Расставьте фигуры минимальной стоимости и отправьте done:', [*commands, 'done']


def _debug_details(private_state: State) -> list[str]:
    placements = private_state.get('optimal_placements') or []
    return [
        'Оптимальная стоимость: ' + str(private_state.get('optimal_cost')),
        'Оптимальная расстановка: '
        + ', '.join(
            f'{item["piece"]}@{chr(65 + int(item["col"]))}{int(item["row"]) + 1}' for item in placements
        ),
    ]


def _ai_context(public_state: State) -> State:
    return {
        'boardSize': public_state.get('board_size'),
        'targets': public_state.get('targets'),
        'pieceTypes': public_state.get('piece_types'),
        'placements': public_state.get('placements'),
        'pieceCounts': public_state.get('piece_counts'),
        'coveredTargets': public_state.get('covered_targets'),
        'totalCost': public_state.get('total_cost'),
        'maxPlacements': public_state.get('max_placements'),
        'allCovered': public_state.get('all_covered'),
        'coordinateNote': (
            'Координаты в данных нулевые; интерфейс подписывает строки '
            'числами 1–8, а столбцы буквами A–H. Каждая фигура атакует '
            'только клетки, заданные её массивом offsets.'
        ),
    }


FAMILY = TaskFamily(
    key=FAMILY_KEY,
    version=GENERATOR_VERSION,
    readable_versions=READABLE_VERSIONS,
    generate=lambda seed, difficulty, context: generate_chess_coverage_task(seed=seed, difficulty=difficulty),
    evaluate=lambda answer, private_state: evaluate_chess_coverage_answer(
        answer=answer, private_state=private_state
    ),
    actions={name: _action(name) for name in ('apply_op', 'reset')},
    aliases=('chess-coverage',),
    tracks_first_action=True,
    reference_answer=_reference_answer,
    debug_details=_debug_details,
    ai_context=_ai_context,
)
