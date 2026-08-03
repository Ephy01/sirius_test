"""point_zendo: hidden rules over point configurations on a 12×12 grid.

Five to eight distinct lattice points. Collinear triples and
parallelograms are frequent on an integer grid, while central symmetry
and concyclic quadruples are naturally rare, so the population sampler
mixes targeted constructions ("with property" / "without") and records
its rejection metrics in the build log.
"""

from __future__ import annotations

import itertools
import random
from typing import Any, Hashable

from ..core.rule_dsl import Atom, Rule, enumerate_rules
from ..core.zendo_engine import (
    PROBE_BUDGET,
    evaluate_zendo_answer,
    get_universe_space,
    rule_hint_category,
    select_material,
    transition_zendo_hint,
    transition_zendo_probe,
)

FAMILY_KEY = "point_zendo"
GENERATOR_VERSION = "point-zendo-v1"
PUBLIC_KIND = "point_zendo"
UNIVERSE_VERSION = "point-universe-v1"
DSL_VERSION = "point-dsl-v1"

GRID_SIZE = 12
MIN_POINTS = 5
MAX_POINTS = 8
POPULATION_SIZE = 1200
_POPULATION_SEED = 0x9017_2026

PointConfig = tuple[tuple[int, int], ...]


def _cross(
    origin: tuple[int, int],
    first: tuple[int, int],
    second: tuple[int, int],
) -> int:
    return (
        (first[0] - origin[0]) * (second[1] - origin[1])
        - (first[1] - origin[1]) * (second[0] - origin[0])
    )


def _three_collinear(config: PointConfig) -> bool:
    return any(
        _cross(a, b, c) == 0
        for a, b, c in itertools.combinations(config, 3)
    )


def _strict_convex_hull(config: PointConfig) -> list[tuple[int, int]]:
    points = sorted(config)
    if len(points) <= 2:
        return points

    def half(iterable: list[tuple[int, int]]) -> list[tuple[int, int]]:
        chain: list[tuple[int, int]] = []
        for point in iterable:
            while (
                len(chain) >= 2
                and _cross(chain[-2], chain[-1], point) <= 0
            ):
                chain.pop()
            chain.append(point)
        return chain

    lower = half(points)
    upper = half(points[::-1])
    return lower[:-1] + upper[:-1]


def _convex_position(config: PointConfig) -> bool:
    return len(_strict_convex_hull(config)) == len(config)


def _central_symmetry(config: PointConfig) -> bool:
    count = len(config)
    sum_x = sum(x for x, _y in config)
    sum_y = sum(y for _x, y in config)
    if (2 * sum_x) % count or (2 * sum_y) % count:
        return False
    doubled_center = ((2 * sum_x) // count, (2 * sum_y) // count)
    occupied = set(config)
    return all(
        (doubled_center[0] - x, doubled_center[1] - y) in occupied
        for x, y in config
    )


def _four_parallelogram(config: PointConfig) -> bool:
    pairs_by_sum: dict[tuple[int, int], list[tuple[int, int]]] = {}
    indexed = list(enumerate(config))
    for (first_index, first), (second_index, second) in itertools.combinations(
        indexed, 2
    ):
        key = (first[0] + second[0], first[1] + second[1])
        pairs_by_sum.setdefault(key, []).append((first_index, second_index))
    for pairs in pairs_by_sum.values():
        if len(pairs) < 2:
            continue
        for (a, c), (b, d) in itertools.combinations(pairs, 2):
            if {a, c} & {b, d}:
                continue
            quad = (config[a], config[b], config[c], config[d])
            if any(
                _cross(quad[0], quad[1], point) != 0
                for point in quad[2:]
            ):
                return True
    return False


def _concyclic(quad: tuple[tuple[int, int], ...]) -> bool:
    if any(
        _cross(a, b, c) == 0
        for a, b, c in itertools.combinations(quad, 3)
    ):
        return False
    (ax, ay), (bx, by), (cx, cy), (dx, dy) = quad
    rows = []
    for x, y in ((ax, ay), (bx, by), (cx, cy), (dx, dy)):
        rows.append((x * x + y * y, x, y, 1))

    def det3(matrix: list[tuple[int, int, int]]) -> int:
        (a, b, c), (d, e, f), (g, h, i) = matrix
        return a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)

    total = 0
    for column in range(4):
        minor = [
            tuple(value for idx, value in enumerate(row) if idx != column)
            for row in rows[1:]
        ]
        sign = -1 if column % 2 else 1
        total += sign * rows[0][column] * det3(minor)
    return total == 0


