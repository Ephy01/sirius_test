"""Configuration space of geo_zendo: small graphs on a fixed set of points.

The population, atoms, rule enumeration, mutation order and object keys are
part of the generator version: changing them changes every generated task.
"""

from __future__ import annotations

from typing import Any

from ..graphs import CARD_COORDINATES, MiniGraph, normalize_edges


def graph_key(graph: MiniGraph) -> tuple[object, ...]:
    return graph.points, graph.edges, graph.colors


def serialize_graph(graph: MiniGraph) -> dict[str, Any]:
    return {
        'points': [list(point) for point in graph.points],
        'edges': [list(edge) for edge in graph.edges],
        'colors': list(graph.colors),
    }


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
                MiniGraph(points=graph.points, edges=normalize_edges(next_edges), colors=graph.colors)
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
            mutations.append(MiniGraph(points=tuple(next_points), edges=graph.edges, colors=graph.colors))
    unique: dict[tuple[object, ...], MiniGraph] = {}
    for mutation in mutations:
        unique.setdefault(graph_key(mutation), mutation)
    return tuple(unique.values())
