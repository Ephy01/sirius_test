"""token_zendo: hidden rules over sequences of numbered colour tokens.

The cheapest universe of the multiverse rollout — sequences of three to
seven tokens, each carrying ``num`` in 1..9 and ``color`` in {R, G, B}.
XOR hybrids of number and colour atoms come out of the shared rule
combinators for free.
"""

from __future__ import annotations

import math
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

FAMILY_KEY = "token_zendo"
GENERATOR_VERSION = "token-zendo-v1"
PUBLIC_KIND = "token_zendo"
UNIVERSE_VERSION = "token-universe-v1"
DSL_VERSION = "token-dsl-v1"

TOKEN_COLORS = ("R", "G", "B")
MIN_TOKEN_VALUE = 1
MAX_TOKEN_VALUE = 9
MIN_LENGTH = 3
MAX_LENGTH = 7
POPULATION_SIZE = 1200
_POPULATION_SEED = 0x70CE_2026

# One token is a (num, color) pair; a configuration is a tuple of tokens.
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
    return all(
        math.gcd(first, second) == 1
        for first, second in zip(numbers, numbers[1:], strict=False)
    )


def _palindrome(sequence: TokenSequence) -> bool:
    numbers = _numbers(sequence)
    return numbers == numbers[::-1]


def _all_same_color(sequence: TokenSequence) -> bool:
    return len(set(_colors(sequence))) == 1


def _has_red(sequence: TokenSequence) -> bool:
    return "R" in _colors(sequence)


def _exactly_two_colors(sequence: TokenSequence) -> bool:
    return len(set(_colors(sequence))) == 2


# Order is part of token-dsl-v1 and must only change with a new DSL version.
TOKEN_ATOMS: tuple[Atom, ...] = (
    Atom("odd_count_even", 3, _odd_count_even),
    Atom("sum_divisible_by_3", 3, _sum_divisible_by_three),
    Atom("palindrome", 3, _palindrome),
    Atom("all_same_color", 3, _all_same_color),
    Atom("has_red", 3, _has_red),
    Atom("sum_of_squares_divisible_by_4", 4, _sum_of_squares_divisible_by_four),
    Atom("max_minus_min_equals_length", 4, _max_minus_min_equals_length),
    Atom("adjacent_coprime", 4, _adjacent_coprime),
    Atom("exactly_two_colors", 4, _exactly_two_colors),
)


ATOM_DESCRIPTIONS = {
    "odd_count_even": "число нечётных фишек чётно",
    "sum_divisible_by_3": "сумма чисел кратна 3",
    "sum_of_squares_divisible_by_4": "сумма квадратов чисел кратна 4",
    "max_minus_min_equals_length": "максимум минус минимум равен длине полки",
    "palindrome": "числа читаются одинаково слева направо и справа налево",
    "adjacent_coprime": "числа любых двух соседних фишек взаимно просты",
    "all_same_color": "все фишки одного цвета",
    "has_red": "есть красная фишка",
    "exactly_two_colors": "использовано ровно два цвета",
}


ATOM_HINT_CATEGORIES = {
    "odd_count_even": "count",
    "sum_divisible_by_3": "count",
    "sum_of_squares_divisible_by_4": "count",
    "max_minus_min_equals_length": "count",
    "palindrome": "symmetry",
    "adjacent_coprime": "neighbors",
    "all_same_color": "color",
    "has_red": "color",
    "exactly_two_colors": "color",
}


def token_key(sequence: TokenSequence) -> Hashable:
    return sequence


def serialize_tokens(sequence: TokenSequence) -> list[dict[str, Any]]:
    return [{"num": num, "color": color} for num, color in sequence]


def deserialize_tokens(value: list[dict[str, Any]]) -> TokenSequence:
    return tuple(
        (int(item["num"]), str(item["color"]))
        for item in value
    )


def _random_sequence(rng: random.Random) -> TokenSequence:
    length = rng.randint(MIN_LENGTH, MAX_LENGTH)
    return tuple(
        (
            rng.randint(MIN_TOKEN_VALUE, MAX_TOKEN_VALUE),
            rng.choice(TOKEN_COLORS),
        )
        for _ in range(length)
    )


