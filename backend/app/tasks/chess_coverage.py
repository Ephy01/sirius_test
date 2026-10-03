"""chess_coverage: cover the marked cells with custom leaping pieces at minimal cost."""

from __future__ import annotations

import random
import re
from copy import deepcopy
from typing import Any

from .family import State, TaskFamily, Transition, latency_ms, optional_text, required_text

FAMILY_KEY = 'chess_coverage'
GENERATOR_VERSION = 'chess-coverage-v2'
PUBLIC_KIND = 'chess_coverage'

_DONE = frozenset({'done', 'готово', 'готов', 'решено'})


def _inside(row: int, col: int, size: int) -> bool:
    return 0 <= row < size and 0 <= col < size


def _interaction_counts(interaction: dict[str, Any]) -> dict[str, Any]:
    return {
        'placement_count': int(interaction.get('placement_count') or 0),
        'removal_count': int(interaction.get('removal_count') or 0),
        'reset_count': int(interaction.get('reset_count') or 0),
        'first_action_latency_ms': interaction.get('first_action_latency_ms'),
    }


CUSTOM_PIECES: tuple[dict[str, Any], ...] = (
    {
        'id': 'N',
        'label': 'конь',
        'base_cost': 2,
        'repeat_surcharge': 1,
        'limit': 3,
        'move_label': 'Г-прыжок: 1×2',
        'offsets': ((-2, -1), (-2, 1), (-1, -2), (-1, 2), (1, -2), (1, 2), (2, -1), (2, 1)),
    },
    {
        'id': 'B',
        'label': 'слон',
        'base_cost': 3,
        'repeat_surcharge': 2,
        'limit': 3,
        'move_label': 'диагональные прыжки 2×2 и 1×3',
        'offsets': (
            (-3, -1),
            (-3, 1),
            (-2, -2),
            (-1, -3),
            (-1, 3),
            (1, -3),
            (1, 3),
            (2, -2),
            (2, 2),
            (3, -1),
            (3, 1),
        ),
    },
    {
        'id': 'R',
        'label': 'ладья',
        'base_cost': 4,
        'repeat_surcharge': 2,
        'limit': 2,
        'move_label': 'прямой прыжок на 2 или 3 клетки',
        'offsets': ((-3, 0), (-2, 0), (0, -3), (0, -2), (0, 2), (0, 3), (2, 0), (3, 0)),
    },
    {
        'id': 'Q',
        'label': 'ферзь',
        'base_cost': 6,
        'repeat_surcharge': 5,
        'limit': 2,
        'move_label': 'корона: Г-прыжок и диагональ 2×2',
        'offsets': (
            (-2, -2),
            (-2, -1),
            (-2, 1),
            (-2, 2),
            (-1, -2),
            (-1, 2),
            (1, -2),
            (1, 2),
            (2, -2),
            (2, -1),
            (2, 1),
            (2, 2),
        ),
    },
)

_PLACE_ACTION = re.compile(r'^place:([NBRQ]):([0-7]):([0-7])$', re.IGNORECASE)
_REMOVE_ACTION = re.compile(r'^remove:(P\d+)$', re.IGNORECASE)


def _piece_map(piece_types: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(piece['id']): piece for piece in piece_types}


def _custom_attacks(piece: dict[str, Any], row: int, col: int, size: int = 8) -> set[tuple[int, int]]:
    return {
        (row + int(dr), col + int(dc))
        for dr, dc in piece['offsets']
        if _inside(row + int(dr), col + int(dc), size)
    }


def _marginal_cost(piece: dict[str, Any], existing_count: int) -> int:
    return int(piece['base_cost']) + int(piece['repeat_surcharge']) * existing_count


def _placement_cost(placements: list[dict[str, Any]], piece_types: list[dict[str, Any]]) -> int:
    definitions = _piece_map(piece_types)
    counts = {piece_id: 0 for piece_id in definitions}
    total = 0
    for placement in placements:
        piece_id = str(placement['piece'])
        total += _marginal_cost(definitions[piece_id], counts[piece_id])
        counts[piece_id] += 1
    return total


def _placement_state(placements: list[dict[str, Any]], private_state: dict[str, Any]) -> dict[str, Any]:
    definitions = _piece_map(private_state['piece_types'])
    targets = [tuple(point) for point in private_state['targets']]
    covered: set[tuple[int, int]] = set()
    counts = {piece_id: 0 for piece_id in definitions}
    public_placements: list[dict[str, Any]] = []
    total_cost = 0
    for placement in sorted(placements, key=lambda item: int(str(item['id'])[1:])):
        piece_id = str(placement['piece'])
        definition = definitions[piece_id]
        cost = _marginal_cost(definition, counts[piece_id])
        counts[piece_id] += 1
        total_cost += cost
        row, col = int(placement['row']), int(placement['col'])
        attacked = _custom_attacks(definition, row, col)
        covered.update(target for target in targets if target in attacked)
        public_placements.append(
            {'id': str(placement['id']), 'piece': piece_id, 'row': row, 'col': col, 'cost': cost}
        )
    return {
        'placements': public_placements,
        'piece_counts': counts,
        'covered_targets': [{'row': row, 'col': col} for row, col in sorted(covered)],
        'covered_count': len(covered),
        'target_count': len(targets),
        'total_cost': total_cost,
        'all_covered': len(covered) == len(targets),
    }


