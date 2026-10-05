"""token_zendo: hidden rules over sequences of numbered colour tokens.

The cheapest universe of the multiverse rollout — sequences of three to
seven tokens, each carrying ``num`` in 1..9 and ``color`` in {R, G, B}.
XOR hybrids of number and colour atoms come out of the shared rule
combinators for free.
"""

from __future__ import annotations

import math
import random
from collections.abc import Hashable
from typing import Any

from sirius_gate.family import FamilyCard, State

from .engine import (
    ANSWER_RESPONSE_HINT,
    card_probes,
    card_visibility,
    private_state,
    probe_limits,
    public_content,
    rule_hint_category,
    universe_material,
    zendo_family,
)
from .rule_dsl import Atom, Rule, enumerate_rules

FAMILY_KEY = 'token_zendo'
GENERATOR_VERSION = 'token-zendo-v2'
PUBLIC_KIND = 'token_zendo'
UNIVERSE_VERSION = 'token-universe-v1'
DSL_VERSION = 'token-dsl-v1'

TOKEN_COLORS = ('R', 'G', 'B')
MIN_TOKEN_VALUE = 1
MAX_TOKEN_VALUE = 9
MIN_LENGTH = 3
MAX_LENGTH = 7
POPULATION_SIZE = 1200
_POPULATION_SEED = 0x70CE_2026
PROMPT = (
    'Загадано некоторое свойство для набора фишек. Для '
    'некоторых полок это свойство выполняется, для некоторых — нет. '
    'Твоя задача — раскрыть это свойство. Доступно 5 подсказок.'
)

TokenSequence = tuple[tuple[int, str], ...]


def _numbers(sequence: TokenSequence) -> tuple[int, ...]:
    return tuple(num for num, _color in sequence)


def _colors(sequence: TokenSequence) -> tuple[str, ...]:
    return tuple(color for _num, color in sequence)


def _odd_count_even(sequence: TokenSequence) -> bool:
    return sum(num % 2 == 1 for num in _numbers(sequence)) % 2 == 0


def _sum_divisible_by_three(sequence: TokenSequence) -> bool:
    return sum(_numbers(sequence)) % 3 == 0


def _sum_of_squares_divisible_by_four(sequence: TokenSequence) -> bool:
    return sum(num * num for num in _numbers(sequence)) % 4 == 0


def _max_minus_min_equals_length(sequence: TokenSequence) -> bool:
    numbers = _numbers(sequence)
    return max(numbers) - min(numbers) == len(numbers)


def _adjacent_coprime(sequence: TokenSequence) -> bool:
    numbers = _numbers(sequence)
    return all(math.gcd(first, second) == 1 for first, second in zip(numbers, numbers[1:], strict=False))


def _palindrome(sequence: TokenSequence) -> bool:
    numbers = _numbers(sequence)
    return numbers == numbers[::-1]


def _all_same_color(sequence: TokenSequence) -> bool:
    return len(set(_colors(sequence))) == 1


def _has_red(sequence: TokenSequence) -> bool:
    return 'R' in _colors(sequence)


def _exactly_two_colors(sequence: TokenSequence) -> bool:
    return len(set(_colors(sequence))) == 2


TOKEN_ATOMS: tuple[Atom, ...] = (
    Atom('odd_count_even', 3, _odd_count_even),
    Atom('sum_divisible_by_3', 3, _sum_divisible_by_three),
    Atom('palindrome', 3, _palindrome),
    Atom('all_same_color', 3, _all_same_color),
    Atom('has_red', 3, _has_red),
    Atom('sum_of_squares_divisible_by_4', 4, _sum_of_squares_divisible_by_four),
    Atom('max_minus_min_equals_length', 4, _max_minus_min_equals_length),
    Atom('adjacent_coprime', 4, _adjacent_coprime),
    Atom('exactly_two_colors', 4, _exactly_two_colors),
)


ATOM_DESCRIPTIONS = {
    'odd_count_even': 'число нечётных фишек чётно',
    'sum_divisible_by_3': 'сумма чисел кратна 3',
    'sum_of_squares_divisible_by_4': 'сумма квадратов чисел кратна 4',
    'max_minus_min_equals_length': 'максимум минус минимум равен длине полки',
    'palindrome': 'числа читаются одинаково слева направо и справа налево',
    'adjacent_coprime': 'числа любых двух соседних фишек взаимно просты',
    'all_same_color': 'все фишки одного цвета',
    'has_red': 'есть красная фишка',
    'exactly_two_colors': 'использовано ровно два цвета',
}


ATOM_HINT_CATEGORIES = {
    'odd_count_even': 'count',
    'sum_divisible_by_3': 'count',
    'sum_of_squares_divisible_by_4': 'count',
    'max_minus_min_equals_length': 'count',
    'palindrome': 'symmetry',
    'adjacent_coprime': 'neighbors',
    'all_same_color': 'color',
    'has_red': 'color',
    'exactly_two_colors': 'color',
}


def token_key(sequence: TokenSequence) -> Hashable:
    return sequence


def serialize_tokens(sequence: TokenSequence) -> list[dict[str, Any]]:
    return [{'num': num, 'color': color} for num, color in sequence]


def _random_sequence(rng: random.Random) -> TokenSequence:
    length = rng.randint(MIN_LENGTH, MAX_LENGTH)
    return tuple(
        (rng.randint(MIN_TOKEN_VALUE, MAX_TOKEN_VALUE), rng.choice(TOKEN_COLORS)) for _ in range(length)
    )


