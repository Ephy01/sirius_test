"""Universe-agnostic core of the Zendo family engine.

The engine owns everything that made geo_zendo measurable: the starting
minimal example pair, version-space bounds, entropy-ranked probes with
ΔH telemetry, the near-miss exam and scoring. A concrete family plugs in
a :class:`ZendoUniverse` describing its configuration space.

Degeneracy filters required for every universe:

* deduplication by minimal MDL cost (``distill_rules`` keeps the cheapest
  semantic representative per truth mask);
* base rate of every retained rule within ``[MIN_BASE_RATE, MAX_BASE_RATE]``;
* every generated item carries a near-miss exam, so a minimal pair exists
  for the hidden rule by construction.

Rule-space assembly is cached per ``(universe_version, dsl_version)`` for
the lifetime of the process.
"""

from __future__ import annotations

import math
import random
import re
import threading
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Callable, Hashable, Protocol, Sequence

from .rule_dsl import (
    MAX_BASE_RATE,
    MIN_BASE_RATE,
    Atom,
    Rule,
    actual_information_gain,
    compile_truth_masks,
    distill_rules,
    filter_version_space,
    information_gain,
    pick_probe_by_entropy,
)

PROBE_BUDGET = 5
PROBE_CARD_COUNT = 12
TARGET_COUNT = 8
EXAMPLE_POSITIVE_COUNT = 2
EXAMPLE_NEGATIVE_COUNT = 2
NEAR_MISS_TOGGLED_COUNT = 4
NEAR_MISS_UNCHANGED_COUNT = 4
VERSION_SPACE_BOUNDS = (8, 64)
SELECTION_ATTEMPTS = 160


class ZendoUniverse(Protocol):
    """A configuration space pluggable into the shared Zendo engine."""

    universe_version: str
    dsl_version: str

    def population(self) -> tuple[Any, ...]:
        """Deterministic fixed population of configurations."""

    def atoms(self) -> tuple[Atom, ...]:
        """(name, MDL weight, predicate) primitives in canonical order."""

    def enumerate_rules(self) -> tuple[Rule, ...]:
        """All raw rule expressions before distillation."""

    def mutations(self, obj: Any) -> tuple[Any, ...]:
        """All one-step mutations of ``obj`` in a stable order."""

    def object_key(self, obj: Any) -> Hashable:
        """Stable, orderable identity used for dedup and tie-breaking."""

    def render_payload(self, obj: Any) -> dict[str, Any]:
        """Serializable public/private representation of ``obj``."""


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


@dataclass(frozen=True)
class UniverseSpace:
    """A distilled rule catalogue over one universe population."""

    universe_version: str
    dsl_version: str
    population: tuple[Any, ...]
    atoms: tuple[Atom, ...]
    rules: tuple[Rule, ...]
    truth_masks: tuple[int, ...]
    mdl_buckets: tuple[tuple[int, ...], ...]
    object_masks: tuple[int, ...]
    build_log: dict[str, Any] = field(default_factory=dict)

    @property
    def all_rules_mask(self) -> int:
        return (1 << len(self.rules)) - 1

    def indices_for_difficulty(self, difficulty: int) -> tuple[int, ...]:
        if not 1 <= difficulty <= 5:
            raise ValueError("difficulty must be between 1 and 5")
        return self.mdl_buckets[difficulty - 1]


def transpose_truth_masks(
    truth_masks: Sequence[int],
    population_size: int,
) -> tuple[int, ...]:
    """Turn per-rule population masks into per-object rule masks."""

    masks = [0] * population_size
    for rule_index, truth_mask in enumerate(truth_masks):
        rule_bit = 1 << rule_index
        remaining = truth_mask
        while remaining:
            least_bit = remaining & -remaining
            object_index = least_bit.bit_length() - 1
            masks[object_index] |= rule_bit
            remaining ^= least_bit
    return tuple(masks)


_SPACE_CACHE: dict[tuple[str, str], UniverseSpace] = {}
_SPACE_CACHE_LOCK = threading.Lock()


