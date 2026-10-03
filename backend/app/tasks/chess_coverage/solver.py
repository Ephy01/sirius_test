"""Exact solver: the cheapest set of placements that covers every target."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .board import custom_attacks, marginal_cost, placement_cost


def _placement_options(
    targets: list[tuple[int, int]], piece_types: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Every piece on every free cell that attacks at least one target, with the targets as a bit mask."""

    target_set = set(targets)
    options: list[dict[str, Any]] = []
    for row in range(8):
        for col in range(8):
            if (row, col) in target_set:
                continue
            for piece in piece_types:
                mask = sum(
                    1 << index
                    for index, target in enumerate(targets)
                    if target in custom_attacks(piece, row, col)
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
    return options


class _PlacementSearch:
    """Branch and bound for the cheapest cover, started from a known solution.

    A node branches on the uncovered target with the fewest legal placements and
    tries the placements that pay least per newly covered target first.
    """

    def __init__(
        self,
        targets: list[tuple[int, int]],
        piece_types: list[dict[str, Any]],
        max_placements: int,
        incumbent: list[dict[str, Any]],
    ) -> None:
        options = _placement_options(targets, piece_types)
        self.piece_types = piece_types
        self.max_placements = max_placements
        self.target_count = len(targets)
        self.full_mask = (1 << len(targets)) - 1
        self.piece_index = {str(piece['id']): index for index, piece in enumerate(piece_types)}
        self.by_target = [
            [option for option in options if int(option['mask']) & (1 << index)]
            for index in range(len(targets))
        ]
        self.best_cost = placement_cost(incumbent, piece_types)
        self.best_solution = deepcopy(incumbent)
        self.memo: dict[tuple[int, tuple[int, ...], int], int] = {}
        self.visited_nodes = 0

    def _legal_options(
        self, target_index: int, counts: tuple[int, ...], occupied: int
    ) -> list[dict[str, Any]]:
        legal = []
        for option in self.by_target[target_index]:
            square_bit = 1 << int(option['square'])
            index = self.piece_index[str(option['piece'])]
            if occupied & square_bit:
                continue
            if counts[index] >= int(self.piece_types[index]['limit']):
                continue
            legal.append(option)
        return legal

    def _branching_options(
        self, mask: int, counts: tuple[int, ...], occupied: int
    ) -> list[dict[str, Any]] | None:
        """Placements for the most constrained uncovered target; ``None`` if some target cannot be covered."""

        chosen_options: list[dict[str, Any]] | None = None
        for target_index in range(self.target_count):
            if mask & (1 << target_index):
                continue
            legal = self._legal_options(target_index, counts, occupied)
            if not legal:
                return None
            if chosen_options is None or len(legal) < len(chosen_options):
                chosen_options = legal
        return chosen_options

    def _ranked(
        self, options: list[dict[str, Any]], mask: int, counts: tuple[int, ...]
    ) -> list[tuple[float, int, int, dict[str, Any]]]:
        ranked: list[tuple[float, int, int, dict[str, Any]]] = []
        for option in options:
            index = self.piece_index[str(option['piece'])]
            added = int(option['mask']) & ~mask
            gain = added.bit_count()
            incremental = marginal_cost(self.piece_types[index], counts[index])
            ranked.append((incremental / gain, incremental, -gain, option))
        ranked.sort(key=lambda item: (item[0], item[1], item[2]))
        return ranked

    def _is_pruned(self, mask: int, counts: tuple[int, ...], occupied: int, cost: int, depth: int) -> bool:
        if depth >= self.max_placements or cost >= self.best_cost:
            return True
        key = (mask, counts, occupied)
        previous_cost = self.memo.get(key)
        if previous_cost is not None and previous_cost <= cost:
            return True
        self.memo[key] = cost
        return False

    def search(
        self, mask: int, counts: tuple[int, ...], occupied: int, cost: int, selected: list[dict[str, Any]]
    ) -> None:
        self.visited_nodes += 1
        if mask == self.full_mask:
            if cost < self.best_cost:
                self.best_cost = cost
                self.best_solution = deepcopy(selected)
            return
        if self._is_pruned(mask, counts, occupied, cost, len(selected)):
            return
        options = self._branching_options(mask, counts, occupied)
        if options is None:
            return
        ranked = self._ranked(options, mask, counts)
        if cost + min(item[1] for item in ranked) >= self.best_cost:
            return

        for _ratio, incremental, _negative_gain, option in ranked:
            if cost + incremental >= self.best_cost:
                continue
            index = self.piece_index[str(option['piece'])]
            next_counts = list(counts)
            next_counts[index] += 1
            placement = {
                'id': f'P{len(selected) + 1}',
                'piece': str(option['piece']),
                'row': int(option['row']),
                'col': int(option['col']),
            }
            self.search(
                mask | int(option['mask']),
                tuple(next_counts),
                occupied | (1 << int(option['square'])),
                cost + incremental,
                [*selected, placement],
            )


def solve_placement_problem(
    *,
    targets: list[tuple[int, int]],
    piece_types: list[dict[str, Any]],
    max_placements: int,
    incumbent: list[dict[str, Any]],
) -> tuple[int, list[dict[str, Any]], int]:
    """Cost and placements of a cheapest cover, and the number of search nodes it took."""

    search = _PlacementSearch(targets, piece_types, max_placements, incumbent)
    search.search(0, tuple(0 for _ in piece_types), 0, 0, [])
    return search.best_cost, search.best_solution, search.visited_nodes
