"""Generator: targets drawn under a random witness placement, then solved exactly."""

from __future__ import annotations

import random
from copy import deepcopy
from typing import Any

from .board import CUSTOM_PIECES, FAMILY_KEY, GENERATOR_VERSION, PUBLIC_KIND, custom_attacks, piece_map
from .solver import solve_placement_problem

GENERATION_ATTEMPTS = 180
WITNESS_PIECE_WEIGHTS = [5, 4, 3, 2]
RESPONSE_HINT = (
    'Сначала выберите тип фигуры, затем нажмите на свободную клетку. '
    'Нажатие на установленную фигуру убирает её.'
)


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


def _random_witness(
    rng: random.Random, piece_types: list[dict[str, Any]], count: int
) -> list[dict[str, Any]]:
    """Pieces on random cells; the targets are then chosen among the cells they attack."""

    squares = rng.sample(range(64), count)
    witness: list[dict[str, Any]] = []
    type_counts = {str(piece['id']): 0 for piece in piece_types}
    for index, square in enumerate(squares, start=1):
        available = [piece for piece in piece_types if type_counts[str(piece['id'])] < int(piece['limit'])]
        piece = rng.choices(available, weights=WITNESS_PIECE_WEIGHTS[: len(available)])[0]
        piece_id = str(piece['id'])
        type_counts[piece_id] += 1
        witness.append({'id': f'P{index}', 'piece': piece_id, 'row': square // 8, 'col': square % 8})
    return witness


def _witness_targets(
    rng: random.Random, witness: list[dict[str, Any]], piece_types: list[dict[str, Any]], target_count: int
) -> list[tuple[int, int]] | None:
    """Targets under the witness: a cell only one piece attacks for each piece, the rest from all attacks."""

    occupied = {(int(item['row']), int(item['col'])) for item in witness}
    witness_attacks = [
        custom_attacks(piece_map(piece_types)[str(item['piece'])], int(item['row']), int(item['col']))
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
        return None
    return sorted(mandatory | set(rng.sample(union, target_count - len(mandatory))))


def _solved_puzzle(
    rng: random.Random, piece_types: list[dict[str, Any]], difficulty: int, max_placements: int
) -> tuple[list[tuple[int, int]], int, list[dict[str, Any]], int]:
    """Targets whose cheapest cover needs at least two pieces of at least two types."""

    witness_count = 3 if difficulty <= 2 else 4 if difficulty <= 4 else 5
    for _ in range(GENERATION_ATTEMPTS):
        witness = _random_witness(rng, piece_types, witness_count)
        targets = _witness_targets(rng, witness, piece_types, 5 + difficulty)
        if targets is None:
            continue
        optimal_cost, solution, solver_nodes = solve_placement_problem(
            targets=targets, piece_types=piece_types, max_placements=max_placements, incumbent=witness
        )
        if not 2 <= len(solution) <= max_placements:
            continue
        if len({str(item['piece']) for item in solution}) < 2:
            continue
        return targets, optimal_cost, solution, solver_nodes
    raise RuntimeError('Unable to generate a custom chess placement task')


def _prompt(max_placements: int) -> str:
    return (
        'На доске 8×8 отмечены целевые клетки. Выберите фигуру в панели '
        'и расставьте фигуры так, чтобы каждая цель находилась под боем. '
        'Фигуры ходят не по обычным шахматным правилам: их прыжки показаны '
        'в панели, промежуточные клетки не имеют значения. Стоимость каждой '
        'следующей фигуры одного типа возрастает. Покройте все цели с '
        f'минимальной стоимостью, используя не более {max_placements} фигур.'
    )


def _public_state(
    piece_types: list[dict[str, Any]], targets: list[tuple[int, int]], max_placements: int
) -> dict[str, Any]:
    return {
        'kind': PUBLIC_KIND,
        'family': FAMILY_KEY,
        'variant': 'custom_jump_placement',
        'prompt': _prompt(max_placements),
        'board_size': 8,
        'targets': [{'row': row, 'col': col} for row, col in targets],
        'piece_types': _public_piece_types(piece_types),
        'placements': [],
        'covered_targets': [],
        'piece_counts': {str(piece['id']): 0 for piece in piece_types},
        'total_cost': 0,
        'all_covered': False,
        'max_placements': max_placements,
        'response_hint': RESPONSE_HINT,
    }


def generate_chess_coverage_task(*, seed: int, difficulty: int) -> tuple[dict[str, Any], dict[str, Any]]:
    difficulty = max(1, min(5, int(difficulty)))
    rng = random.Random(f'{GENERATOR_VERSION}:{seed}:{difficulty}')
    piece_types = [deepcopy(piece) for piece in CUSTOM_PIECES]
    max_placements = 4 if difficulty <= 2 else 5 if difficulty <= 4 else 6
    targets, optimal_cost, solution, solver_nodes = _solved_puzzle(
        rng, piece_types, difficulty, max_placements
    )
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
    return _public_state(piece_types, targets, max_placements), private
