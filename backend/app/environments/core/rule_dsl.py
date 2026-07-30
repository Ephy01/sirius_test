"""A small deterministic rule DSL for graph-classification tasks.

Two different bit sets are deliberately used throughout this module:

* a compiled rule's ``truth_mask`` has one bit per graph in the fixed universe;
* a ``version_space`` has one bit per rule in the distilled rule catalogue.

Keeping both representations as Python integers makes filtering a version
space a handful of bit operations, while the immutable :class:`Rule` objects
remain useful for generation and tests.
"""

from __future__ import annotations

import itertools
import math
from collections import deque
from dataclasses import dataclass
from typing import Callable, Iterable, Mapping, Sequence

from ..geometry_world.atlas import MiniGraph

MIN_BASE_RATE = 0.12
MAX_BASE_RATE = 0.88


def _adjacency(graph: MiniGraph) -> tuple[frozenset[int], ...]:
    neighbors = [set() for _ in graph.points]
    for first, second in graph.edges:
        if 0 <= first < len(neighbors) and 0 <= second < len(neighbors):
            neighbors[first].add(second)
            neighbors[second].add(first)
    return tuple(frozenset(items) for items in neighbors)


def _vertex_count_even(graph: MiniGraph) -> bool:
    return len(graph.points) % 2 == 0


def _edge_count_even(graph: MiniGraph) -> bool:
    return len(graph.edges) % 2 == 0


def _is_connected(graph: MiniGraph) -> bool:
    if not graph.points:
        return False
    neighbors = _adjacency(graph)
    reached = {0}
    queue: deque[int] = deque([0])
    while queue:
        current = queue.popleft()
        for neighbor in neighbors[current]:
            if neighbor not in reached:
                reached.add(neighbor)
                queue.append(neighbor)
    return len(reached) == len(graph.points)


def _has_triangle(graph: MiniGraph) -> bool:
    edge_set = set(graph.edges)
    return any(
        {
            (min(a, b), max(a, b)),
            (min(a, c), max(a, c)),
            (min(b, c), max(b, c)),
        }
        <= edge_set
        for a, b, c in itertools.combinations(range(len(graph.points)), 3)
    )


def _has_cycle(graph: MiniGraph) -> bool:
    neighbors = _adjacency(graph)
    seen: set[int] = set()

    def visit(current: int, parent: int) -> bool:
        seen.add(current)
        for neighbor in neighbors[current]:
            if neighbor == parent:
                continue
            if neighbor in seen or visit(neighbor, current):
                return True
        return False

    return any(
        visit(vertex, -1)
        for vertex in range(len(graph.points))
        if vertex not in seen
    )


def _has_isolated_vertex(graph: MiniGraph) -> bool:
    return any(not neighbors for neighbors in _adjacency(graph))


def _has_leaf(graph: MiniGraph) -> bool:
    return any(len(neighbors) == 1 for neighbors in _adjacency(graph))


def _max_degree_at_least_three(graph: MiniGraph) -> bool:
    return any(len(neighbors) >= 3 for neighbors in _adjacency(graph))


def _all_degrees_even(graph: MiniGraph) -> bool:
    return all(len(neighbors) % 2 == 0 for neighbors in _adjacency(graph))


def _exactly_two_odd_degrees(graph: MiniGraph) -> bool:
    return (
        sum(len(neighbors) % 2 == 1 for neighbors in _adjacency(graph))
        == 2
    )


def _is_bipartite(graph: MiniGraph) -> bool:
    neighbors = _adjacency(graph)
    sides: dict[int, bool] = {}
    for start in range(len(graph.points)):
        if start in sides:
            continue
        sides[start] = False
        queue: deque[int] = deque([start])
        while queue:
            current = queue.popleft()
            for neighbor in neighbors[current]:
                if neighbor not in sides:
                    sides[neighbor] = not sides[current]
                    queue.append(neighbor)
                elif sides[neighbor] == sides[current]:
                    return False
    return True


def _orientation(
    first: tuple[int, int],
    second: tuple[int, int],
    third: tuple[int, int],
) -> int:
    return (
        (second[0] - first[0]) * (third[1] - first[1])
        - (second[1] - first[1]) * (third[0] - first[0])
    )


