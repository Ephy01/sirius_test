"""The board of chess_coverage: custom leaping pieces, their attacks and the cost of a placement."""

from __future__ import annotations

from typing import Any

FAMILY_KEY = 'chess_coverage'
GENERATOR_VERSION = 'chess-coverage-v3'
READABLE_VERSIONS = ('chess-coverage-v2',)
PUBLIC_KIND = 'chess_coverage'

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
            (-2, 2),
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


def _inside(row: int, col: int, size: int) -> bool:
    return 0 <= row < size and 0 <= col < size


def piece_map(piece_types: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(piece['id']): piece for piece in piece_types}


def custom_attacks(piece: dict[str, Any], row: int, col: int, size: int = 8) -> set[tuple[int, int]]:
    return {
        (row + int(dr), col + int(dc))
        for dr, dc in piece['offsets']
        if _inside(row + int(dr), col + int(dc), size)
    }


def marginal_cost(piece: dict[str, Any], existing_count: int) -> int:
    return int(piece['base_cost']) + int(piece['repeat_surcharge']) * existing_count


def placement_cost(placements: list[dict[str, Any]], piece_types: list[dict[str, Any]]) -> int:
    definitions = piece_map(piece_types)
    counts = {piece_id: 0 for piece_id in definitions}
    total = 0
    for placement in placements:
        piece_id = str(placement['piece'])
        total += marginal_cost(definitions[piece_id], counts[piece_id])
        counts[piece_id] += 1
    return total


def placement_state(placements: list[dict[str, Any]], private_state: dict[str, Any]) -> dict[str, Any]:
    definitions = piece_map(private_state['piece_types'])
    targets = [tuple(point) for point in private_state['targets']]
    covered: set[tuple[int, int]] = set()
    counts = {piece_id: 0 for piece_id in definitions}
    public_placements: list[dict[str, Any]] = []
    total_cost = 0
    for placement in sorted(placements, key=lambda item: int(str(item['id'])[1:])):
        piece_id = str(placement['piece'])
        definition = definitions[piece_id]
        cost = marginal_cost(definition, counts[piece_id])
        counts[piece_id] += 1
        total_cost += cost
        row, col = int(placement['row']), int(placement['col'])
        attacked = custom_attacks(definition, row, col)
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


def interaction_counts(interaction: dict[str, Any]) -> dict[str, Any]:
    return {
        'placement_count': int(interaction.get('placement_count') or 0),
        'removal_count': int(interaction.get('removal_count') or 0),
        'reset_count': int(interaction.get('reset_count') or 0),
        'first_action_latency_ms': interaction.get('first_action_latency_ms'),
    }