def build_universe_space(universe: ZendoUniverse) -> UniverseSpace:
    population = universe.population()
    atoms = universe.atoms()
    raw_rules = universe.enumerate_rules()
    rules = distill_rules(
        raw_rules,
        population,
        min_base_rate=MIN_BASE_RATE,
        max_base_rate=MAX_BASE_RATE,
        atoms=atoms,
    )
    truth_masks = compile_truth_masks(rules, population, atoms=atoms)
    buckets: list[list[int]] = [[] for _ in range(5)]
    for rule_index, rule in enumerate(rules):
        buckets[_mdl_bucket(rule) - 1].append(rule_index)
    if any(not bucket for bucket in buckets):
        raise RuntimeError(
            f"Universe {universe.universe_version!r} produced an empty "
            "MDL difficulty bucket"
        )
    return UniverseSpace(
        universe_version=universe.universe_version,
        dsl_version=universe.dsl_version,
        population=population,
        atoms=atoms,
        rules=rules,
        truth_masks=truth_masks,
        mdl_buckets=tuple(tuple(bucket) for bucket in buckets),
        object_masks=transpose_truth_masks(truth_masks, len(population)),
        build_log={
            "raw_rule_count": len(raw_rules),
            "distilled_rule_count": len(rules),
            "population_size": len(population),
        },
    )


def get_universe_space(universe: ZendoUniverse) -> UniverseSpace:
    """Return the once-per-process cached space for ``universe``."""

    cache_key = (universe.universe_version, universe.dsl_version)
    cached = _SPACE_CACHE.get(cache_key)
    if cached is not None:
        return cached
    with _SPACE_CACHE_LOCK:
        cached = _SPACE_CACHE.get(cache_key)
        if cached is None:
            cached = build_universe_space(universe)
            _SPACE_CACHE[cache_key] = cached
    return cached


def clear_universe_space_cache() -> None:
    with _SPACE_CACHE_LOCK:
        _SPACE_CACHE.clear()


@dataclass(frozen=True)
class ZendoMaterial:
    """Everything a family needs to assemble one Zendo task."""

    rule_index: int
    examples: list[Any]
    example_labels: list[bool]
    probes: list[Any]
    probe_masks: list[int]
    targets: list[Any]
    target_answers: list[bool]
    version_space: int


def _target_truth(*, object_mask: int, rule_index: int) -> bool:
    return bool(object_mask & (1 << rule_index))


def _version_space_after_examples(
    *,
    all_rules_mask: int,
    examples: Sequence[tuple[int, bool]],
) -> int:
    version_space = all_rules_mask
    for truth_mask, outcome in examples:
        version_space = filter_version_space(
            version_space,
            truth_mask,
            outcome,
            all_rules_mask=all_rules_mask,
        )
    return version_space


@lru_cache(maxsize=1 << 17)
def _atom_values(atoms: tuple[Atom, ...], obj: Hashable) -> dict[str, bool]:
    """Memoize per-object atom evaluations.

    Near-miss selection re-visits the same mutation candidates across
    attempts; caching keeps expensive geometric atoms one-shot without
    changing any outcome.
    """

    return {atom.key: atom.evaluate(obj) for atom in atoms}


def clear_atom_value_cache() -> None:
    _atom_values.cache_clear()


def evaluate_rule(
    rule: Rule,
    obj: Any,
    atoms: Sequence[Atom],
) -> bool:
    """Evaluate ``rule`` on ``obj`` using the universe's own atoms."""

    return rule.evaluate(obj, atom_values=_atom_values(tuple(atoms), obj))


def _near_miss_targets(
    *,
    rng: random.Random,
    rule: Rule,
    atoms: Sequence[Atom],
    mutations: Callable[[Any], tuple[Any, ...]],
    object_key: Callable[[Any], Hashable],
    positive_examples: list[Any],
    forbidden: set[Hashable],
) -> list[Any] | None:
    toggled: list[Any] = []
    unchanged: list[Any] = []
    seen = set(forbidden)
    for example in positive_examples:
        candidates = list(mutations(example))
        rng.shuffle(candidates)
        for candidate in candidates:
            key = object_key(candidate)
            if key in seen:
                continue
            seen.add(key)
            truth = evaluate_rule(rule, candidate, atoms)
            (unchanged if truth else toggled).append(candidate)
    if (
        len(toggled) < NEAR_MISS_TOGGLED_COUNT
        or len(unchanged) < NEAR_MISS_UNCHANGED_COUNT
    ):
        return None
    selected = [
        *rng.sample(toggled, NEAR_MISS_TOGGLED_COUNT),
        *rng.sample(unchanged, NEAR_MISS_UNCHANGED_COUNT),
    ]
    rng.shuffle(selected)
    return selected