def _properly_cross(
    first_start: tuple[int, int],
    first_end: tuple[int, int],
    second_start: tuple[int, int],
    second_end: tuple[int, int],
) -> bool:
    first_side = _orientation(first_start, first_end, second_start)
    second_side = _orientation(first_start, first_end, second_end)
    third_side = _orientation(second_start, second_end, first_start)
    fourth_side = _orientation(second_start, second_end, first_end)
    return (
        first_side != 0
        and second_side != 0
        and third_side != 0
        and fourth_side != 0
        and (first_side > 0) != (second_side > 0)
        and (third_side > 0) != (fourth_side > 0)
    )


def _has_crossing(graph: MiniGraph) -> bool:
    for first_edge, second_edge in itertools.combinations(graph.edges, 2):
        if set(first_edge) & set(second_edge):
            continue
        if _properly_cross(
            graph.points[first_edge[0]],
            graph.points[first_edge[1]],
            graph.points[second_edge[0]],
            graph.points[second_edge[1]],
        ):
            return True
    return False


def _edges_at_least_vertices(graph: MiniGraph) -> bool:
    return len(graph.edges) >= len(graph.points)


def _density_at_least_half(graph: MiniGraph) -> bool:
    vertex_count = len(graph.points)
    possible_edges = vertex_count * (vertex_count - 1) // 2
    return possible_edges > 0 and len(graph.edges) * 2 >= possible_edges


@dataclass(frozen=True, slots=True)
class Atom:
    """A named primitive predicate with a fixed description length."""

    key: str
    mdl: int
    predicate: Callable[[MiniGraph], bool]

    def evaluate(self, graph: MiniGraph) -> bool:
        return bool(self.predicate(graph))


# Order is part of graph-dsl-v1 and must only change with a new DSL version.
GRAPH_ATOMS: tuple[Atom, ...] = (
    Atom("vertex_count_even", 3, _vertex_count_even),
    Atom("edge_count_even", 3, _edge_count_even),
    Atom("has_isolated_vertex", 3, _has_isolated_vertex),
    Atom("has_leaf", 3, _has_leaf),
    Atom("edges_at_least_vertices", 3, _edges_at_least_vertices),
    Atom("connected", 4, _is_connected),
    Atom("has_triangle", 4, _has_triangle),
    Atom("has_cycle", 4, _has_cycle),
    Atom("max_degree_at_least_three", 4, _max_degree_at_least_three),
    Atom("all_degrees_even", 4, _all_degrees_even),
    Atom("exactly_two_odd_degrees", 4, _exactly_two_odd_degrees),
    Atom("bipartite", 4, _is_bipartite),
    Atom("has_crossing", 4, _has_crossing),
    Atom("density_at_least_half", 4, _density_at_least_half),
)
_ATOM_BY_KEY = {atom.key: atom for atom in GRAPH_ATOMS}


@dataclass(frozen=True, slots=True)
class Rule:
    """An immutable canonical expression in the graph rule DSL."""

    op: str
    children: tuple["Rule", ...]
    atom_key: str | None
    mdl: int
    key: str

    @classmethod
    def atom(cls, atom: Atom) -> "Rule":
        return cls(
            op="atom",
            children=(),
            atom_key=atom.key,
            mdl=atom.mdl,
            key=atom.key,
        )

    @classmethod
    def negate(cls, child: "Rule") -> "Rule":
        return cls(
            op="not",
            children=(child,),
            atom_key=None,
            mdl=child.mdl + 2,
            key=f"!{child.key}",
        )

    @classmethod
    def combine(cls, op: str, children: Iterable["Rule"]) -> "Rule":
        normalized = tuple(sorted(children, key=lambda item: item.key))
        if op not in {"and", "or", "xor"}:
            raise ValueError(f"Unsupported rule operator: {op!r}")
        if len(normalized) < 2:
            raise ValueError("Combined rules require at least two children")
        symbol = {"and": "&", "or": "|", "xor": "^"}[op]
        overhead = (len(normalized) - 1) * (2 if op == "xor" else 1)
        return cls(
            op=op,
            children=normalized,
            atom_key=None,
            mdl=sum(child.mdl for child in normalized) + overhead,
            key=f"({symbol.join(child.key for child in normalized)})",
        )

    def evaluate(
        self,
        graph: MiniGraph,
        *,
        atom_values: Mapping[str, bool] | None = None,
    ) -> bool:
        values = atom_values
        if values is None:
            values = {
                atom.key: atom.evaluate(graph)
                for atom in GRAPH_ATOMS
            }
        if self.op == "atom":
            if self.atom_key is None:
                raise RuntimeError("Atom rule has no atom key")
            return bool(values[self.atom_key])
        if self.op == "not":
            return not self.children[0].evaluate(graph, atom_values=values)
        child_values = [
            child.evaluate(graph, atom_values=values)
            for child in self.children
        ]
        if self.op == "and":
            return all(child_values)
        if self.op == "or":
            return any(child_values)
        if self.op == "xor":
            return sum(child_values) % 2 == 1
        raise RuntimeError(f"Unknown rule operator: {self.op!r}")


