"""Small drawn graphs shared by the graph-based task families."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

PUBLIC_KIND = 'geometry_atlas'

POINT_LABELS = 'ABCDEFGHIJKL'
POINT_COLORS = ('cyan', 'plum', 'violet')
CARD_COORDINATES = ((-3, 0), (-2, -2), (0, -3), (2, -2), (3, 0), (2, 2), (0, 3), (-2, 2), (0, 0))
GRAPH_COORDINATES = ((0, 4), (3, 3), (4, 0), (3, -3), (0, -4), (-3, -3), (-4, 0), (-3, 3))


@dataclass(frozen=True)
class MiniGraph:
    points: tuple[tuple[int, int], ...]
    edges: tuple[tuple[int, int], ...]
    colors: tuple[str, ...]


def normalize_edges(edges: Iterable[tuple[int, int]]) -> tuple[tuple[int, int], ...]:
    return tuple(
        sorted({(min(first, second), max(first, second)) for first, second in edges if first != second})
    )


def scene(
    *, graphs: Sequence[tuple[str, MiniGraph, str]], bounds: tuple[int, int, int, int] = (-4, 4, -4, 4)
) -> dict[str, Any]:
    points: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for group, graph, edge_color in graphs:
        for index, ((x, y), color) in enumerate(zip(graph.points, graph.colors, strict=True)):
            label = POINT_LABELS[index]
            points.append(
                {'id': f'{group}:{label}', 'group': group, 'x': x, 'y': y, 'label': label, 'color': color}
            )
        for edge_index, (first, second) in enumerate(graph.edges, start=1):
            edges.append(
                {
                    'id': f'{group}:E{edge_index}',
                    'group': group,
                    'source': f'{group}:{POINT_LABELS[first]}',
                    'target': f'{group}:{POINT_LABELS[second]}',
                    'color': edge_color,
                }
            )
    min_x, max_x, min_y, max_y = bounds
    return {
        'bounds': {'min_x': min_x, 'max_x': max_x, 'min_y': min_y, 'max_y': max_y},
        'points': points,
        'edges': edges,
    }


def public_state(
    *,
    family: str,
    variant: str,
    prompt: str,
    scene: dict[str, Any],
    content: dict[str, Any],
    mode: str,
    commands: list[str],
    response_hint: str,
) -> dict[str, Any]:
    return {
        'kind': PUBLIC_KIND,
        'family': family,
        'variant': variant,
        'prompt': prompt,
        'scene': scene,
        'content': content,
        'interaction': {'mode': mode, 'commands': commands},
        'response_hint': response_hint,
    }


def adjacency(graph: MiniGraph) -> tuple[frozenset[int], ...]:
    neighbors = [set() for _ in graph.points]
    for first, second in graph.edges:
        neighbors[first].add(second)
        neighbors[second].add(first)
    return tuple(frozenset(items) for items in neighbors)


def scene_cards(public_state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Group the shared scene into per-card vertex and edge lists."""

    drawn = public_state.get('scene') if isinstance(public_state.get('scene'), dict) else {}
    cards: dict[str, dict[str, Any]] = {}
    for point in drawn.get('points') or []:
        if not isinstance(point, dict) or not isinstance(point.get('group'), str):
            continue
        card = cards.setdefault(point['group'], {'vertices': [], 'edges': []})
        card['vertices'].append(
            {
                'id': point.get('id'),
                'label': point.get('label'),
                'x': point.get('x'),
                'y': point.get('y'),
                'color': point.get('color'),
            }
        )
    for edge in drawn.get('edges') or []:
        if not isinstance(edge, dict) or not isinstance(edge.get('group'), str):
            continue
        card = cards.setdefault(edge['group'], {'vertices': [], 'edges': []})
        card['edges'].append({'source': edge.get('source'), 'target': edge.get('target'), 'directed': False})
    return cards