def select_material(
    *,
    rng: random.Random,
    difficulty: int,
    pool: Sequence[Any],
    pool_masks: Sequence[int],
    rules: Sequence[Rule],
    atoms: Sequence[Atom],
    all_rules_mask: int,
    difficulty_rule_indices: Sequence[int],
    mutations: Callable[[Any], tuple[Any, ...]],
    object_key: Callable[[Any], Hashable],
    probe_card_count: int = PROBE_CARD_COUNT,
    version_space_bounds: tuple[int, int] = VERSION_SPACE_BOUNDS,
    selection_attempts: int = SELECTION_ATTEMPTS,
) -> ZendoMaterial:
    """Pick a rule, minimal example pairs, probes and a near-miss exam.

    The sequence of RNG consumption is part of every family's generator
    version: reordering the calls below is a breaking change.
    """

    pool = list(pool)
    pool_masks = list(pool_masks)
    candidate_rules = list(difficulty_rule_indices)
    rng.shuffle(candidate_rules)
    lower_bound, upper_bound = version_space_bounds

    for rule_index in candidate_rules:
        positives = [
            index
            for index, mask in enumerate(pool_masks)
            if _target_truth(object_mask=mask, rule_index=rule_index)
        ]
        negatives = [
            index
            for index, mask in enumerate(pool_masks)
            if not _target_truth(object_mask=mask, rule_index=rule_index)
        ]
        if (
            len(positives) < EXAMPLE_POSITIVE_COUNT
            or len(negatives) < EXAMPLE_NEGATIVE_COUNT
        ):
            continue
        for _ in range(selection_attempts):
            selected_indices = [
                *rng.sample(positives, EXAMPLE_POSITIVE_COUNT),
                *rng.sample(negatives, EXAMPLE_NEGATIVE_COUNT),
            ]
            example_observations = [
                (
                    pool_masks[index],
                    index in positives,
                )
                for index in selected_indices
            ]
            version_space = _version_space_after_examples(
                all_rules_mask=all_rules_mask,
                examples=example_observations,
            )
            if not lower_bound <= version_space.bit_count() <= upper_bound:
                continue
            examples = [pool[index] for index in selected_indices]
            example_labels = [index in positives for index in selected_indices]
            forbidden = {object_key(obj) for obj in examples}
            targets = _near_miss_targets(
                rng=rng,
                rule=rules[rule_index],
                atoms=atoms,
                mutations=mutations,
                object_key=object_key,
                positive_examples=[
                    obj
                    for obj, label in zip(
                        examples,
                        example_labels,
                        strict=True,
                    )
                    if label
                ],
                forbidden=forbidden,
            )
            if targets is None:
                continue
            forbidden.update(object_key(obj) for obj in targets)
            remaining = [
                (obj, truth_mask)
                for obj, truth_mask in zip(pool, pool_masks, strict=True)
                if object_key(obj) not in forbidden
            ]
            ranked = sorted(
                remaining,
                key=lambda item: (
                    -information_gain(version_space, item[1]),
                    object_key(item[0]),
                ),
            )
            selected_probes = ranked[:probe_card_count]
            probes = [obj for obj, _mask in selected_probes]
            probe_masks = [mask for _obj, mask in selected_probes]
            if len(probes) != probe_card_count:
                continue
            target_answers = [
                evaluate_rule(rules[rule_index], obj, atoms)
                for obj in targets
            ]
            return ZendoMaterial(
                rule_index=rule_index,
                examples=examples,
                example_labels=example_labels,
                probes=probes,
                probe_masks=probe_masks,
                targets=targets,
                target_answers=target_answers,
                version_space=version_space,
            )
    raise RuntimeError(
        f"Unable to select Zendo material at difficulty {difficulty}"
    )


@dataclass(frozen=True)
class ZendoProbeTransition:
    public_state: dict[str, Any]
    private_state: dict[str, Any]
    accepted: bool
    reason: str
    message: str
    normalized_card_id: str
    telemetry: dict[str, Any] | None