@dataclass(frozen=True, slots=True)
class ProbeChoice:
    """The first maximum-entropy candidate in deterministic input order."""

    index: int
    graph: MiniGraph
    truth_mask: int
    gain_bits: float


def enumerate_rules(
    atoms: Sequence[Atom] = GRAPH_ATOMS,
) -> tuple[Rule, ...]:
    """Enumerate graph-dsl-v1 expressions in a fixed canonical order."""

    atom_rules = tuple(Rule.atom(atom) for atom in atoms)
    negated = tuple(Rule.negate(rule) for rule in atom_rules)
    rules: list[Rule] = [*atom_rules, *negated]

    for first, second in itertools.combinations(atom_rules, 2):
        rules.extend(
            Rule.combine(op, (first, second))
            for op in ("and", "or", "xor")
        )

    # Mixed literals add useful high-MDL alternatives without arbitrary nesting.
    for first_index, first in enumerate(atom_rules):
        for second_index, second in enumerate(atom_rules):
            if first_index == second_index:
                continue
            negative_second = negated[second_index]
            rules.extend(
                Rule.combine(op, (first, negative_second))
                for op in ("and", "or")
            )

    # Three-way positive clauses form the open-ended difficulty-five bucket.
    for children in itertools.combinations(atom_rules, 3):
        rules.extend(
            Rule.combine(op, children)
            for op in ("and", "or")
        )
    return tuple(rules)


def _atom_truth_masks(
    universe: Sequence[MiniGraph],
    atoms: Sequence[Atom],
) -> dict[str, int]:
    masks: dict[str, int] = {}
    for atom in atoms:
        mask = 0
        for graph_index, graph in enumerate(universe):
            if atom.evaluate(graph):
                mask |= 1 << graph_index
        masks[atom.key] = mask
    return masks


def _compile_rule_mask(
    rule: Rule,
    *,
    atom_masks: Mapping[str, int],
    universe_mask: int,
) -> int:
    if rule.op == "atom":
        if rule.atom_key is None:
            raise RuntimeError("Atom rule has no atom key")
        return atom_masks[rule.atom_key]
    if rule.op == "not":
        return universe_mask ^ _compile_rule_mask(
            rule.children[0],
            atom_masks=atom_masks,
            universe_mask=universe_mask,
        )
    child_masks = [
        _compile_rule_mask(
            child,
            atom_masks=atom_masks,
            universe_mask=universe_mask,
        )
        for child in rule.children
    ]
    result = child_masks[0]
    for child_mask in child_masks[1:]:
        if rule.op == "and":
            result &= child_mask
        elif rule.op == "or":
            result |= child_mask
        elif rule.op == "xor":
            result ^= child_mask
        else:
            raise RuntimeError(f"Unknown rule operator: {rule.op!r}")
    return result & universe_mask


def compile_truth_masks(
    rules: Sequence[Rule],
    universe: Sequence[MiniGraph],
    *,
    atoms: Sequence[Atom] = GRAPH_ATOMS,
) -> tuple[int, ...]:
    """Compile one universe-bitmask per rule."""

    if not universe:
        raise ValueError("A rule universe cannot be empty")
    atom_masks = _atom_truth_masks(universe, atoms)
    universe_mask = (1 << len(universe)) - 1
    return tuple(
        _compile_rule_mask(
            rule,
            atom_masks=atom_masks,
            universe_mask=universe_mask,
        )
        for rule in rules
    )


def distill_rules(
    rules: Sequence[Rule],
    universe: Sequence[MiniGraph],
    *,
    min_base_rate: float = MIN_BASE_RATE,
    max_base_rate: float = MAX_BASE_RATE,
    atoms: Sequence[Atom] = GRAPH_ATOMS,
) -> tuple[Rule, ...]:
    """Filter degenerate rules and retain the cheapest semantic representative."""

    if not 0 <= min_base_rate < max_base_rate <= 1:
        raise ValueError("Base-rate bounds must satisfy 0 <= min < max <= 1")
    compiled = compile_truth_masks(rules, universe, atoms=atoms)
    ordered = sorted(
        zip(rules, compiled, strict=True),
        key=lambda item: (item[0].mdl, item[0].key),
    )
    cheapest_by_truth: dict[int, Rule] = {}
    universe_size = len(universe)
    for rule, truth_mask in ordered:
        base_rate = truth_mask.bit_count() / universe_size
        if not min_base_rate <= base_rate <= max_base_rate:
            continue
        cheapest_by_truth.setdefault(truth_mask, rule)
    return tuple(
        sorted(
            cheapest_by_truth.values(),
            key=lambda rule: (rule.mdl, rule.key),
        )
    )