def _solve_placement_problem(
    *,
    targets: list[tuple[int, int]],
    piece_types: list[dict[str, Any]],
    max_placements: int,
    incumbent: list[dict[str, Any]],
) -> tuple[int, list[dict[str, Any]], int]:
    full_mask = (1 << len(targets)) - 1
    target_set = set(targets)
    piece_index = {str(piece['id']): index for index, piece in enumerate(piece_types)}
    options: list[dict[str, Any]] = []
    for row in range(8):
        for col in range(8):
            if (row, col) in target_set:
                continue
            for piece in piece_types:
                mask = sum(
                    1 << index
                    for index, target in enumerate(targets)
                    if target in _custom_attacks(piece, row, col)
                )
                if mask:
                    options.append(
                        {
                            'piece': str(piece['id']),
                            'row': row,
                            'col': col,
                            'square': row * 8 + col,
                            'mask': mask,
                        }
                    )
    by_target = [
        [option for option in options if int(option['mask']) & (1 << index)] for index in range(len(targets))
    ]
    best_cost = _placement_cost(incumbent, piece_types)
    best_solution = deepcopy(incumbent)
    memo: dict[tuple[int, tuple[int, ...], int], int] = {}
    visited_nodes = 0

    def search(
        mask: int, counts: tuple[int, ...], occupied: int, cost: int, selected: list[dict[str, Any]]
    ) -> None:
        nonlocal best_cost, best_solution, visited_nodes
        visited_nodes += 1
        if mask == full_mask:
            if cost < best_cost:
                best_cost = cost
                best_solution = deepcopy(selected)
            return
        if len(selected) >= max_placements or cost >= best_cost:
            return
        key = (mask, counts, occupied)
        previous_cost = memo.get(key)
        if previous_cost is not None and previous_cost <= cost:
            return
        memo[key] = cost

        chosen_options: list[dict[str, Any]] | None = None
        for target_index in range(len(targets)):
            if mask & (1 << target_index):
                continue
            legal = []
            for option in by_target[target_index]:
                square_bit = 1 << int(option['square'])
                index = piece_index[str(option['piece'])]
                if occupied & square_bit:
                    continue
                if counts[index] >= int(piece_types[index]['limit']):
                    continue
                legal.append(option)
            if not legal:
                return
            if chosen_options is None or len(legal) < len(chosen_options):
                chosen_options = legal

        assert chosen_options is not None
        ranked: list[tuple[float, int, int, dict[str, Any]]] = []
        for option in chosen_options:
            index = piece_index[str(option['piece'])]
            added = int(option['mask']) & ~mask
            gain = added.bit_count()
            incremental = _marginal_cost(piece_types[index], counts[index])
            ranked.append((incremental / gain, incremental, -gain, option))
        ranked.sort(key=lambda item: (item[0], item[1], item[2]))
        if cost + min(item[1] for item in ranked) >= best_cost:
            return

        for _ratio, incremental, _negative_gain, option in ranked:
            if cost + incremental >= best_cost:
                continue
            index = piece_index[str(option['piece'])]
            next_counts = list(counts)
            next_counts[index] += 1
            placement = {
                'id': f'P{len(selected) + 1}',
                'piece': str(option['piece']),
                'row': int(option['row']),
                'col': int(option['col']),
            }
            search(
                mask | int(option['mask']),
                tuple(next_counts),
                occupied | (1 << int(option['square'])),
                cost + incremental,
                [*selected, placement],
            )

    search(0, tuple(0 for _ in piece_types), 0, 0, [])
    return best_cost, best_solution, visited_nodes


def _public_piece_types(piece_types: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            'id': str(piece['id']),
            'label': str(piece['label']),
            'base_cost': int(piece['base_cost']),
            'repeat_surcharge': int(piece['repeat_surcharge']),
            'limit': int(piece['limit']),
            'move_label': str(piece['move_label']),
            'offsets': [{'row': int(row), 'col': int(col)} for row, col in piece['offsets']],
        }
        for piece in piece_types
    ]


