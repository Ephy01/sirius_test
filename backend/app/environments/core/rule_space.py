"""Versioned, process-local cache of distilled graph rule catalogues."""

from __future__ import annotations

import itertools
import random
import threading
from dataclasses import dataclass

from ..geometry_world.atlas import MiniGraph
from .rule_dsl import (
    GRAPH_ATOMS,
    MAX_BASE_RATE,
    MIN_BASE_RATE,
    Rule,
    compile_truth_masks,
    distill_rules,
    enumerate_rules,
    rule_truth_mask,
)

DEFAULT_DSL_VERSION = "graph-dsl-v1"
UNIVERSE_SIZE = 1200
_VERSION_SEEDS = {
    DEFAULT_DSL_VERSION: 0x47A7_2026,
}
_COORDINATES = (
    (-4, 0),
    (-3, -3),
    (0, -4),
    (3, -3),
    (4, 0),
    (3, 3),
    (0, 4),
    (-3, 3),
    (0, 0),
)
_CACHE: dict[str, "RuleSpace"] = {}
_CACHE_LOCK = threading.Lock()


def _normalize_edges(
    edges: list[tuple[int, int]] | tuple[tuple[int, int], ...],
) -> tuple[tuple[int, int], ...]:
    return tuple(
        sorted(
            {
                (min(first, second), max(first, second))
                for first, second in edges
                if first != second
            }
        )
    )


def _graph_key(graph: MiniGraph) -> tuple[object, ...]:
    return graph.points, graph.edges


def _forced_graphs() -> tuple[MiniGraph, ...]:
    square = ((-3, -3), (3, -3), (3, 3), (-3, 3))
    crossing = ((-3, -3), (3, 3), (-3, 3), (3, -3))
    triangle_and_point = ((-3, -2), (3, -2), (0, 3), (0, 0))
    edge_sets = (
        ((0, 1), (1, 2), (2, 3)),
        ((0, 1), (1, 2), (2, 3), (3, 0)),
        ((0, 1), (1, 2), (2, 0)),
        ((0, 1), (2, 3)),
        ((0, 1), (0, 2), (0, 3)),
        ((0, 1),),
        (),
    )
    points = (
        square,
        square,
        triangle_and_point,
        crossing,
        square,
        triangle_and_point,
        square,
    )
    return tuple(
        MiniGraph(
            points=graph_points,
            edges=_normalize_edges(edge_set),
            colors=("cyan",) * len(graph_points),
        )
        for graph_points, edge_set in zip(points, edge_sets, strict=True)
    )


def _random_graph(rng: random.Random) -> MiniGraph:
    vertex_count = rng.randint(3, 7)
    points = tuple(rng.sample(_COORDINATES, vertex_count))
    possible_edges = tuple(itertools.combinations(range(vertex_count), 2))
    # A varying density is important for balanced primitives and composites.
    density = rng.uniform(0.12, 0.88)
    edges = _normalize_edges(
        [
            edge
            for edge in possible_edges
            if rng.random() < density
        ]
    )
    return MiniGraph(
        points=points,
        edges=edges,
        colors=("cyan",) * vertex_count,
    )


def build_graph_universe(
    dsl_version: str = DEFAULT_DSL_VERSION,
) -> tuple[MiniGraph, ...]:
    """Build the immutable deterministic universe for one DSL version."""

    try:
        seed = _VERSION_SEEDS[dsl_version]
    except KeyError as error:
        raise ValueError(f"Unsupported DSL version: {dsl_version!r}") from error
    rng = random.Random(seed)
    graphs: list[MiniGraph] = []
    seen: set[tuple[object, ...]] = set()
    for graph in _forced_graphs():
        key = _graph_key(graph)
        if key not in seen:
            seen.add(key)
            graphs.append(graph)
    while len(graphs) < UNIVERSE_SIZE:
        graph = _random_graph(rng)
        key = _graph_key(graph)
        if key in seen:
            continue
        seen.add(key)
        graphs.append(graph)
    return tuple(graphs)


@dataclass(frozen=True, slots=True)
class RuleSpace:
    """A stable rule catalogue and its universe-level compiled masks."""

    dsl_version: str
    universe: tuple[MiniGraph, ...]
    rules: tuple[Rule, ...]
    truth_masks: tuple[int, ...]
    mdl_buckets: tuple[tuple[int, ...], ...]

    @property
    def all_rules_mask(self) -> int:
        return (1 << len(self.rules)) - 1

    def indices_for_difficulty(self, difficulty: int) -> tuple[int, ...]:
        if not 1 <= difficulty <= 5:
            raise ValueError("difficulty must be between 1 and 5")
        return self.mdl_buckets[difficulty - 1]

    def truth_mask_for_graph(self, graph: MiniGraph) -> int:
        return rule_truth_mask(graph, self.rules)

    def base_rate(self, rule_index: int) -> float:
        return self.truth_masks[rule_index].bit_count() / len(self.universe)


def _mdl_bucket(rule: Rule) -> int:
    if rule.mdl <= 4:
        return 1
    if rule.mdl <= 6:
        return 2
    if rule.mdl <= 8:
        return 3
    if rule.mdl <= 10:
        return 4
    return 5


def _build_rule_space(dsl_version: str) -> RuleSpace:
    universe = build_graph_universe(dsl_version)
    raw_rules = enumerate_rules(GRAPH_ATOMS)
    rules = distill_rules(
        raw_rules,
        universe,
        min_base_rate=MIN_BASE_RATE,
        max_base_rate=MAX_BASE_RATE,
        atoms=GRAPH_ATOMS,
    )
    truth_masks = compile_truth_masks(rules, universe, atoms=GRAPH_ATOMS)
    buckets: list[list[int]] = [[] for _ in range(5)]
    for rule_index, rule in enumerate(rules):
        buckets[_mdl_bucket(rule) - 1].append(rule_index)
    if any(not bucket for bucket in buckets):
        raise RuntimeError(
            f"DSL {dsl_version!r} produced an empty MDL difficulty bucket"
        )
    return RuleSpace(
        dsl_version=dsl_version,
        universe=universe,
        rules=rules,
        truth_masks=truth_masks,
        mdl_buckets=tuple(tuple(bucket) for bucket in buckets),
    )


def get_rule_space(
    dsl_version: str = DEFAULT_DSL_VERSION,
) -> RuleSpace:
    """Return the once-per-process cached rule space for ``dsl_version``."""

    if dsl_version not in _VERSION_SEEDS:
        raise ValueError(f"Unsupported DSL version: {dsl_version!r}")
    cached = _CACHE.get(dsl_version)
    if cached is not None:
        return cached
    with _CACHE_LOCK:
        cached = _CACHE.get(dsl_version)
        if cached is None:
            cached = _build_rule_space(dsl_version)
            _CACHE[dsl_version] = cached
    return cached


def clear_rule_space_cache() -> None:
    """Clear the process cache (intended for deterministic unit benchmarks)."""

    with _CACHE_LOCK:
        _CACHE.clear()


__all__ = [
    "DEFAULT_DSL_VERSION",
    "UNIVERSE_SIZE",
    "RuleSpace",
    "build_graph_universe",
    "clear_rule_space_cache",
    "get_rule_space",
]