def _forced_sequences() -> tuple[TokenSequence, ...]:
    return (
        ((2, 'R'), (3, 'G'), (2, 'B')),
        ((1, 'R'), (1, 'R'), (1, 'R')),
        ((9, 'G'), (2, 'G'), (7, 'G'), (4, 'G')),
        ((1, 'B'), (2, 'B'), (3, 'B'), (2, 'B'), (1, 'B')),
        ((4, 'R'), (8, 'G'), (6, 'B'), (2, 'R')),
        ((5, 'G'), (7, 'B'), (5, 'G')),
        ((3, 'R'), (6, 'G'), (9, 'B'), (3, 'R'), (6, 'G'), (9, 'B'), (1, 'R')),
    )


def build_token_population() -> tuple[TokenSequence, ...]:
    rng = random.Random(_POPULATION_SEED)
    sequences: list[TokenSequence] = []
    seen: set[TokenSequence] = set()
    for sequence in _forced_sequences():
        if sequence not in seen:
            seen.add(sequence)
            sequences.append(sequence)
    while len(sequences) < POPULATION_SIZE:
        sequence = _random_sequence(rng)
        if sequence in seen:
            continue
        seen.add(sequence)
        sequences.append(sequence)
    return tuple(sequences)


def token_mutations(sequence: TokenSequence) -> tuple[TokenSequence, ...]:
    """Single-attribute changes of one token, in stable order."""

    mutations: list[TokenSequence] = []
    for index, (num, color) in enumerate(sequence):
        for candidate in range(MIN_TOKEN_VALUE, MAX_TOKEN_VALUE + 1):
            if candidate == num:
                continue
            mutated = list(sequence)
            mutated[index] = (candidate, color)
            mutations.append(tuple(mutated))
        for candidate_color in TOKEN_COLORS:
            if candidate_color == color:
                continue
            mutated = list(sequence)
            mutated[index] = (num, candidate_color)
            mutations.append(tuple(mutated))
    unique: dict[TokenSequence, TokenSequence] = {}
    for mutation in mutations:
        unique.setdefault(mutation, mutation)
    return tuple(unique.values())


class TokenUniverse:
    universe_version = UNIVERSE_VERSION
    dsl_version = DSL_VERSION

    def population(self) -> tuple[TokenSequence, ...]:
        return build_token_population()

    def atoms(self) -> tuple[Atom, ...]:
        return TOKEN_ATOMS

    def enumerate_rules(self) -> tuple[Rule, ...]:
        return enumerate_rules(TOKEN_ATOMS)

    def mutations(self, obj: TokenSequence) -> tuple[TokenSequence, ...]:
        return token_mutations(obj)

    def object_key(self, obj: TokenSequence) -> Hashable:
        return token_key(obj)


_UNIVERSE = TokenUniverse()


def generate_token_zendo_task(*, seed: int, difficulty: int) -> tuple[dict[str, Any], dict[str, Any]]:
    if isinstance(difficulty, bool) or not 1 <= difficulty <= 5:
        raise ValueError('token_zendo difficulty must be from 1 to 5')
    space, material = universe_material(random.Random(seed), difficulty, _UNIVERSE)
    cards = [*material.example_cards, *material.probe_cards, *material.target_cards]
    public = {
        'kind': PUBLIC_KIND,
        'family': FAMILY_KEY,
        'variant': 'classify_hidden_token_rule',
        'prompt': PROMPT,
        'cards': {card_id: serialize_tokens(sequence) for card_id, sequence in cards},
        'content': public_content(material),
        'interaction': {'mode': 'probe_then_answer', 'commands': ['/test <card_id>', '/answer <да/нет ...>']},
        'response_hint': ANSWER_RESPONSE_HINT,
        'dsl_version': DSL_VERSION,
    }
    private = private_state(
        material,
        identity={
            'family': FAMILY_KEY,
            'generator_version': GENERATOR_VERSION,
            'difficulty': difficulty,
            'dsl_version': DSL_VERSION,
            'universe_version': UNIVERSE_VERSION,
        },
        probes=card_probes(material, serialize_tokens),
        hint_category=rule_hint_category(space.rules[material.rule_index], ATOM_HINT_CATEGORIES),
    )
    return public, private


def _ai_context(public_state: State) -> State:
    roles, classifications = card_visibility(public_state)
    cards = public_state.get('cards') if isinstance(public_state.get('cards'), dict) else {}
    visible = [
        {
            'id': card_id,
            'role': roles[card_id],
            'classification': classifications.get(card_id),
            'tokens': cards.get(card_id) if isinstance(cards.get(card_id), list) else [],
        }
        for card_id in sorted(roles)
    ]
    return {'cards': visible, 'limits': probe_limits(public_state)}


FAMILY = zendo_family(
    key=FAMILY_KEY,
    version=GENERATOR_VERSION,
    card=FamilyCard(
        title='Zendo: фишки',
        description='Скрытое правило про последовательности числовых фишек трёх цветов.',
        weight=12,
        skin='tokens',
    ),
    generate=generate_token_zendo_task,
    universe=_UNIVERSE,
    atom_descriptions=ATOM_DESCRIPTIONS,
    ai_context=_ai_context,
    aliases=('token-zendo',),
)
