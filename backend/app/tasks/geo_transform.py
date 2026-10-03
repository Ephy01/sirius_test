"""geo_transform: recognise which symmetry of the square moved a figure."""

from __future__ import annotations

import random
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .answers import strip_answer_command
from .family import State, TaskFamily
from .graphs import CARD_COORDINATES, MiniGraph, normalize_edges, public_state, scene, scene_cards

FAMILY_KEY = 'geo_transform'
GENERATOR_VERSION = 'geometry-atlas-v1'


@dataclass(frozen=True)
class D4Transform:
    key: str
    label: str
    apply: Callable[[int, int], tuple[int, int]]


def _identity(x: int, y: int) -> tuple[int, int]:
    return x, y


def _rotate_90(x: int, y: int) -> tuple[int, int]:
    return -y, x


def _rotate_180(x: int, y: int) -> tuple[int, int]:
    return -x, -y


def _rotate_270(x: int, y: int) -> tuple[int, int]:
    return y, -x


def _reflect_x(x: int, y: int) -> tuple[int, int]:
    return x, -y


def _reflect_y(x: int, y: int) -> tuple[int, int]:
    return -x, y


def _reflect_main_diagonal(x: int, y: int) -> tuple[int, int]:
    return y, x


def _reflect_anti_diagonal(x: int, y: int) -> tuple[int, int]:
    return -y, -x


D4_TRANSFORMS = (
    D4Transform('identity', 'Тождественное преобразование', _identity),
    D4Transform('rotate_90', 'Поворот на 90° против часовой стрелки', _rotate_90),
    D4Transform('rotate_180', 'Поворот на 180°', _rotate_180),
    D4Transform('rotate_270', 'Поворот на 270° против часовой стрелки', _rotate_270),
    D4Transform('reflect_x', 'Отражение относительно оси x', _reflect_x),
    D4Transform('reflect_y', 'Отражение относительно оси y', _reflect_y),
    D4Transform('reflect_main', 'Отражение относительно прямой y = x', _reflect_main_diagonal),
    D4Transform('reflect_anti', 'Отражение относительно прямой y = -x', _reflect_anti_diagonal),
)
D4_BY_KEY = {transform.key: transform for transform in D4_TRANSFORMS}


def _transform_keys_for_difficulty(difficulty: int) -> tuple[str, ...]:
    if difficulty <= 1:
        return ('identity', 'rotate_90', 'rotate_180', 'rotate_270')
    if difficulty == 2:
        return ('identity', 'rotate_90', 'rotate_180', 'rotate_270', 'reflect_x', 'reflect_y')
    return tuple(transform.key for transform in D4_TRANSFORMS)


def _transform_graph(graph: MiniGraph, transform: D4Transform) -> MiniGraph:
    return MiniGraph(
        points=tuple(transform.apply(x, y) for x, y in graph.points), edges=graph.edges, colors=graph.colors
    )


def generate_geo_transform_task(*, seed: int, difficulty: int) -> tuple[dict[str, Any], dict[str, Any]]:
    if difficulty < 1:
        raise ValueError('difficulty must be at least 1')
    rng = random.Random(seed)
    candidate_keys = list(_transform_keys_for_difficulty(difficulty))
    selected_key = rng.choice(candidate_keys)
    selected_transform = D4_BY_KEY[selected_key]

    additional_points = rng.sample(
        [coordinate for coordinate in CARD_COORDINATES if coordinate not in {(1, 2), (0, 0)}],
        2 + min(1, difficulty // 3),
    )
    source_points = ((1, 2), *additional_points)
    source_edges = normalize_edges((index, index + 1) for index in range(len(source_points) - 1))
    source = MiniGraph(points=source_points, edges=source_edges, colors=tuple('cyan' for _ in source_points))
    image = _transform_graph(
        MiniGraph(points=source.points, edges=source.edges, colors=tuple('plum' for _ in source.points)),
        selected_transform,
    )

    rng.shuffle(candidate_keys)
    cards = [
        {'id': f'T{index}', 'label': D4_BY_KEY[key].label}
        for index, key in enumerate(candidate_keys, start=1)
    ]
    card_key_map = {card['id']: key for card, key in zip(cards, candidate_keys, strict=True)}
    correct_card_id = next(card_id for card_id, key in card_key_map.items() if key == selected_key)
    public = public_state(
        family=FAMILY_KEY,
        variant='identify_d4_transform',
        prompt=(
            'К исходной фигуре (source) применено некоторое '
            'преобразование и получен образ (image). Координатная плоскость '
            'и подписи вершин сохраняются. Твоя задача — выбрать это '
            'преобразование.'
        ),
        scene=scene(graphs=[('source', source, 'cyan'), ('image', image, 'plum')]),
        content={'source_group': 'source', 'image_group': 'image', 'answer_cards': cards},
        mode='single_answer',
        commands=['/answer <card_id>'],
        response_hint='Например: /answer T3.',
    )
    private = {
        'family': FAMILY_KEY,
        'variant': 'identify_d4_transform',
        'difficulty': difficulty,
        'transform_key': selected_key,
        'card_key_map': card_key_map,
        'correct_card_id': correct_card_id,
        'source_points': [list(point) for point in source.points],
        'image_points': [list(point) for point in image.points],
    }
    return public, private


def _parse_card_answer(answer: str) -> str | None:
    match = re.fullmatch(r't(\d+)', strip_answer_command(answer))
    return f'T{int(match.group(1))}' if match else None


def evaluate_geo_transform_answer(*, answer: str, private_state: dict[str, Any]) -> dict[str, Any]:
    submitted_card_id = _parse_card_answer(answer)
    available_cards = set(private_state['card_key_map'])
    parsed = submitted_card_id in available_cards
    return {
        'correct': parsed and submitted_card_id == private_state['correct_card_id'],
        'parsed': parsed,
        'submitted_card_id': submitted_card_id if parsed else None,
    }


def _debug_details(private_state: State) -> list[str]:
    card_map = private_state.get('card_key_map') or {}
    return [
        f'Загаданное преобразование: {private_state.get("transform_key")}',
        *(f'  {card_id} → {card_map[card_id]}' for card_id in sorted(card_map)),
    ]


def _ai_context(visible_state: State) -> State:
    content = visible_state.get('content') if isinstance(visible_state.get('content'), dict) else {}
    cards = scene_cards(visible_state)

    def figure(group: Any) -> State:
        if isinstance(group, str) and group in cards:
            return {'id': group, **cards[group]}
        return {'id': group, 'vertices': [], 'edges': []}

    return {
        'source': figure(content.get('source_group')),
        'image': figure(content.get('image_group')),
        'answerCards': content.get('answer_cards'),
    }


FAMILY = TaskFamily(
    key=FAMILY_KEY,
    version=GENERATOR_VERSION,
    generate=lambda seed, difficulty, context: generate_geo_transform_task(seed=seed, difficulty=difficulty),
    evaluate=lambda answer, private_state: evaluate_geo_transform_answer(
        answer=answer, private_state=private_state
    ),
    aliases=('geometry_transform',),
    reference_answer=lambda private_state: (f'/answer {private_state.get("correct_card_id")}', []),
    debug_details=_debug_details,
    ai_context=_ai_context,
)
