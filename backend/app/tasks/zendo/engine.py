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

import random
import re
import threading
from collections.abc import Callable, Hashable, Sequence
from copy import deepcopy
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Protocol

from sirius_gate.family import FamilyCard, State, TaskFamily, Transition, required_text

from ..graphs import scene_cards
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
EXAMPLE_POSITIVE_COUNT = 2
EXAMPLE_NEGATIVE_COUNT = 2
NEAR_MISS_TOGGLED_COUNT = 4
NEAR_MISS_UNCHANGED_COUNT = 4
VERSION_SPACE_BOUNDS = (8, 64)
SELECTION_ATTEMPTS = 160
# Сколько проб каждого исхода гарантируется в наборе карточек. Ранжирование
# по ожидаемому выигрышу само по себе не смотрит на истинность загаданного
# правила, поэтому у редких правил весь топ-12 оказывался одного знака.
PROBE_OUTCOME_QUOTA = 4
ANSWER_RESPONSE_HINT = (
    'Ответьте восемью значениями в порядке целей (1 — подходит, 0 — нет): /answer 1 0 1 0 1 0 1 0.'
)


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

    @property
    def all_rules_mask(self) -> int:
        return (1 << len(self.rules)) - 1

    def indices_for_difficulty(self, difficulty: int) -> tuple[int, ...]:
        if not 1 <= difficulty <= 5:
            raise ValueError('difficulty must be between 1 and 5')
        return self.mdl_buckets[difficulty - 1]