def rule_truth_mask(
    graph: MiniGraph,
    rules: Sequence[Rule],
    *,
    atoms: Sequence[Atom] = GRAPH_ATOMS,
) -> int:
    """Return a rule-index bitmask of rules accepting ``graph``."""

    atom_values = {
        atom.key: atom.evaluate(graph)
        for atom in atoms
    }
    mask = 0
    for rule_index, rule in enumerate(rules):
        if rule.evaluate(graph, atom_values=atom_values):
            mask |= 1 << rule_index
    return mask


def filter_version_space(
    version_space: int,
    graph_truth_mask: int,
    outcome: bool,
    *,
    all_rules_mask: int,
) -> int:
    """Filter a rule-index bitmask using one labelled graph observation."""

    compatible = (
        graph_truth_mask
        if outcome
        else all_rules_mask ^ graph_truth_mask
    )
    return version_space & compatible & all_rules_mask


def version_space_from_observations(
    observations: Iterable[tuple[int, bool]],
    *,
    rule_count: int,
    initial_version_space: int | None = None,
) -> int:
    """Build a rule-index bitmask from ``(truth_mask, outcome)`` pairs."""

    if rule_count < 1:
        raise ValueError("rule_count must be positive")
    all_rules_mask = (1 << rule_count) - 1
    version_space = (
        all_rules_mask
        if initial_version_space is None
        else initial_version_space & all_rules_mask
    )
    for graph_truth_mask, outcome in observations:
        version_space = filter_version_space(
            version_space,
            graph_truth_mask,
            outcome,
            all_rules_mask=all_rules_mask,
        )
    return version_space


def information_gain(version_space: int, graph_truth_mask: int) -> float:
    """Expected information gain, in bits, for a uniformly weighted VS."""

    size = version_space.bit_count()
    if size <= 1:
        return 0.0
    positive_count = (version_space & graph_truth_mask).bit_count()
    if positive_count in {0, size}:
        return 0.0
    positive_probability = positive_count / size
    negative_probability = 1.0 - positive_probability
    return -(
        positive_probability * math.log2(positive_probability)
        + negative_probability * math.log2(negative_probability)
    )


def actual_information_gain(
    version_space_before: int,
    version_space_after: int,
) -> float:
    """Realized reduction of the hypothesis set, in bits."""

    before_size = version_space_before.bit_count()
    after_size = version_space_after.bit_count()
    if before_size == 0 or after_size == 0 or after_size > before_size:
        return 0.0
    return math.log2(before_size / after_size)


def pick_probe_by_entropy(
    *,
    candidates: Sequence[MiniGraph],
    rules: Sequence[Rule],
    version_space: int,
    candidate_truth_masks: Sequence[int] | None = None,
) -> ProbeChoice | None:
    """Pick the maximum expected-information probe, with stable tie-breaking."""

    if not candidates or version_space.bit_count() <= 1:
        return None
    masks = (
        tuple(candidate_truth_masks)
        if candidate_truth_masks is not None
        else tuple(rule_truth_mask(graph, rules) for graph in candidates)
    )
    if len(masks) != len(candidates):
        raise ValueError("candidate_truth_masks must align with candidates")
    best_index = max(
        range(len(candidates)),
        key=lambda index: (information_gain(version_space, masks[index]), -index),
    )
    return ProbeChoice(
        index=best_index,
        graph=candidates[best_index],
        truth_mask=masks[best_index],
        gain_bits=information_gain(version_space, masks[best_index]),
    )


__all__ = [
    "GRAPH_ATOMS",
    "MAX_BASE_RATE",
    "MIN_BASE_RATE",
    "Atom",
    "ProbeChoice",
    "Rule",
    "actual_information_gain",
    "compile_truth_masks",
    "distill_rules",
    "enumerate_rules",
    "filter_version_space",
    "information_gain",
    "pick_probe_by_entropy",
    "rule_truth_mask",
    "version_space_from_observations",
]