def _four_concyclic(config: PointConfig) -> bool:
    return any(
        _concyclic(quad)
        for quad in itertools.combinations(config, 4)
    )


def _distances_distinct(config: PointConfig) -> bool:
    seen: set[int] = set()
    for (ax, ay), (bx, by) in itertools.combinations(config, 2):
        squared = (ax - bx) ** 2 + (ay - by) ** 2
        if squared in seen:
            return False
        seen.add(squared)
    return True


# Order is part of point-dsl-v1 and must only change with a new DSL version.
POINT_ATOMS: tuple[Atom, ...] = (
    Atom("three_collinear", 3, _three_collinear),
    Atom("convex_position", 3, _convex_position),
    Atom("distances_distinct", 3, _distances_distinct),
    Atom("central_symmetry", 4, _central_symmetry),
    Atom("four_parallelogram", 4, _four_parallelogram),
    Atom("four_concyclic", 4, _four_concyclic),
)


ATOM_DESCRIPTIONS = {
    "three_collinear": "какие-то 3 точки лежат на одной прямой",
    "convex_position": "все точки — вершины выпуклой оболочки",
    "distances_distinct": "все попарные расстояния различны",
    "central_symmetry": "конфигурация имеет центр симметрии",
    "four_parallelogram": "какие-то 4 точки образуют параллелограмм",
    "four_concyclic": "какие-то 4 точки лежат на одной окружности",
}


ATOM_HINT_CATEGORIES = {
    "three_collinear": "arrangement",
    "convex_position": "arrangement",
    "distances_distinct": "arrangement",
    "central_symmetry": "symmetry",
    "four_parallelogram": "arrangement",
    "four_concyclic": "arrangement",
}


def point_key(config: PointConfig) -> Hashable:
    return config


def serialize_points(config: PointConfig) -> list[list[int]]:
    return [[x, y] for x, y in config]


def _canonical(points: set[tuple[int, int]]) -> PointConfig:
    return tuple(sorted(points))


def _random_config(rng: random.Random, *, count: int | None = None) -> PointConfig:
    size = count if count is not None else rng.randint(MIN_POINTS, MAX_POINTS)
    cells = rng.sample(
        [(x, y) for x in range(GRID_SIZE) for y in range(GRID_SIZE)],
        size,
    )
    return _canonical(set(cells))


