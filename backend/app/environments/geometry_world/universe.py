"""GraphUniverse: the geo_zendo configuration space behind the engine.

This is a straight extraction of the pre-refactoring geo_zendo v2 code.
The population, atoms, rule enumeration, mutation order and object keys
must stay byte-for-byte identical to keep ``geometry-zendo-v2`` replayable.
"""

from __future__ import annotations

from typing import Any, Hashable

from ..core.rule_dsl import GRAPH_ATOMS, Atom, Rule, enumerate_rules
from ..core.rule_space import DEFAULT_DSL_VERSION, build_graph_universe
from .atlas import CARD_COORDINATES, MiniGraph, _normalize_edges

UNIVERSE_VERSION = "graph-universe-v1"


def graph_key(graph: MiniGraph) -> tuple[object, ...]:
    return graph.points, graph.edges, graph.colors


def serialize_graph(graph: MiniGraph) -> dict[str, Any]:
    return {
        "points": [list(point) for point in graph.points],
        "edges": [list(edge) for edge in graph.edges],
        "colors": list(graph.colors),
    }


def deserialize_graph(value: dict[str, Any]) -> MiniGraph:
    return MiniGraph(
        points=tuple(
            (int(point[0]), int(point[1]))
            for point in value["points"]
        ),
        edges=_normalize_edges(
            (int(edge[0]), int(edge[1]))
            for edge in value["edges"]
        ),
        colors=tuple(str(color) for color in value["colors"]),
    )


def graph_mutations(graph: MiniGraph) -> tuple[MiniGraph, ...]:
    """All one-edge toggles and one-point relocations in stable order."""

    mutations: list[MiniGraph] = []
    edge_set = set(graph.edges)
    for first in range(len(graph.points)):
        for second in range(first + 1, len(graph.points)):
            edge = (first, second)
            next_edges = set(edge_set)
            if edge in next_edges:
                next_edges.remove(edge)
            else:
                next_edges.add(edge)
            mutations.append(
                MiniGraph(
                    points=graph.points,
                    edges=_normalize_edges(next_edges),
                    colors=graph.colors,
                )
            )

    occupied = set(graph.points)
    for index in range(len(graph.points)):
        for coordinate in CARD_COORDINATES:
            if coordinate in occupied and coordinate != graph.points[index]:
                continue
            if coordinate == graph.points[index]:
                continue
            next_points = list(graph.points)
            next_points[index] = coordinate
            mutations.append(
                MiniGraph(
                    points=tuple(next_points),
                    edges=graph.edges,
                    colors=graph.colors,
                )
            )
    unique: dict[tuple[object, ...], MiniGraph] = {}
    for mutation in mutations:
        unique.setdefault(graph_key(mutation), mutation)
    return tuple(unique.values())


class GraphUniverse:
    """The mini-graph universe extracted from geo_zendo v2 unchanged."""

    universe_version = UNIVERSE_VERSION
    dsl_version = DEFAULT_DSL_VERSION

    def population(self) -> tuple[MiniGraph, ...]:
        return build_graph_universe(self.dsl_version)

    def atoms(self) -> tuple[Atom, ...]:
        return GRAPH_ATOMS

    def enumerate_rules(self) -> tuple[Rule, ...]:
        return enumerate_rules(GRAPH_ATOMS)

    def mutations(self, obj: MiniGraph) -> tuple[MiniGraph, ...]:
        return graph_mutations(obj)

    def object_key(self, obj: MiniGraph) -> Hashable:
        return graph_key(obj)

    def render_payload(self, obj: MiniGraph) -> dict[str, Any]:
        return serialize_graph(obj)


__all__ = [
    "GraphUniverse",
    "UNIVERSE_VERSION",
    "deserialize_graph",
    "graph_key",
    "graph_mutations",
    "serialize_graph",
]