def transpose_truth_masks(truth_masks: Sequence[int], population_size: int) -> tuple[int, ...]:
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
        raw_rules, population, min_base_rate=MIN_BASE_RATE, max_base_rate=MAX_BASE_RATE, atoms=atoms
    )
    truth_masks = compile_truth_masks(rules, population, atoms=atoms)
    buckets: list[list[int]] = [[] for _ in range(5)]
    for rule_index, rule in enumerate(rules):
        buckets[_mdl_bucket(rule) - 1].append(rule_index)
    if any(not bucket for bucket in buckets):
        raise RuntimeError(f'Universe {universe.universe_version!r} produced an empty MDL difficulty bucket')
    return UniverseSpace(
        universe_version=universe.universe_version,
        dsl_version=universe.dsl_version,
        population=population,
        atoms=atoms,
        rules=rules,
        truth_masks=truth_masks,
        mdl_buckets=tuple(tuple(bucket) for bucket in buckets),
        object_masks=transpose_truth_masks(truth_masks, len(population)),
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


def _numbered(prefix: str, objects: Sequence[Any]) -> list[tuple[str, Any]]:
    return [(f'{prefix}{index:02d}', obj) for index, obj in enumerate(objects, start=1)]


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

    @property
    def example_cards(self) -> list[tuple[str, Any]]:
        return _numbered('E', self.examples)

    @property
    def probe_cards(self) -> list[tuple[str, Any]]:
        return _numbered('P', self.probes)

    @property
    def target_cards(self) -> list[tuple[str, Any]]:
        return _numbered('T', self.targets)


def _target_truth(*, object_mask: int, rule_index: int) -> bool:
    return bool(object_mask & (1 << rule_index))


def _version_space_after_examples(*, all_rules_mask: int, examples: Sequence[tuple[int, bool]]) -> int:
    version_space = all_rules_mask
    for truth_mask, outcome in examples:
        version_space = filter_version_space(
            version_space, truth_mask, outcome, all_rules_mask=all_rules_mask
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


def evaluate_rule(rule: Rule, obj: Any, atoms: Sequence[Atom]) -> bool:
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
    if len(toggled) < NEAR_MISS_TOGGLED_COUNT or len(unchanged) < NEAR_MISS_UNCHANGED_COUNT:
        return None
    selected = [
        *rng.sample(toggled, NEAR_MISS_TOGGLED_COUNT),
        *rng.sample(unchanged, NEAR_MISS_UNCHANGED_COUNT),
    ]
    rng.shuffle(selected)
    return selected


@dataclass(frozen=True)
class _MaterialSelector:
    """Selection parameters of one generator call and the steps of a single selection attempt."""

    pool: list[Any]
    pool_masks: list[int]
    rules: Sequence[Rule]
    atoms: Sequence[Atom]
    all_rules_mask: int
    mutations: Callable[[Any], tuple[Any, ...]]
    object_key: Callable[[Any], Hashable]
    probe_card_count: int
    probe_outcome_quota: int
    version_space_bounds: tuple[int, int]

    def split_pool(self, rule_index: int) -> tuple[list[int], list[int]]:
        """Pool indices of the objects that satisfy the rule and of those that do not."""

        positives = [
            index
            for index, mask in enumerate(self.pool_masks)
            if _target_truth(object_mask=mask, rule_index=rule_index)
        ]
        negatives = [
            index
            for index, mask in enumerate(self.pool_masks)
            if not _target_truth(object_mask=mask, rule_index=rule_index)
        ]
        return positives, negatives

    def probe_cards(
        self, rng: random.Random, rule_index: int, version_space: int, forbidden: set[Hashable]
    ) -> list[tuple[Any, int]]:
        """The most informative unused objects with a quota of each outcome, in shuffled order."""

        remaining = [
            (obj, truth_mask)
            for obj, truth_mask in zip(self.pool, self.pool_masks, strict=True)
            if self.object_key(obj) not in forbidden
        ]
        ranked = sorted(
            remaining, key=lambda item: (-information_gain(version_space, item[1]), self.object_key(item[0]))
        )
        positive_ranked = [
            item for item in ranked if _target_truth(object_mask=item[1], rule_index=rule_index)
        ]
        negative_ranked = [
            item for item in ranked if not _target_truth(object_mask=item[1], rule_index=rule_index)
        ]
        quota = min(self.probe_outcome_quota, len(positive_ranked), len(negative_ranked))
        chosen_keys = {
            self.object_key(obj) for obj, _mask in [*positive_ranked[:quota], *negative_ranked[:quota]]
        }
        for obj, _mask in ranked:
            if len(chosen_keys) >= self.probe_card_count:
                break
            chosen_keys.add(self.object_key(obj))
        selected_probes = [item for item in ranked if self.object_key(item[0]) in chosen_keys][
            : self.probe_card_count
        ]
        # Порядок карточек перемешивается: по рангу выигрыша квота исходов
        # ложится в хвост, и первые пробы участника оказывались одного
        # знака. Перемешивание заодно не даёт позиции карточки подсказывать
        # её исход.
        # The shuffle draws from the generator even if the caller then discards the attempt
        # for having too few cards. Moving it changes every generated task.
        rng.shuffle(selected_probes)
        return selected_probes

    def attempt(
        self, rng: random.Random, rule_index: int, positives: list[int], negatives: list[int]
    ) -> ZendoMaterial | None:
        """Draw examples, then build the near-miss exam and the probes around them."""

        selected_indices = [
            *rng.sample(positives, EXAMPLE_POSITIVE_COUNT),
            *rng.sample(negatives, EXAMPLE_NEGATIVE_COUNT),
        ]
        example_observations = [(self.pool_masks[index], index in positives) for index in selected_indices]
        version_space = _version_space_after_examples(
            all_rules_mask=self.all_rules_mask, examples=example_observations
        )
        lower_bound, upper_bound = self.version_space_bounds
        if not lower_bound <= version_space.bit_count() <= upper_bound:
            return None
        examples = [self.pool[index] for index in selected_indices]
        example_labels = [index in positives for index in selected_indices]
        forbidden = {self.object_key(obj) for obj in examples}
        targets = _near_miss_targets(
            rng=rng,
            rule=self.rules[rule_index],
            atoms=self.atoms,
            mutations=self.mutations,
            object_key=self.object_key,
            positive_examples=[obj for obj, label in zip(examples, example_labels, strict=True) if label],
            forbidden=forbidden,
        )
        if targets is None:
            return None
        forbidden.update(self.object_key(obj) for obj in targets)
        selected_probes = self.probe_cards(rng, rule_index, version_space, forbidden)
        if len(selected_probes) != self.probe_card_count:
            return None
        return ZendoMaterial(
            rule_index=rule_index,
            examples=examples,
            example_labels=example_labels,
            probes=[obj for obj, _mask in selected_probes],
            probe_masks=[mask for _obj, mask in selected_probes],
            targets=targets,
            target_answers=[evaluate_rule(self.rules[rule_index], obj, self.atoms) for obj in targets],
            version_space=version_space,
        )


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
    probe_outcome_quota: int = PROBE_OUTCOME_QUOTA,
    version_space_bounds: tuple[int, int] = VERSION_SPACE_BOUNDS,
    selection_attempts: int = SELECTION_ATTEMPTS,
) -> ZendoMaterial:
    """Pick a rule, minimal example pairs, probes and a near-miss exam.

    The sequence of RNG consumption, here and in ``_MaterialSelector``, is
    part of every family's generator version: reordering the calls is a
    breaking change.
    """

    lower_bound, upper_bound = version_space_bounds
    selector = _MaterialSelector(
        pool=list(pool),
        pool_masks=list(pool_masks),
        rules=rules,
        atoms=atoms,
        all_rules_mask=all_rules_mask,
        mutations=mutations,
        object_key=object_key,
        probe_card_count=probe_card_count,
        probe_outcome_quota=probe_outcome_quota,
        version_space_bounds=(lower_bound, upper_bound),
    )
    candidate_rules = list(difficulty_rule_indices)
    rng.shuffle(candidate_rules)
    for rule_index in candidate_rules:
        positives, negatives = selector.split_pool(rule_index)
        if len(positives) < EXAMPLE_POSITIVE_COUNT or len(negatives) < EXAMPLE_NEGATIVE_COUNT:
            continue
        for _ in range(selection_attempts):
            material = selector.attempt(rng, rule_index, positives, negatives)
            if material is not None:
                return material
    raise RuntimeError(f'Unable to select Zendo material at difficulty {difficulty}')


def universe_material(
    rng: random.Random, difficulty: int, universe: ZendoUniverse
) -> tuple[UniverseSpace, ZendoMaterial]:
    """Material selected from the cached rule space of ``universe``."""

    space = get_universe_space(universe)
    material = select_material(
        rng=rng,
        difficulty=difficulty,
        pool=space.population,
        pool_masks=space.object_masks,
        rules=space.rules,
        atoms=space.atoms,
        all_rules_mask=space.all_rules_mask,
        difficulty_rule_indices=space.indices_for_difficulty(difficulty),
        mutations=universe.mutations,
        object_key=universe.object_key,
    )
    return space, material


def public_content(material: ZendoMaterial, *, probe_cards: bool = True) -> State:
    """Labelled examples, the probe cards of a family that deals them, and the targets of the exam."""

    content: State = {
        'examples': [
            {'card_id': card_id, 'classification': 'positive' if label else 'negative'}
            for (card_id, _obj), label in zip(material.example_cards, material.example_labels, strict=True)
        ]
    }
    if probe_cards:
        content['probe_cards'] = [
            {'card_id': card_id, 'used': False} for card_id, _obj in material.probe_cards
        ]
    content['targets'] = [
        {'card_id': card_id, 'position': index}
        for index, (card_id, _obj) in enumerate(material.target_cards, start=1)
    ]
    content['probe_budget'] = PROBE_BUDGET
    content['probes_remaining'] = PROBE_BUDGET
    content['probe_observations'] = []
    return content


def card_probes(material: ZendoMaterial, serialize: Callable[[Any], Any]) -> State:
    """Private record of dealt probe cards: their content, rule masks and the cards already used."""

    return {
        'probe_cards': {card_id: serialize(obj) for card_id, obj in material.probe_cards},
        'probe_truth_masks': {
            card_id: truth_mask
            for (card_id, _obj), truth_mask in zip(material.probe_cards, material.probe_masks, strict=True)
        },
        'used_probe_card_ids': [],
    }


def private_state(material: ZendoMaterial, *, identity: State, probes: State, **extra: Any) -> State:
    """Hidden rule, version space, probe record and exam answers in the order every family stores them."""

    return {
        **identity,
        'rule_index': material.rule_index,
        'version_space': material.version_space,
        'version_space_after_examples': material.version_space,
        **probes,
        'probe_budget': PROBE_BUDGET,
        'probes_remaining': PROBE_BUDGET,
        'target_card_ids': [card_id for card_id, _obj in material.target_cards],
        'target_answers': material.target_answers,
        **extra,
    }


def _probe_refusal(private_state: State, card_id: str) -> tuple[str, str] | None:
    probe_cards = private_state.get('probe_cards')
    probe_truth_masks = private_state.get('probe_truth_masks')
    used = [str(value) for value in private_state.get('used_probe_card_ids', [])]
    if (
        not isinstance(probe_cards, dict)
        or not isinstance(probe_truth_masks, dict)
        or card_id not in probe_cards
        or card_id not in probe_truth_masks
    ):
        return 'unknown_probe_card', 'Такой карточки нет среди доступных для проверки.'
    if card_id in used:
        return 'probe_already_used', 'Эта карточка уже была проверена.'
    if int(private_state.get('probes_remaining') or 0) <= 0:
        return 'probe_budget_exhausted', 'Лимит проверок исчерпан.'
    return None


def _consume_probe(private_state: State, card_id: str, all_rules_mask: int) -> tuple[bool, State]:
    """Filter the version space by the probe; returns its outcome and the ΔH telemetry."""

    probe_cards = private_state['probe_cards']
    probe_truth_masks = private_state['probe_truth_masks']
    used = [str(value) for value in private_state.get('used_probe_card_ids', [])]
    rule_index = int(private_state['rule_index'])
    before = int(private_state['version_space'])
    available_ids = [candidate_id for candidate_id in sorted(probe_cards) if candidate_id not in used]
    candidate_masks = [int(probe_truth_masks[candidate_id]) for candidate_id in available_ids]
    best = pick_probe_by_entropy(
        candidates=[probe_cards[candidate_id] for candidate_id in available_ids],
        rules=(),
        version_space=before,
        candidate_truth_masks=candidate_masks,
    )
    object_mask = int(probe_truth_masks[card_id])
    outcome = _target_truth(object_mask=object_mask, rule_index=rule_index)
    after = filter_version_space(before, object_mask, outcome, all_rules_mask=all_rules_mask)
    telemetry = {
        'vs_size_before': before.bit_count(),
        'vs_size_after': after.bit_count(),
        'gain_bits_actual': actual_information_gain(before, after),
        'gain_bits_best': best.gain_bits if best is not None else 0.0,
    }
    private_state['version_space'] = after
    private_state['used_probe_card_ids'] = [*used, card_id]
    private_state['probes_remaining'] = int(private_state['probes_remaining']) - 1
    return outcome, telemetry


def _show_probe(content: State, card_id: str, outcome: bool) -> None:
    content['probes_remaining'] = int(content['probes_remaining']) - 1
    for item in content['probe_cards']:
        if item['card_id'] == card_id:
            item['used'] = True
            break
    content['probe_observations'].append(
        {'card_id': card_id, 'classification': 'positive' if outcome else 'negative'}
    )


def transition_zendo_probe(
    *, card_id: str, public_state: dict[str, Any], private_state: dict[str, Any], all_rules_mask: int
) -> Transition:
    """Consume one probe: outcome, VS filtering and exact ΔH telemetry."""

    next_public = deepcopy(public_state)
    next_private = deepcopy(private_state)
    normalized = card_id.strip().upper()
    refusal = _probe_refusal(next_private, normalized)
    if refusal is not None:
        return Transition(next_public, next_private, False, *refusal, normalized)
    outcome, telemetry = _consume_probe(next_private, normalized, all_rules_mask)
    _show_probe(next_public['content'], normalized, outcome)
    return Transition(
        public_state=next_public,
        private_state=next_private,
        accepted=True,
        reason='accepted',
        message=(f'Конструкция {normalized}: {"подходит" if outcome else "не подходит"}.'),
        normalized_input=normalized,
        evaluation_state=telemetry,
    )


def parse_boolean_sequence(answer: str) -> list[bool] | None:
    """Parse yes/no sequences in the shared /answer format."""

    normalized = re.sub(r'^\s*/?answer\b', '', answer.strip().casefold()).strip()
    if not normalized:
        return None
    tokens = [token for token in re.split(r'[\s,;|/]+', normalized) if token]
    true_tokens = {'да', 'yes', 'y', '1', 'true', '+'}
    false_tokens = {'нет', 'no', 'n', '0', 'false', '-'}
    parsed: list[bool] = []
    for token in tokens:
        if token in true_tokens:
            parsed.append(True)
        elif token in false_tokens:
            parsed.append(False)
        else:
            return None
    return parsed


def evaluate_zendo_answer(*, answer: str, private_state: dict[str, Any]) -> dict[str, Any]:
    """Score the near-miss exam with the shared probe-economy bonus."""

    expected = [bool(value) for value in private_state['target_answers']]
    parsed = parse_boolean_sequence(answer)
    valid = parsed is not None and len(parsed) == len(expected)
    correct_count = (
        sum(submitted == expected_value for submitted, expected_value in zip(parsed, expected, strict=True))
        if valid and parsed is not None
        else 0
    )
    accuracy = correct_count / len(expected)
    unused_probes = int(private_state.get('probes_remaining') or 0)
    zendo_score = max(0.0, accuracy - 0.5) * 2 * (1 + 0.05 * unused_probes)
    exact = bool(valid and correct_count == len(expected))
    hint_used = bool(private_state.get('hint_used'))
    continuous_score = min(1.0, zendo_score)
    if hint_used:
        continuous_score *= HINT_SCORE_MULTIPLIER
    return {
        'correct': exact,
        'parsed': valid,
        'submitted_sequence': parsed if valid else None,
        'target_count': len(expected),
        'correct_count': correct_count,
        'accuracy': accuracy,
        'unused_probes': unused_probes,
        'zendo_score': zendo_score,
        'hint_used': hint_used,
        'continuous_score': continuous_score,
        'efficient': exact and unused_probes > 0,
        'evidence': 1 if exact else -1,
    }


HINT_SCORE_MULTIPLIER = 0.7
HINT_CATEGORY_LABELS = {
    'count': 'правило про количество',
    'symmetry': 'правило про симметрию',
    'neighbors': 'правило про соседние элементы',
    'color': 'правило про цвет',
    'arrangement': 'правило про взаимное расположение',
    'connectivity': 'правило про связность и форму области',
    'combination': 'правило-комбинация двух условий',
}


def describe_rule(rule: Rule, atom_descriptions: dict[str, str]) -> str:
    """Render a hidden rule as a human-readable Russian sentence."""

    if rule.op == 'atom':
        if rule.atom_key is None:
            raise RuntimeError('Atom rule has no atom key')
        return atom_descriptions.get(rule.atom_key, rule.atom_key)
    if rule.op == 'not':
        return 'НЕ (' + describe_rule(rule.children[0], atom_descriptions) + ')'
    parts = [describe_rule(child, atom_descriptions) for child in rule.children]
    if rule.op == 'and':
        return '(' + ' И '.join(parts) + ')'
    if rule.op == 'or':
        return '(' + ' ИЛИ '.join(parts) + ')'
    if rule.op == 'xor':
        return 'ровно одно из: (' + '; '.join(parts) + ')'
    raise RuntimeError(f'Unknown rule operator: {rule.op!r}')


def rule_hint_category(rule: Rule, atom_categories: dict[str, str]) -> str:
    """Resolve the fixed hint-dictionary label for a hidden rule."""

    def category_key(current: Rule) -> str:
        if current.op == 'atom':
            if current.atom_key is None:
                raise RuntimeError('Atom rule has no atom key')
            return atom_categories[current.atom_key]
        if current.op == 'not':
            return category_key(current.children[0])
        return 'combination'

    return HINT_CATEGORY_LABELS[category_key(rule)]


def transition_zendo_hint(
    *, public_state: dict[str, Any], private_state: dict[str, Any], category: str
) -> Transition:
    """Consume the single paid hint: category reveal at 0.7 score cost."""

    next_public = deepcopy(public_state)
    next_private = deepcopy(private_state)
    if next_private.get('hint_used'):
        return Transition(
            next_public,
            next_private,
            False,
            'hint_already_used',
            'Подсказка уже использована в этой задаче.',
            'hint',
        )
    next_private['hint_used'] = True
    next_private['hint_category_used'] = category
    next_public['hint'] = {'category': category}
    return Transition(
        public_state=next_public,
        private_state=next_private,
        accepted=True,
        reason='accepted',
        message=(f'Подсказка: это {category}. Скор задачи будет умножен на {HINT_SCORE_MULTIPLIER}.'),
        normalized_input='hint',
        evaluation_state={'hint_category': category, 'score_multiplier': HINT_SCORE_MULTIPLIER},
    )


CLASSIFICATION_LABELS = {'positive': 'подходит', 'negative': 'не подходит'}


def classification_label(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    return CLASSIFICATION_LABELS.get(value, value)


def _card_role(card_id: str, classification: str | None, tested: bool) -> str:
    if card_id.startswith('E'):
        return 'positive_example' if classification == 'подходит' else 'negative_example'
    if card_id.startswith('T'):
        return 'target'
    return 'tested_probe' if tested else 'available_probe'


def _card_ids(items: Any) -> list[tuple[str, dict[str, Any]]]:
    return [
        (item['card_id'], item)
        for item in items or []
        if isinstance(item, dict) and isinstance(item.get('card_id'), str)
    ]


def card_visibility(public_state: State) -> tuple[dict[str, str], dict[str, str | None]]:
    """Roles and already revealed classifications of every visible card."""

    content = public_state.get('content') if isinstance(public_state.get('content'), dict) else {}
    classification: dict[str, str | None] = {}
    tested: set[str] = set()
    for card_id, example in _card_ids(content.get('examples')):
        classification[card_id] = classification_label(example.get('classification'))
    for card_id, observation in _card_ids(content.get('probe_observations')):
        tested.add(card_id)
        classification[card_id] = classification_label(observation.get('classification'))
    roles: dict[str, str] = {}
    for card_id, _example in _card_ids(content.get('examples')):
        roles[card_id] = _card_role(card_id, classification.get(card_id), False)
    for card_id, _probe in _card_ids(content.get('probe_cards')):
        roles[card_id] = _card_role(card_id, None, card_id in tested)
    for card_id, _target in _card_ids(content.get('targets')):
        roles[card_id] = 'target'
    return roles, classification


def probe_limits(public_state: State) -> State:
    content = public_state.get('content') if isinstance(public_state.get('content'), dict) else {}
    return {'probesRemaining': content.get('probes_remaining'), 'probeBudget': content.get('probe_budget')}


def scene_context(public_state: State) -> State:
    """Cards drawn as subgraphs of one shared scene (graphs and point sets)."""

    roles, classifications = card_visibility(public_state)
    cards = scene_cards(public_state)
    visible = []
    for card_id in sorted(roles):
        card = cards.get(card_id, {'vertices': [], 'edges': []})
        visible.append(
            {
                'id': card_id,
                'role': roles[card_id],
                'classification': classifications.get(card_id),
                'vertices': card['vertices'],
                'edges': card['edges'],
            }
        )
    return {'cards': visible, 'limits': probe_limits(public_state)}


def reference_answer(private_state: State) -> tuple[str, list[str]]:
    answers = private_state.get('target_answers', [])
    return '/answer ' + ' '.join('да' if value else 'нет' for value in answers), []


def target_details(private_state: State) -> str:
    target_ids = [str(item) for item in private_state.get('target_card_ids', [])]
    answers = [bool(item) for item in private_state.get('target_answers', [])]
    return 'Цели: ' + ', '.join(
        f'{card_id} → {"да" if answer else "нет"}'
        for card_id, answer in zip(target_ids, answers, strict=False)
    )


def rule_details(private_state: State, rules: Sequence[Rule], atom_descriptions: dict[str, str]) -> list[str]:
    rule = rules[int(private_state['rule_index'])]
    details = [
        f'Скрытое правило: {describe_rule(rule, atom_descriptions)}',
        f'Формула правила: {rule.key} (MDL {rule.mdl})',
    ]
    if private_state.get('hint_category'):
        details.append(f'Категория подсказки: {private_state["hint_category"]}')
    version_space = int(private_state.get('version_space') or 0)
    after_examples = int(private_state.get('version_space_after_examples') or 0)
    details.append(
        'Гипотез в version space: '
        f'{version_space.bit_count()} сейчас, '
        f'{after_examples.bit_count()} после примеров'
    )
    details.append(target_details(private_state))
    return details


def zendo_family(
    *,
    key: str,
    version: str,
    generate: Callable[..., tuple[State, State]],
    universe: ZendoUniverse,
    atom_descriptions: dict[str, str],
    ai_context: Callable[[State], State],
    aliases: tuple[str, ...] = (),
    probe: Callable[[State, State, State], Transition] | None = None,
    card: FamilyCard | None = None,
) -> TaskFamily:
    """Assemble a Zendo family: shared hint, scoring and debug views."""

    def card_probe(payload: State, public_state: State, private_state: State) -> Transition:
        return transition_zendo_probe(
            card_id=required_text(payload, 'probe', 'Probe payload must contain a string probe'),
            public_state=public_state,
            private_state=private_state,
            all_rules_mask=get_universe_space(universe).all_rules_mask,
        )

    def hint(payload: State, public_state: State, private_state: State) -> Transition:
        return transition_zendo_hint(
            public_state=public_state,
            private_state=private_state,
            category=str(private_state['hint_category']),
        )

    return TaskFamily(
        key=key,
        version=version,
        generate=lambda seed, difficulty, context: generate(seed=seed, difficulty=difficulty),
        evaluate=lambda answer, private_state: evaluate_zendo_answer(
            answer=answer, private_state=private_state
        ),
        actions={'probe': probe or card_probe, 'hint': hint},
        probe_action='probe',
        aliases=aliases,
        reference_answer=reference_answer,
        debug_details=lambda private_state: rule_details(
            private_state, get_universe_space(universe).rules, atom_descriptions
        ),
        ai_context=ai_context,
        card=card,
    )