def _symmetric_config(rng: random.Random) -> PointConfig | None:
    count = rng.randint(MIN_POINTS, MAX_POINTS)
    doubled_center = (rng.randint(6, 16), rng.randint(6, 16))
    if count % 2 == 1:
        if doubled_center[0] % 2 or doubled_center[1] % 2:
            doubled_center = (
                doubled_center[0] - doubled_center[0] % 2,
                doubled_center[1] - doubled_center[1] % 2,
            )
        center = (doubled_center[0] // 2, doubled_center[1] // 2)
        points = {center}
    else:
        points = set()
    for _ in range(80):
        if len(points) >= count:
            break
        x = rng.randint(0, GRID_SIZE - 1)
        y = rng.randint(0, GRID_SIZE - 1)
        mirror = (doubled_center[0] - x, doubled_center[1] - y)
        if (x, y) == mirror:
            continue
        if not (0 <= mirror[0] < GRID_SIZE and 0 <= mirror[1] < GRID_SIZE):
            continue
        if (x, y) in points or mirror in points:
            continue
        if len(points) + 2 > count:
            continue
        points.add((x, y))
        points.add(mirror)
    if len(points) != count:
        return None
    return _canonical(points)


def _lattice_circles() -> tuple[tuple[tuple[int, int], ...], ...]:
    circles: list[tuple[tuple[int, int], ...]] = []
    for center_x in range(2, GRID_SIZE - 2):
        for center_y in range(2, GRID_SIZE - 2):
            by_radius: dict[int, list[tuple[int, int]]] = {}
            for x in range(GRID_SIZE):
                for y in range(GRID_SIZE):
                    squared = (x - center_x) ** 2 + (y - center_y) ** 2
                    if squared == 0:
                        continue
                    by_radius.setdefault(squared, []).append((x, y))
            for points in by_radius.values():
                if len(points) >= 4:
                    circles.append(tuple(sorted(points)))
    return tuple(circles)


_CIRCLES = _lattice_circles()


def _concyclic_config(rng: random.Random) -> PointConfig | None:
    count = rng.randint(MIN_POINTS, MAX_POINTS)
    circle = rng.choice(_CIRCLES)
    on_circle = rng.sample(list(circle), 4)
    points = set(on_circle)
    for _ in range(60):
        if len(points) >= count:
            break
        candidate = (
            rng.randint(0, GRID_SIZE - 1),
            rng.randint(0, GRID_SIZE - 1),
        )
        if candidate in points:
            continue
        points.add(candidate)
    if len(points) != count:
        return None
    return _canonical(points)


def _convex_config(rng: random.Random) -> PointConfig | None:
    count = rng.randint(MIN_POINTS, 7)
    for _ in range(40):
        config = _random_config(rng, count=count)
        if _convex_position(config):
            return config
    return None


def _no_collinear_config(rng: random.Random) -> PointConfig | None:
    count = rng.randint(MIN_POINTS, 6)
    for _ in range(40):
        config = _random_config(rng, count=count)
        if not _three_collinear(config):
            return config
    return None


def _distinct_distances_config(rng: random.Random) -> PointConfig | None:
    count = rng.randint(MIN_POINTS, 6)
    for _ in range(60):
        config = _random_config(rng, count=count)
        if _distances_distinct(config):
            return config
    return None


_BUILD_LOG: dict[str, Any] = {}


def build_point_population() -> tuple[PointConfig, ...]:
    """Deterministic population with targeted property mixing."""

    rng = random.Random(_POPULATION_SEED)
    phases: list[tuple[str, int, Any]] = [
        ("random", 440, lambda: _random_config(rng)),
        ("symmetric", 170, lambda: _symmetric_config(rng)),
        ("concyclic", 170, lambda: _concyclic_config(rng)),
        ("convex", 170, lambda: _convex_config(rng)),
        ("no_collinear", 110, lambda: _no_collinear_config(rng)),
        ("distinct_distances", 140, lambda: _distinct_distances_config(rng)),
    ]
    configs: list[PointConfig] = []
    seen: set[PointConfig] = set()
    rejects: dict[str, int] = {}
    for phase_name, quota, sampler in phases:
        produced = 0
        attempts = 0
        while produced < quota and attempts < quota * 60:
            attempts += 1
            config = sampler()
            if config is None or config in seen:
                rejects[phase_name] = rejects.get(phase_name, 0) + 1
                continue
            seen.add(config)
            configs.append(config)
            produced += 1
        rejects.setdefault(phase_name, 0)
    while len(configs) < POPULATION_SIZE:
        config = _random_config(rng)
        if config in seen:
            rejects["fill"] = rejects.get("fill", 0) + 1
            continue
        seen.add(config)
        configs.append(config)
    _BUILD_LOG["sampler_rejects"] = rejects
    _BUILD_LOG["atom_base_rates"] = {
        atom.key: (
            sum(atom.evaluate(config) for config in configs)
            / len(configs)
        )
        for atom in POINT_ATOMS
    }
    return tuple(configs[:POPULATION_SIZE])


def point_mutations(config: PointConfig) -> tuple[PointConfig, ...]:
    """Relocate one point within its 3×3 neighbourhood, in stable order."""

    mutations: list[PointConfig] = []
    occupied = set(config)
    for index, (x, y) in enumerate(config):
        for delta_x in range(-1, 2):
            for delta_y in range(-1, 2):
                if delta_x == 0 and delta_y == 0:
                    continue
                candidate = (x + delta_x, y + delta_y)
                if not (
                    0 <= candidate[0] < GRID_SIZE
                    and 0 <= candidate[1] < GRID_SIZE
                ):
                    continue
                if candidate in occupied:
                    continue
                moved = set(config)
                moved.discard((x, y))
                moved.add(candidate)
                mutations.append(_canonical(moved))
    unique: dict[PointConfig, PointConfig] = {}
    for mutation in mutations:
        unique.setdefault(mutation, mutation)
    return tuple(unique.values())


class PointUniverse:
    universe_version = UNIVERSE_VERSION
    dsl_version = DSL_VERSION

    def population(self) -> tuple[PointConfig, ...]:
        return build_point_population()

    def atoms(self) -> tuple[Atom, ...]:
        return POINT_ATOMS

    def enumerate_rules(self) -> tuple[Rule, ...]:
        return enumerate_rules(POINT_ATOMS)

    def mutations(self, obj: PointConfig) -> tuple[PointConfig, ...]:
        return point_mutations(obj)

    def object_key(self, obj: PointConfig) -> Hashable:
        return point_key(obj)

    def render_payload(self, obj: PointConfig) -> dict[str, Any]:
        return {"points": serialize_points(obj)}


_UNIVERSE = PointUniverse()

_POINT_LABELS = "ABCDEFGH"


def _scene(cards: list[tuple[str, PointConfig]]) -> dict[str, Any]:
    points: list[dict[str, Any]] = []
    for card_id, config in cards:
        for index, (x, y) in enumerate(config):
            points.append(
                {
                    "id": f"{card_id}:{_POINT_LABELS[index]}",
                    "group": card_id,
                    "x": x,
                    "y": y,
                    "label": _POINT_LABELS[index],
                    "color": "cyan",
                }
            )
    return {
        "bounds": {
            "min_x": 0,
            "max_x": GRID_SIZE - 1,
            "min_y": 0,
            "max_y": GRID_SIZE - 1,
        },
        "points": points,
        "edges": [],
    }


def generate_point_zendo_task(
    *,
    seed: int,
    difficulty: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if isinstance(difficulty, bool) or not 1 <= difficulty <= 5:
        raise ValueError("point_zendo difficulty must be from 1 to 5")
    rng = random.Random(seed)
    space = get_universe_space(_UNIVERSE)
    material = select_material(
        rng=rng,
        difficulty=difficulty,
        pool=space.population,
        pool_masks=space.object_masks,
        rules=space.rules,
        atoms=space.atoms,
        all_rules_mask=space.all_rules_mask,
        difficulty_rule_indices=space.indices_for_difficulty(difficulty),
        mutations=point_mutations,
        object_key=point_key,
    )

    example_cards = [
        (f"E{index:02d}", config)
        for index, config in enumerate(material.examples, start=1)
    ]
    probe_cards = [
        (f"P{index:02d}", config)
        for index, config in enumerate(material.probes, start=1)
    ]
    target_cards = [
        (f"T{index:02d}", config)
        for index, config in enumerate(material.targets, start=1)
    ]
    all_cards = [*example_cards, *probe_cards, *target_cards]
    public = {
        "kind": PUBLIC_KIND,
        "family": FAMILY_KEY,
        "variant": "classify_hidden_point_rule",
        "prompt": (
            "Рассмотрите предложенные наборы точек. Было загадано некоторое "
            "утверждение: одни наборы ему соответствуют, другие — нет. "
            "Предположите, что это за утверждение, и классифицируйте восемь "
            "целевых наборов по порядку. Перед ответом можно опробовать "
            "несколько наборов — доступно 5 проб."
        ),
        "scene": _scene(all_cards),
        "content": {
            "examples": [
                {
                    "card_id": card_id,
                    "classification": "positive" if label else "negative",
                }
                for (card_id, _config), label in zip(
                    example_cards,
                    material.example_labels,
                    strict=True,
                )
            ],
            "probe_cards": [
                {"card_id": card_id, "used": False}
                for card_id, _config in probe_cards
            ],
            "targets": [
                {"card_id": card_id, "position": index}
                for index, (card_id, _config) in enumerate(
                    target_cards,
                    start=1,
                )
            ],
            "probe_budget": PROBE_BUDGET,
            "probes_remaining": PROBE_BUDGET,
            "probe_observations": [],
        },
        "interaction": {
            "mode": "probe_then_answer",
            "commands": ["/test <card_id>", "/answer <да/нет ...>"],
        },
        "response_hint": (
            "Ответьте восемью значениями в порядке целей: "
            "/answer да нет да нет да нет да нет."
        ),
        "dsl_version": DSL_VERSION,
    }
    private = {
        "family": FAMILY_KEY,
        "generator_version": GENERATOR_VERSION,
        "difficulty": difficulty,
        "dsl_version": DSL_VERSION,
        "universe_version": UNIVERSE_VERSION,
        "rule_index": material.rule_index,
        "version_space": material.version_space,
        "version_space_after_examples": material.version_space,
        "probe_cards": {
            card_id: serialize_points(config)
            for card_id, config in probe_cards
        },
        "probe_truth_masks": {
            card_id: truth_mask
            for (card_id, _config), truth_mask in zip(
                probe_cards,
                material.probe_masks,
                strict=True,
            )
        },
        "used_probe_card_ids": [],
        "probe_budget": PROBE_BUDGET,
        "probes_remaining": PROBE_BUDGET,
        "target_card_ids": [
            card_id for card_id, _config in target_cards
        ],
        "target_answers": material.target_answers,
        "hint_category": rule_hint_category(
            space.rules[material.rule_index],
            ATOM_HINT_CATEGORIES,
        ),
    }
    return public, private


def transition_point_zendo_hint(
    *,
    public_state: dict[str, Any],
    private_state: dict[str, Any],
):
    return transition_zendo_hint(
        public_state=public_state,
        private_state=private_state,
        category=str(private_state["hint_category"]),
    )


def transition_point_zendo_probe(
    *,
    card_id: str,
    public_state: dict[str, Any],
    private_state: dict[str, Any],
):
    space = get_universe_space(_UNIVERSE)
    return transition_zendo_probe(
        card_id=card_id,
        public_state=public_state,
        private_state=private_state,
        all_rules_mask=space.all_rules_mask,
    )


def evaluate_point_zendo_answer(
    *,
    answer: str,
    private_state: dict[str, Any],
) -> dict[str, Any]:
    return evaluate_zendo_answer(answer=answer, private_state=private_state)


def sampler_build_log() -> dict[str, Any]:
    return dict(_BUILD_LOG)


__all__ = [
    "DSL_VERSION",
    "FAMILY_KEY",
    "GENERATOR_VERSION",
    "POINT_ATOMS",
    "PUBLIC_KIND",
    "PointUniverse",
    "UNIVERSE_VERSION",
    "build_point_population",
    "evaluate_point_zendo_answer",
    "generate_point_zendo_task",
    "point_mutations",
    "sampler_build_log",
    "transition_point_zendo_hint",
    "transition_point_zendo_probe",
]