def transition_zendo_probe(
    *,
    card_id: str,
    public_state: dict[str, Any],
    private_state: dict[str, Any],
    all_rules_mask: int,
) -> ZendoProbeTransition:
    """Consume one probe: outcome, VS filtering and exact ΔH telemetry."""

    from copy import deepcopy

    next_public = deepcopy(public_state)
    next_private = deepcopy(private_state)
    normalized = card_id.strip().upper()
    probe_cards = next_private.get("probe_cards")
    probe_truth_masks = next_private.get("probe_truth_masks")
    used = [
        str(value)
        for value in next_private.get("used_probe_card_ids", [])
    ]
    if (
        not isinstance(probe_cards, dict)
        or not isinstance(probe_truth_masks, dict)
        or normalized not in probe_cards
        or normalized not in probe_truth_masks
    ):
        return ZendoProbeTransition(
            next_public,
            next_private,
            False,
            "unknown_probe_card",
            "Такой карточки нет среди доступных для проверки.",
            normalized,
            None,
        )
    if normalized in used:
        return ZendoProbeTransition(
            next_public,
            next_private,
            False,
            "probe_already_used",
            "Эта карточка уже была проверена.",
            normalized,
            None,
        )
    if int(next_private.get("probes_remaining") or 0) <= 0:
        return ZendoProbeTransition(
            next_public,
            next_private,
            False,
            "probe_budget_exhausted",
            "Лимит проверок исчерпан.",
            normalized,
            None,
        )

    rule_index = int(next_private["rule_index"])
    before = int(next_private["version_space"])
    available_ids = [
        candidate_id
        for candidate_id in sorted(probe_cards)
        if candidate_id not in used
    ]
    candidate_masks = [
        int(probe_truth_masks[candidate_id])
        for candidate_id in available_ids
    ]
    # ``pick_probe_by_entropy`` only touches the pre-compiled masks, so
    # the serialized payloads can stand in for the live objects.
    best = pick_probe_by_entropy(
        candidates=[probe_cards[candidate_id] for candidate_id in available_ids],
        rules=(),
        version_space=before,
        candidate_truth_masks=candidate_masks,
    )
    object_mask = int(probe_truth_masks[normalized])
    outcome = _target_truth(object_mask=object_mask, rule_index=rule_index)
    after = filter_version_space(
        before,
        object_mask,
        outcome,
        all_rules_mask=all_rules_mask,
    )
    telemetry = {
        "vs_size_before": before.bit_count(),
        "vs_size_after": after.bit_count(),
        "gain_bits_actual": actual_information_gain(before, after),
        "gain_bits_best": best.gain_bits if best is not None else 0.0,
    }
    next_private["version_space"] = after
    next_private["used_probe_card_ids"] = [*used, normalized]
    next_private["probes_remaining"] = int(
        next_private["probes_remaining"]
    ) - 1
    content = next_public["content"]
    content["probes_remaining"] = int(content["probes_remaining"]) - 1
    for item in content["probe_cards"]:
        if item["card_id"] == normalized:
            item["used"] = True
            break
    content["probe_observations"].append(
        {
            "card_id": normalized,
            "classification": "positive" if outcome else "negative",
        }
    )
    return ZendoProbeTransition(
        public_state=next_public,
        private_state=next_private,
        accepted=True,
        reason="accepted",
        message=(
            f"Карточка {normalized}: "
            f"{'подходит' if outcome else 'не подходит'}."
        ),
        normalized_card_id=normalized,
        telemetry=telemetry,
    )


def parse_boolean_sequence(answer: str) -> list[bool] | None:
    """Parse yes/no sequences in the shared /answer format."""

    normalized = re.sub(
        r"^\s*/?answer\b",
        "",
        answer.strip().casefold(),
    ).strip()
    if not normalized:
        return None
    tokens = [
        token
        for token in re.split(r"[\s,;|/]+", normalized)
        if token
    ]
    true_tokens = {"да", "yes", "y", "1", "true", "+"}
    false_tokens = {"нет", "no", "n", "0", "false", "-"}
    parsed: list[bool] = []
    for token in tokens:
        if token in true_tokens:
            parsed.append(True)
        elif token in false_tokens:
            parsed.append(False)
        else:
            return None
    return parsed