def generate_chess_coverage_task(*, seed: int, difficulty: int) -> tuple[dict[str, Any], dict[str, Any]]:
    difficulty = max(1, min(5, int(difficulty)))
    rng = random.Random(f'{GENERATOR_VERSION}:{seed}:{difficulty}')
    piece_types = [deepcopy(piece) for piece in CUSTOM_PIECES]
    max_placements = 4 if difficulty <= 2 else 5 if difficulty <= 4 else 6
    witness_count = 3 if difficulty <= 2 else 4 if difficulty <= 4 else 5
    target_count = 5 + difficulty

    for _ in range(180):
        squares = rng.sample(range(64), witness_count)
        witness: list[dict[str, Any]] = []
        type_counts = {str(piece['id']): 0 for piece in piece_types}
        for index, square in enumerate(squares, start=1):
            available = [
                piece for piece in piece_types if type_counts[str(piece['id'])] < int(piece['limit'])
            ]
            piece = rng.choices(available, weights=[5, 4, 3, 2][: len(available)])[0]
            piece_id = str(piece['id'])
            type_counts[piece_id] += 1
            witness.append({'id': f'P{index}', 'piece': piece_id, 'row': square // 8, 'col': square % 8})
        occupied = {(int(item['row']), int(item['col'])) for item in witness}
        witness_attacks = [
            _custom_attacks(_piece_map(piece_types)[str(item['piece'])], int(item['row']), int(item['col']))
            - occupied
            for item in witness
        ]
        mandatory: set[tuple[int, int]] = set()
        for index, attacks in enumerate(witness_attacks):
            other_attacks = set().union(
                *(value for other_index, value in enumerate(witness_attacks) if other_index != index)
            )
            unique = sorted(attacks - other_attacks)
            if unique:
                mandatory.add(rng.choice(unique))
        union = sorted(set().union(*witness_attacks) - mandatory)
        if len(mandatory) < 2 or len(union) < target_count - len(mandatory):
            continue
        targets = sorted(mandatory | set(rng.sample(union, target_count - len(mandatory))))
        optimal_cost, solution, solver_nodes = _solve_placement_problem(
            targets=targets, piece_types=piece_types, max_placements=max_placements, incumbent=witness
        )
        if not 2 <= len(solution) <= max_placements:
            continue
        if len({str(item['piece']) for item in solution}) < 2:
            continue
        break
    else:
        raise RuntimeError('Unable to generate a custom chess placement task')

    public_piece_types = _public_piece_types(piece_types)
    public = {
        'kind': PUBLIC_KIND,
        'family': FAMILY_KEY,
        'variant': 'custom_jump_placement',
        'prompt': (
            'На доске 8×8 отмечены целевые клетки. Выберите фигуру в панели '
            'и расставьте фигуры так, чтобы каждая цель находилась под боем. '
            'Фигуры ходят не по обычным шахматным правилам: их прыжки показаны '
            'в панели, промежуточные клетки не имеют значения. Стоимость каждой '
            'следующей фигуры одного типа возрастает. Покройте все цели с '
            f'минимальной стоимостью, используя не более {max_placements} фигур.'
        ),
        'board_size': 8,
        'targets': [{'row': row, 'col': col} for row, col in targets],
        'piece_types': public_piece_types,
        'placements': [],
        'covered_targets': [],
        'piece_counts': {str(piece['id']): 0 for piece in piece_types},
        'total_cost': 0,
        'all_covered': False,
        'max_placements': max_placements,
        'response_hint': (
            'Сначала выберите тип фигуры, затем нажмите на свободную клетку. '
            'Нажатие на установленную фигуру убирает её.'
        ),
    }
    private = {
        'family': FAMILY_KEY,
        'generator_version': GENERATOR_VERSION,
        'variant': 'custom_jump_placement',
        'difficulty': difficulty,
        'board_size': 8,
        'targets': [[row, col] for row, col in targets],
        'piece_types': deepcopy(piece_types),
        'placements': [],
        'max_placements': max_placements,
        'next_placement_number': 1,
        'optimal_cost': optimal_cost,
        'optimal_placements': deepcopy(solution),
        'solver_nodes': solver_nodes,
        'interaction': {
            'placement_count': 0,
            'removal_count': 0,
            'reset_count': 0,
            'first_action_latency_ms': None,
            'processed_actions': {},
        },
    }
    return public, private


def transition_chess_coverage_action(
    *,
    action_type: str,
    public_state: dict[str, Any],
    private_state: dict[str, Any],
    client_action_id: str,
    op_id: str | None = None,
    first_action_latency_ms: int | None = None,
) -> Transition:
    normalized_type = action_type.strip().casefold()
    if normalized_type not in {'apply_op', 'reset'}:
        raise ValueError('Chess placement action must be apply_op or reset')
    normalized_op = (op_id or '').strip()
    if normalized_type == 'apply_op' and not normalized_op:
        raise ValueError('apply_op requires op_id')
    normalized_input = normalized_op.casefold() if normalized_type == 'apply_op' else 'reset'
    action_id = client_action_id.strip()
    if not action_id:
        raise ValueError('client_action_id must not be empty')

    next_public = deepcopy(public_state)
    next_private = deepcopy(private_state)
    interaction = next_private['interaction']
    processed = interaction['processed_actions']
    previous = processed.get(action_id)
    if previous is not None:
        if previous['normalized_input'] != normalized_input:
            raise ValueError('client_action_id was reused with another action')
        state = _placement_state(next_private['placements'], next_private)
        return Transition(
            public_state=next_public,
            private_state=next_private,
            accepted=bool(previous['accepted']),
            completed=False,
            reason=str(previous['reason']),
            message=str(previous['message']),
            normalized_input=normalized_input,
            evaluation_state={**state, **_interaction_counts(interaction)},
        )
    if interaction['first_action_latency_ms'] is None and first_action_latency_ms is not None:
        interaction['first_action_latency_ms'] = max(0, int(first_action_latency_ms))

    placements = list(next_private['placements'])
    definitions = _piece_map(next_private['piece_types'])
    targets = {tuple(point) for point in next_private['targets']}
    accepted = False
    if normalized_type == 'reset':
        if placements:
            placements = []
            interaction['reset_count'] = int(interaction['reset_count']) + 1
            accepted, reason = True, 'reset'
            message = 'Расстановка возвращена в начало.'
        else:
            reason, message = 'already_at_start', 'На доске пока нет фигур.'
    else:
        place_match = _PLACE_ACTION.fullmatch(normalized_op)
        remove_match = _REMOVE_ACTION.fullmatch(normalized_op)
        if remove_match:
            placement_id = remove_match.group(1).upper()
            before = len(placements)
            placements = [item for item in placements if item['id'] != placement_id]
            if len(placements) < before:
                interaction['removal_count'] = int(interaction['removal_count']) + 1
                accepted, reason = True, 'removed'
                message = f'Фигура {placement_id} убрана.'
            else:
                reason, message = 'unknown_placement', 'Такой фигуры на доске нет.'
        elif place_match:
            piece_id = place_match.group(1).upper()
            row, col = int(place_match.group(2)), int(place_match.group(3))
            counts = {key: sum(1 for item in placements if item['piece'] == key) for key in definitions}
            if piece_id not in definitions:
                reason, message = 'unknown_piece', 'Такого типа фигуры нет.'
            elif (row, col) in targets:
                reason, message = 'target_cell', 'На целевую клетку ставить фигуру нельзя.'
            elif any(int(item['row']) == row and int(item['col']) == col for item in placements):
                reason, message = 'occupied_cell', 'Клетка уже занята другой фигурой.'
            elif len(placements) >= int(next_private['max_placements']):
                reason, message = 'piece_budget', 'Лимит фигур исчерпан.'
            elif counts[piece_id] >= int(definitions[piece_id]['limit']):
                reason, message = 'piece_limit', 'Лимит фигур этого типа исчерпан.'
            else:
                placement_id = f'P{int(next_private["next_placement_number"])}'
                next_private['next_placement_number'] = int(next_private['next_placement_number']) + 1
                placements.append({'id': placement_id, 'piece': piece_id, 'row': row, 'col': col})
                interaction['placement_count'] = int(interaction['placement_count']) + 1
                accepted, reason = True, 'placed'
                message = f'Фигура {placement_id} установлена.'
        else:
            reason = 'invalid_action'
            message = 'Не удалось распознать действие с фигурой.'

    next_private['placements'] = placements
    state = _placement_state(placements, next_private)
    next_public.update(
        {
            'placements': state['placements'],
            'piece_counts': state['piece_counts'],
            'covered_targets': state['covered_targets'],
            'total_cost': state['total_cost'],
            'all_covered': state['all_covered'],
        }
    )
    message += (
        f' Покрыто {state["covered_count"]} из {state["target_count"]}; стоимость {state["total_cost"]}.'
    )
    processed[action_id] = {
        'normalized_input': normalized_input,
        'accepted': accepted,
        'reason': reason,
        'message': message,
    }
    return Transition(
        public_state=next_public,
        private_state=next_private,
        accepted=accepted,
        completed=False,
        reason=reason,
        message=message,
        normalized_input=normalized_input,
        evaluation_state={**state, **_interaction_counts(interaction)},
    )


def evaluate_chess_coverage_answer(*, answer: str, private_state: dict[str, Any]) -> dict[str, Any]:
    parsed = answer.strip().casefold() in _DONE
    state = _placement_state(private_state.get('placements') or [], private_state)
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
        **_interaction_counts(private_state.get('interaction') or {}),
    }


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