def _forced_sequences() -> tuple[TokenSequence, ...]:
    return (
        ((2, "R"), (3, "G"), (2, "B")),
        ((1, "R"), (1, "R"), (1, "R")),
        ((9, "G"), (2, "G"), (7, "G"), (4, "G")),
        ((1, "B"), (2, "B"), (3, "B"), (2, "B"), (1, "B")),
        ((4, "R"), (8, "G"), (6, "B"), (2, "R")),
        ((5, "G"), (7, "B"), (5, "G")),
        ((3, "R"), (6, "G"), (9, "B"), (3, "R"), (6, "G"), (9, "B"), (1, "R")),
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

    def render_payload(self, obj: TokenSequence) -> dict[str, Any]:
        return {"tokens": serialize_tokens(obj)}


_UNIVERSE = TokenUniverse()


def generate_token_zendo_task(
    *,
    seed: int,
    difficulty: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if isinstance(difficulty, bool) or not 1 <= difficulty <= 5:
        raise ValueError("token_zendo difficulty must be from 1 to 5")
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
        mutations=token_mutations,
        object_key=token_key,
    )

    example_cards = [
        (f"E{index:02d}", sequence)
        for index, sequence in enumerate(material.examples, start=1)
    ]
    probe_cards = [
        (f"P{index:02d}", sequence)
        for index, sequence in enumerate(material.probes, start=1)
    ]
    target_cards = [
        (f"T{index:02d}", sequence)
        for index, sequence in enumerate(material.targets, start=1)
    ]
    public = {
        "kind": PUBLIC_KIND,
        "family": FAMILY_KEY,
        "variant": "classify_hidden_token_rule",
        "prompt": (
            "Рассмотрите предложенные полки с фишками. Было загадано "
            "некоторое утверждение: одни полки ему соответствуют, другие — "
            "нет. Предположите, что это за утверждение, и классифицируйте "
            "восемь целевых полок по порядку. Перед ответом можно опробовать "
            "несколько полок — доступно 5 проб."
        ),
        "cards": {
            card_id: serialize_tokens(sequence)
            for card_id, sequence in [
                *example_cards,
                *probe_cards,
                *target_cards,
            ]
        },
        "content": {
            "examples": [
                {
                    "card_id": card_id,
                    "classification": "positive" if label else "negative",
                }
                for (card_id, _sequence), label in zip(
                    example_cards,
                    material.example_labels,
                    strict=True,
                )
            ],
            "probe_cards": [
                {"card_id": card_id, "used": False}
                for card_id, _sequence in probe_cards
            ],
            "targets": [
                {"card_id": card_id, "position": index}
                for index, (card_id, _sequence) in enumerate(
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
            card_id: serialize_tokens(sequence)
            for card_id, sequence in probe_cards
        },
        "probe_truth_masks": {
            card_id: truth_mask
            for (card_id, _sequence), truth_mask in zip(
                probe_cards,
                material.probe_masks,
                strict=True,
            )
        },
        "used_probe_card_ids": [],
        "probe_budget": PROBE_BUDGET,
        "probes_remaining": PROBE_BUDGET,
        "target_card_ids": [
            card_id for card_id, _sequence in target_cards
        ],
        "target_answers": material.target_answers,
        "hint_category": rule_hint_category(
            space.rules[material.rule_index],
            ATOM_HINT_CATEGORIES,
        ),
    }
    return public, private


def transition_token_zendo_hint(
    *,
    public_state: dict[str, Any],
    private_state: dict[str, Any],
):
    return transition_zendo_hint(
        public_state=public_state,
        private_state=private_state,
        category=str(private_state["hint_category"]),
    )


def transition_token_zendo_probe(
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


def evaluate_token_zendo_answer(
    *,
    answer: str,
    private_state: dict[str, Any],
) -> dict[str, Any]:
    return evaluate_zendo_answer(answer=answer, private_state=private_state)


__all__ = [
    "DSL_VERSION",
    "FAMILY_KEY",
    "GENERATOR_VERSION",
    "PUBLIC_KIND",
    "TOKEN_ATOMS",
    "TOKEN_COLORS",
    "TokenUniverse",
    "UNIVERSE_VERSION",
    "build_token_population",
    "evaluate_token_zendo_answer",
    "generate_token_zendo_task",
    "token_mutations",
    "transition_token_zendo_hint",
    "transition_token_zendo_probe",
]
