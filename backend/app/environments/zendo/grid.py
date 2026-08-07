"""grid_zendo: hidden rules over filled-cell patterns on a 5×5 grid.

"""

from __future__ import annotations

import random
from collections import deque
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Hashable

from ..core.rule_dsl import (
    Atom,
    Rule,
    actual_information_gain,
    enumerate_rules,
    filter_version_space,
    information_gain,
    rule_truth_mask,
)
from ..core.zendo_engine import (
    PROBE_BUDGET,
    evaluate_zendo_answer,
    get_universe_space,
    rule_hint_category,
    select_material,
    transition_zendo_hint,
)

FAMILY_KEY = "grid_zendo"
GENERATOR_VERSION = "grid-zendo-v1"
PUBLIC_KIND = "grid_zendo"
UNIVERSE_VERSION = "grid-universe-v1"
DSL_VERSION = "grid-dsl-v1"

GRID_SIZE = 5
CELL_COUNT = GRID_SIZE * GRID_SIZE
MIN_FILLED = 4
MAX_FILLED = 13
POPULATION_SIZE = 640
_POPULATION_SEED = 0x6B1D_2026

GridPattern = int


def _cells(pattern: GridPattern) -> list[tuple[int, int]]:
    return [
        (index // GRID_SIZE, index % GRID_SIZE)
        for index in range(CELL_COUNT)
        if pattern >> index & 1
    ]


def _from_cells(cells: Any) -> GridPattern:
    pattern = 0
    for row, column in cells:
        pattern |= 1 << (row * GRID_SIZE + column)
    return pattern


def _transform_pattern(
    pattern: GridPattern,
    transform: Any,
) -> GridPattern:
    return _from_cells(transform(row, column) for row, column in _cells(pattern))


def _symmetry_atom(name: str, transform: Any) -> Any:
    def predicate(pattern: GridPattern) -> bool:
        return _transform_pattern(pattern, transform) == pattern

    predicate.__name__ = f"_sym_{name}"
    return predicate


_ROTATE_90 = lambda row, column: (column, GRID_SIZE - 1 - row)
_ROTATE_180 = lambda row, column: (
    GRID_SIZE - 1 - row,
    GRID_SIZE - 1 - column,
)
_ROTATE_270 = lambda row, column: (GRID_SIZE - 1 - column, row)
_REFLECT_H = lambda row, column: (GRID_SIZE - 1 - row, column)
_REFLECT_V = lambda row, column: (row, GRID_SIZE - 1 - column)
_REFLECT_MAIN = lambda row, column: (column, row)
_REFLECT_ANTI = lambda row, column: (
    GRID_SIZE - 1 - column,
    GRID_SIZE - 1 - row,
)

D4_TRANSFORMS = {
    "rotate_90": _ROTATE_90,
    "rotate_180": _ROTATE_180,
    "rotate_270": _ROTATE_270,
    "reflect_h": _REFLECT_H,
    "reflect_v": _REFLECT_V,
    "reflect_main": _REFLECT_MAIN,
    "reflect_anti": _REFLECT_ANTI,
}


def _cell_count_even(pattern: GridPattern) -> bool:
    return pattern.bit_count() % 2 == 0


def _neighbors(index: int) -> list[int]:
    row, column = index // GRID_SIZE, index % GRID_SIZE
    result = []
    if row > 0:
        result.append(index - GRID_SIZE)
    if row < GRID_SIZE - 1:
        result.append(index + GRID_SIZE)
    if column > 0:
        result.append(index - 1)
    if column < GRID_SIZE - 1:
        result.append(index + 1)
    return result


def _component_count(pattern: GridPattern) -> int:
    remaining = pattern
    components = 0
    while remaining:
        components += 1
        start = (remaining & -remaining).bit_length() - 1
        queue: deque[int] = deque([start])
        seen = 1 << start
        while queue:
            current = queue.popleft()
            for neighbor in _neighbors(current):
                bit = 1 << neighbor
                if remaining & bit and not seen & bit:
                    seen |= bit
                    queue.append(neighbor)
        remaining &= ~seen
    return components


def _connected(pattern: GridPattern) -> bool:
    return _component_count(pattern) == 1


def _component_count_even(pattern: GridPattern) -> bool:
    return _component_count(pattern) % 2 == 0


def _all_rows_even(pattern: GridPattern) -> bool:
    for row in range(GRID_SIZE):
        row_bits = (pattern >> (row * GRID_SIZE)) & ((1 << GRID_SIZE) - 1)
        if row_bits.bit_count() % 2:
            return False
    return True


def _all_columns_even(pattern: GridPattern) -> bool:
    for column in range(GRID_SIZE):
        count = sum(
            pattern >> (row * GRID_SIZE + column) & 1
            for row in range(GRID_SIZE)
        )
        if count % 2:
            return False
    return True


def _domino_tileable(pattern: GridPattern) -> bool:
    cells = [index for index in range(CELL_COUNT) if pattern >> index & 1]
    if len(cells) % 2:
        return False
    if not cells:
        return True
    dark = [
        index
        for index in cells
        if (index // GRID_SIZE + index % GRID_SIZE) % 2 == 0
    ]
    light = {
        index
        for index in cells
        if (index // GRID_SIZE + index % GRID_SIZE) % 2 == 1
    }
    if len(dark) != len(light):
        return False
    match_of: dict[int, int] = {}

    def augment(cell: int, visited: set[int]) -> bool:
        for neighbor in _neighbors(cell):
            if neighbor not in light or neighbor in visited:
                continue
            visited.add(neighbor)
            if neighbor not in match_of or augment(match_of[neighbor], visited):
                match_of[neighbor] = cell
                return True
        return False

    return all(augment(cell, set()) for cell in dark)


def _make_symmetry_predicate(transform):
    def predicate(pattern: GridPattern) -> bool:
        return _transform_pattern(pattern, transform) == pattern

    return predicate


GRID_ATOMS: tuple[Atom, ...] = (
    Atom("cell_count_even", 3, _cell_count_even),
    Atom("connected", 3, _connected),
    Atom("sym_rotate_180", 3, _make_symmetry_predicate(_ROTATE_180)),
    Atom("sym_reflect_h", 3, _make_symmetry_predicate(_REFLECT_H)),
    Atom("sym_reflect_v", 3, _make_symmetry_predicate(_REFLECT_V)),
    Atom("sym_rotate_90", 4, _make_symmetry_predicate(_ROTATE_90)),
    Atom("sym_rotate_270", 4, _make_symmetry_predicate(_ROTATE_270)),
    Atom("sym_reflect_main", 4, _make_symmetry_predicate(_REFLECT_MAIN)),
    Atom("sym_reflect_anti", 4, _make_symmetry_predicate(_REFLECT_ANTI)),
    Atom("all_rows_even", 4, _all_rows_even),
    Atom("all_columns_even", 4, _all_columns_even),
    Atom("component_count_even", 4, _component_count_even),
    Atom("domino_tileable", 4, _domino_tileable),
)


ATOM_DESCRIPTIONS = {
    "cell_count_even": "число закрашенных клеток чётно",
    "connected": "закрашенная область связна",
    "sym_rotate_90": "узор переходит в себя при повороте на 90°",
    "sym_rotate_180": "узор переходит в себя при повороте на 180°",
    "sym_rotate_270": "узор переходит в себя при повороте на 270°",
    "sym_reflect_h": "узор симметричен относительно горизонтальной оси",
    "sym_reflect_v": "узор симметричен относительно вертикальной оси",
    "sym_reflect_main": "узор симметричен относительно главной диагонали",
    "sym_reflect_anti": "узор симметричен относительно побочной диагонали",
    "all_rows_even": "в каждой строке чётное число закрашенных клеток",
    "all_columns_even": "в каждом столбце чётное число закрашенных клеток",
    "component_count_even": "число компонент закрашенной области чётно",
    "domino_tileable": "закрашенная область замощается доминошками",
}


ATOM_HINT_CATEGORIES = {
    "cell_count_even": "count",
    "all_rows_even": "count",
    "all_columns_even": "count",
    "sym_rotate_90": "symmetry",
    "sym_rotate_180": "symmetry",
    "sym_rotate_270": "symmetry",
    "sym_reflect_h": "symmetry",
    "sym_reflect_v": "symmetry",
    "sym_reflect_main": "symmetry",
    "sym_reflect_anti": "symmetry",
    "connected": "connectivity",
    "component_count_even": "connectivity",
    "domino_tileable": "connectivity",
}


def grid_key(pattern: GridPattern) -> Hashable:
    return pattern


def serialize_pattern(pattern: GridPattern) -> list[str]:
    return [
        "".join(
            "1" if pattern >> (row * GRID_SIZE + column) & 1 else "0"
            for column in range(GRID_SIZE)
        )
        for row in range(GRID_SIZE)
    ]


def parse_pattern(value: str) -> GridPattern | None:
    digits = [char for char in value if char in "01"]
    if len(digits) != CELL_COUNT:
        return None
    pattern = 0
    for index, digit in enumerate(digits):
        if digit == "1":
            pattern |= 1 << index
    return pattern


def _random_pattern(rng: random.Random, *, count: int | None = None) -> GridPattern:
    filled = count if count is not None else rng.randint(MIN_FILLED, MAX_FILLED)
    cells = rng.sample(range(CELL_COUNT), filled)
    pattern = 0
    for index in cells:
        pattern |= 1 << index
    return pattern


def _symmetric_pattern(
    rng: random.Random,
    transform: Any,
) -> GridPattern | None:
    pattern = 0
    for _ in range(rng.randint(2, 6)):
        index = rng.randrange(CELL_COUNT)
        orbit = 0
        row, column = index // GRID_SIZE, index % GRID_SIZE
        for _ in range(4):
            orbit |= 1 << (row * GRID_SIZE + column)
            row, column = transform(row, column)
        pattern |= orbit
    count = pattern.bit_count()
    if not MIN_FILLED <= count <= MAX_FILLED:
        return None
    return pattern


def _row_even_pattern(rng: random.Random) -> GridPattern | None:
    pattern = 0
    for row in range(GRID_SIZE):
        size = rng.choice((0, 2, 2, 4))
        for column in rng.sample(range(GRID_SIZE), size):
            pattern |= 1 << (row * GRID_SIZE + column)
    count = pattern.bit_count()
    if not MIN_FILLED <= count <= MAX_FILLED:
        return None
    return pattern


def _column_even_pattern(rng: random.Random) -> GridPattern | None:
    pattern = _row_even_pattern(rng)
    if pattern is None:
        return None
    return _transform_pattern(pattern, _REFLECT_MAIN)


def _connected_pattern(rng: random.Random) -> GridPattern | None:
    filled = rng.randint(MIN_FILLED, MAX_FILLED)
    start = rng.randrange(CELL_COUNT)
    region = {start}
    frontier = set(_neighbors(start))
    while len(region) < filled and frontier:
        cell = rng.choice(sorted(frontier))
        region.add(cell)
        frontier.discard(cell)
        frontier.update(
            neighbor
            for neighbor in _neighbors(cell)
            if neighbor not in region
        )
    if len(region) != filled:
        return None
    pattern = 0
    for index in region:
        pattern |= 1 << index
    return pattern


def _tileable_pattern(rng: random.Random) -> GridPattern | None:
    dominoes = rng.randint(MIN_FILLED // 2, MAX_FILLED // 2)
    pattern = 0
    for _ in range(dominoes * 4):
        if pattern.bit_count() >= dominoes * 2:
            break
        index = rng.randrange(CELL_COUNT)
        neighbors = _neighbors(index)
        partner = rng.choice(neighbors)
        pair = (1 << index) | (1 << partner)
        if pattern & pair:
            continue
        pattern |= pair
    count = pattern.bit_count()
    if count < MIN_FILLED or count > MAX_FILLED or count % 2:
        return None
    return pattern


_BUILD_LOG: dict[str, Any] = {}


def build_grid_population() -> tuple[GridPattern, ...]:
    rng = random.Random(_POPULATION_SEED)
    phases: list[tuple[str, int, Any]] = [
        ("c4", 80, lambda: _symmetric_pattern(rng, _ROTATE_90)),
        ("rotate_180", 55, lambda: _symmetric_pattern(rng, _ROTATE_180)),
        ("reflect_h", 70, lambda: _symmetric_pattern(rng, _REFLECT_H)),
        ("reflect_v", 70, lambda: _symmetric_pattern(rng, _REFLECT_V)),
        ("reflect_main", 70, lambda: _symmetric_pattern(rng, _REFLECT_MAIN)),
        ("reflect_anti", 70, lambda: _symmetric_pattern(rng, _REFLECT_ANTI)),
        ("row_even", 30, lambda: _row_even_pattern(rng)),
        ("column_even", 30, lambda: _column_even_pattern(rng)),
        ("connected", 60, lambda: _connected_pattern(rng)),
        ("tileable", 45, lambda: _tileable_pattern(rng)),
    ]
    patterns: list[GridPattern] = []
    seen: set[GridPattern] = set()
    rejects: dict[str, int] = {}
    for phase_name, quota, sampler in phases:
        produced = 0
        attempts = 0
        while produced < quota and attempts < quota * 60:
            attempts += 1
            pattern = sampler()
            if pattern is None or pattern in seen:
                rejects[phase_name] = rejects.get(phase_name, 0) + 1
                continue
            seen.add(pattern)
            patterns.append(pattern)
            produced += 1
        rejects.setdefault(phase_name, 0)
    while len(patterns) < POPULATION_SIZE:
        pattern = _random_pattern(rng)
        if pattern in seen:
            rejects["fill"] = rejects.get("fill", 0) + 1
            continue
        seen.add(pattern)
        patterns.append(pattern)
    _BUILD_LOG["sampler_rejects"] = rejects
    _BUILD_LOG["atom_base_rates"] = {
        atom.key: (
            sum(atom.evaluate(pattern) for pattern in patterns)
            / len(patterns)
        )
        for atom in GRID_ATOMS
    }
    return tuple(patterns[:POPULATION_SIZE])


def grid_mutations(pattern: GridPattern) -> tuple[GridPattern, ...]:
    """Toggle a single cell, in stable order."""

    return tuple(
        pattern ^ (1 << index)
        for index in range(CELL_COUNT)
    )


class GridUniverse:
    universe_version = UNIVERSE_VERSION
    dsl_version = DSL_VERSION

    def population(self) -> tuple[GridPattern, ...]:
        return build_grid_population()

    def atoms(self) -> tuple[Atom, ...]:
        return GRID_ATOMS

    def enumerate_rules(self) -> tuple[Rule, ...]:
        return enumerate_rules(GRID_ATOMS)

    def mutations(self, obj: GridPattern) -> tuple[GridPattern, ...]:
        return grid_mutations(obj)

    def object_key(self, obj: GridPattern) -> Hashable:
        return grid_key(obj)

    def render_payload(self, obj: GridPattern) -> dict[str, Any]:
        return {"rows": serialize_pattern(obj)}


_UNIVERSE = GridUniverse()


@dataclass(frozen=True)
class GridProbeTransition:
    public_state: dict[str, Any]
    private_state: dict[str, Any]
    accepted: bool
    reason: str
    message: str
    normalized_pattern: str
    telemetry: dict[str, Any] | None


def generate_grid_zendo_task(
    *,
    seed: int,
    difficulty: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if isinstance(difficulty, bool) or not 1 <= difficulty <= 5:
        raise ValueError("grid_zendo difficulty must be from 1 to 5")
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
        mutations=grid_mutations,
        object_key=grid_key,
    )

    example_cards = [
        (f"E{index:02d}", pattern)
        for index, pattern in enumerate(material.examples, start=1)
    ]
    target_cards = [
        (f"T{index:02d}", pattern)
        for index, pattern in enumerate(material.targets, start=1)
    ]
    public = {
        "kind": PUBLIC_KIND,
        "family": FAMILY_KEY,
        "variant": "classify_hidden_grid_rule",
        "prompt": (
            '''
На листочках нарисованы узоры по некоторым правилам. Твоя задача - восстановить эти правила и классифицировать узоры. Для тестирования гипотез можно нарисовать свой узор.
'''
            # "На листочках нарисованы узоры по некоторым правилам. Для "
            # "некоторых узоров это свойство выполняется, для некоторых — нет. "
            # "Твоя задача — раскрыть это свойство и классифицировать восемь "
            # "целевых узоров по порядку. Доступно 5 подсказок — собственные "
            # "узоры можно рисовать и проверять."
        ),
        "cards": {
            card_id: serialize_pattern(pattern)
            for card_id, pattern in [*example_cards, *target_cards]
        },
        "grid_size": GRID_SIZE,
        "content": {
            "examples": [
                {
                    "card_id": card_id,
                    "classification": "positive" if label else "negative",
                }
                for (card_id, _pattern), label in zip(
                    example_cards,
                    material.example_labels,
                    strict=True,
                )
            ],
            "targets": [
                {"card_id": card_id, "position": index}
                for index, (card_id, _pattern) in enumerate(
                    target_cards,
                    start=1,
                )
            ],
            "probe_budget": PROBE_BUDGET,
            "probes_remaining": PROBE_BUDGET,
            "probe_observations": [],
        },
        "interaction": {
            "mode": "draw_probe_then_answer",
            "commands": ["/test <узор из 25 нулей и единиц>", "/answer <да/нет ...>"],
        },
        "response_hint": (
            "Ответьте восемью значениями в порядке целей "
            "(1 — подходит, 0 — нет): /answer 1 0 1 0 1 0 1 0."
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
        "used_probe_patterns": [],
        "probe_budget": PROBE_BUDGET,
        "probes_remaining": PROBE_BUDGET,
        "target_card_ids": [
            card_id for card_id, _pattern in target_cards
        ],
        "target_answers": material.target_answers,
        "hint_category": rule_hint_category(
            space.rules[material.rule_index],
            ATOM_HINT_CATEGORIES,
        ),
    }
    return public, private


def transition_grid_zendo_hint(
    *,
    public_state: dict[str, Any],
    private_state: dict[str, Any],
):
    return transition_zendo_hint(
        public_state=public_state,
        private_state=private_state,
        category=str(private_state["hint_category"]),
    )


def transition_grid_zendo_probe(
    *,
    pattern: str,
    public_state: dict[str, Any],
    private_state: dict[str, Any],
) -> GridProbeTransition:
    """Free-form drawn probe with live ΔH telemetry."""

    next_public = deepcopy(public_state)
    next_private = deepcopy(private_state)
    parsed = parse_pattern(pattern)
    if parsed is None:
        return GridProbeTransition(
            next_public,
            next_private,
            False,
            "invalid_pattern",
            "Узор должен содержать ровно 25 нулей и единиц (5 строк по 5).",
            pattern.strip(),
            None,
        )
    normalized = "".join(serialize_pattern(parsed))
    used = [str(value) for value in next_private.get("used_probe_patterns", [])]
    if normalized in used:
        return GridProbeTransition(
            next_public,
            next_private,
            False,
            "probe_already_used",
            "Этот узор уже был проверен.",
            normalized,
            None,
        )
    if int(next_private.get("probes_remaining") or 0) <= 0:
        return GridProbeTransition(
            next_public,
            next_private,
            False,
            "probe_budget_exhausted",
            "Лимит проверок исчерпан.",
            normalized,
            None,
        )

    space = get_universe_space(_UNIVERSE)
    rule_index = int(next_private["rule_index"])
    before = int(next_private["version_space"])
    pattern_rule_mask = rule_truth_mask(parsed, space.rules, atoms=space.atoms)
    outcome = bool(pattern_rule_mask >> rule_index & 1)
    after = filter_version_space(
        before,
        pattern_rule_mask,
        outcome,
        all_rules_mask=space.all_rules_mask,
    )
    best_gain = max(
        (
            information_gain(before, object_mask)
            for object_mask in space.object_masks
        ),
        default=0.0,
    )
    telemetry = {
        "vs_size_before": before.bit_count(),
        "vs_size_after": after.bit_count(),
        "gain_bits_actual": actual_information_gain(before, after),
        "gain_bits_best": best_gain,
    }
    next_private["version_space"] = after
    next_private["used_probe_patterns"] = [*used, normalized]
    next_private["probes_remaining"] = int(next_private["probes_remaining"]) - 1
    content = next_public["content"]
    content["probes_remaining"] = int(content["probes_remaining"]) - 1
    content["probe_observations"].append(
        {
            "pattern": serialize_pattern(parsed),
            "classification": "positive" if outcome else "negative",
        }
    )
    return GridProbeTransition(
        public_state=next_public,
        private_state=next_private,
        accepted=True,
        reason="accepted",
        message=(
            f"Узор {'подходит' if outcome else 'не подходит'} "
            "под скрытое правило."
        ),
        normalized_pattern=normalized,
        telemetry=telemetry,
    )


def evaluate_grid_zendo_answer(
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
    "GRID_ATOMS",
    "GRID_SIZE",
    "GridProbeTransition",
    "GridUniverse",
    "PUBLIC_KIND",
    "UNIVERSE_VERSION",
    "build_grid_population",
    "evaluate_grid_zendo_answer",
    "generate_grid_zendo_task",
    "grid_mutations",
    "parse_pattern",
    "sampler_build_log",
    "serialize_pattern",
    "transition_grid_zendo_hint",
    "transition_grid_zendo_probe",
]