def evaluate_zendo_answer(
    *,
    answer: str,
    private_state: dict[str, Any],
) -> dict[str, Any]:
    """Score the near-miss exam with the shared probe-economy bonus."""

    expected = [bool(value) for value in private_state["target_answers"]]
    parsed = parse_boolean_sequence(answer)
    valid = parsed is not None and len(parsed) == len(expected)
    correct_count = (
        sum(
            submitted == expected_value
            for submitted, expected_value in zip(
                parsed,
                expected,
                strict=True,
            )
        )
        if valid and parsed is not None
        else 0
    )
    accuracy = correct_count / len(expected)
    unused_probes = int(private_state.get("probes_remaining") or 0)
    zendo_score = (
        max(0.0, accuracy - 0.5)
        * 2
        * (1 + 0.05 * unused_probes)
    )
    exact = bool(valid and correct_count == len(expected))
    hint_used = bool(private_state.get("hint_used"))
    continuous_score = min(1.0, zendo_score)
    if hint_used:
        continuous_score *= HINT_SCORE_MULTIPLIER
    return {
        "correct": exact,
        "parsed": valid,
        "submitted_sequence": parsed if valid else None,
        "target_count": len(expected),
        "correct_count": correct_count,
        "accuracy": accuracy,
        "unused_probes": unused_probes,
        "zendo_score": zendo_score,
        "hint_used": hint_used,
        "continuous_score": continuous_score,
        "efficient": exact and unused_probes > 0,
        "evidence": 1 if exact else -1,
    }


def entropy_bits(count: int) -> float:
    """Version-space size expressed in bits."""

    return math.log2(count) if count > 0 else 0.0


# Fixed dictionary of graduated-prompt categories (stage C.2). Season one
# treats /hint as a research metric only.
HINT_SCORE_MULTIPLIER = 0.7
HINT_CATEGORY_LABELS = {
    "count": "правило про количество",
    "symmetry": "правило про симметрию",
    "neighbors": "правило про соседние элементы",
    "color": "правило про цвет",
    "arrangement": "правило про взаимное расположение",
    "connectivity": "правило про связность и форму области",
    "combination": "правило-комбинация двух условий",
}


def rule_hint_category(rule: Rule, atom_categories: dict[str, str]) -> str:
    """Resolve the fixed hint-dictionary label for a hidden rule."""

    def category_key(current: Rule) -> str:
        if current.op == "atom":
            if current.atom_key is None:
                raise RuntimeError("Atom rule has no atom key")
            return atom_categories[current.atom_key]
        if current.op == "not":
            return category_key(current.children[0])
        return "combination"

    return HINT_CATEGORY_LABELS[category_key(rule)]


@dataclass(frozen=True)
class ZendoHintTransition:
    public_state: dict[str, Any]
    private_state: dict[str, Any]
    accepted: bool
    reason: str
    message: str
    telemetry: dict[str, Any] | None


def transition_zendo_hint(
    *,
    public_state: dict[str, Any],
    private_state: dict[str, Any],
    category: str,
) -> ZendoHintTransition:
    """Consume the single paid hint: category reveal at 0.7 score cost."""

    from copy import deepcopy

    next_public = deepcopy(public_state)
    next_private = deepcopy(private_state)
    if next_private.get("hint_used"):
        return ZendoHintTransition(
            next_public,
            next_private,
            False,
            "hint_already_used",
            "Подсказка уже использована в этой задаче.",
            None,
        )
    next_private["hint_used"] = True
    next_private["hint_category_used"] = category
    next_public["hint"] = {"category": category}
    return ZendoHintTransition(
        public_state=next_public,
        private_state=next_private,
        accepted=True,
        reason="accepted",
        message=(
            f"Подсказка: это {category}. "
            f"Скор задачи будет умножен на {HINT_SCORE_MULTIPLIER}."
        ),
        telemetry={
            "hint_category": category,
            "score_multiplier": HINT_SCORE_MULTIPLIER,
        },
    )


__all__ = [
    "EXAMPLE_NEGATIVE_COUNT",
    "EXAMPLE_POSITIVE_COUNT",
    "HINT_CATEGORY_LABELS",
    "HINT_SCORE_MULTIPLIER",
    "ZendoHintTransition",
    "rule_hint_category",
    "transition_zendo_hint",
    "NEAR_MISS_TOGGLED_COUNT",
    "NEAR_MISS_UNCHANGED_COUNT",
    "PROBE_BUDGET",
    "PROBE_CARD_COUNT",
    "SELECTION_ATTEMPTS",
    "TARGET_COUNT",
    "VERSION_SPACE_BOUNDS",
    "UniverseSpace",
    "ZendoMaterial",
    "ZendoProbeTransition",
    "ZendoUniverse",
    "build_universe_space",
    "clear_universe_space_cache",
    "entropy_bits",
    "evaluate_rule",
    "evaluate_zendo_answer",
    "get_universe_space",
    "parse_boolean_sequence",
    "select_material",
    "transition_zendo_probe",
    "transpose_truth_masks",
]
