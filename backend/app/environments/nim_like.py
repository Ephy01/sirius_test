"""One-move impartial-game tasks for the ``nim_like`` family.

The generator and solver are intentionally independent from HTTP and storage.
Normal play is solved with Sprague--Grundy values.  Misère play uses the same
Grundy telemetry, but its winning status is computed by exact backward
induction because a normal-play nim-sum is not a valid misère solver in
general subtraction games.
"""

from __future__ import annotations

import hashlib
import random
import re
from dataclasses import dataclass
from functools import lru_cache
from itertools import product
from typing import Any, Callable, Iterable, Literal

FAMILY_KEY = "nim_like"
GENERATOR_VERSION = "nim-like-v1"
PUBLIC_KIND = "counters"

NORMAL_MODE = "normal"
MISERE_MODE = "misere"
MODES = (NORMAL_MODE, MISERE_MODE)

MAX_GENERATION_ATTEMPTS = 96

Mode = Literal["normal", "misere"]
HeapState = tuple[int, ...]
RuleSets = tuple[tuple[int, ...], ...]

MOVE_PATTERN = re.compile(
    r"^\s*(?:take|взять)\s+(\d+)\s+(\d+)\s*$",
    re.IGNORECASE,
)
LOSING_ANSWERS = {
    "losing",
    "losing position",
    "проигрышная",
    "проигрышная позиция",
}


@dataclass(frozen=True, order=True)
class NimMove:
    """A one-based heap index and a positive number of removed counters."""

    heap: int
    count: int

    def as_dict(self) -> dict[str, int]:
        return {"heap": self.heap, "count": self.count}


@dataclass(frozen=True)
class NimSolution:
    mode: str
    winning: bool
    legal_moves: tuple[NimMove, ...]
    winning_moves: tuple[NimMove, ...]
    grundy_values: tuple[int, ...]
    nim_sum: int


@dataclass(frozen=True)
class ParsedNimAnswer:
    kind: Literal["move", "losing", "invalid"]
    move: NimMove | None
    normalized: str


def _difficulty(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 5:
        raise ValueError("Nim-like difficulty must be an integer from 1 to 5")
    return value


def _mode(value: str) -> str:
    normalized = value.strip().casefold()
    if normalized not in MODES:
        raise ValueError("Nim-like mode must be 'normal' or 'misere'")
    return normalized


def _rng(seed: int, mode: str) -> random.Random:
    digest = hashlib.sha256(
        f"{GENERATOR_VERSION}:{mode}:{seed}".encode("ascii")
    ).digest()
    return random.Random(int.from_bytes(digest[:16], "big"))


def _desired_winning(seed: int, mode: str) -> bool:
    # Exactly 600 winning and 400 losing tasks in every 1000 consecutive
    # seeds.  The mode offset changes their locations, not their proportion.
    offset = 0 if mode == NORMAL_MODE else 2
    return (seed + offset) % 5 < 3


def mex(values: Iterable[int]) -> int:
    observed = set(values)
    candidate = 0
    while candidate in observed:
        candidate += 1
    return candidate


@lru_cache(maxsize=8192)
def _grundy_table(max_heap: int, takes: tuple[int, ...]) -> tuple[int, ...]:
    values = [0]
    for size in range(1, max_heap + 1):
        values.append(
            mex(
                values[size - take]
                for take in takes
                if take <= size
            )
        )
    return tuple(values)


def grundy_value(size: int, takes: Iterable[int]) -> int:
    if isinstance(size, bool) or not isinstance(size, int) or size < 0:
        raise ValueError("Heap size must be a non-negative integer")
    normalized = tuple(sorted({int(take) for take in takes if int(take) > 0}))
    if not normalized:
        raise ValueError("A subtraction set must contain a positive integer")
    return _grundy_table(size, normalized)[size]


def _normalize_position(
    heaps: Iterable[int],
    rule_sets: Iterable[Iterable[int]],
) -> tuple[HeapState, RuleSets]:
    state = tuple(int(size) for size in heaps)
    rules = tuple(
        tuple(sorted({int(take) for take in takes if int(take) > 0}))
        for takes in rule_sets
    )
    if not state or len(state) > 4:
        raise ValueError("A nim-like position must contain from one to four heaps")
    if any(size < 0 for size in state):
        raise ValueError("Heap sizes must be non-negative")
    if len(rules) != len(state) or any(not takes for takes in rules):
        raise ValueError("Every heap must have a non-empty subtraction set")
    return state, rules


def legal_moves(
    heaps: Iterable[int],
    rule_sets: Iterable[Iterable[int]],
) -> tuple[NimMove, ...]:
    state, rules = _normalize_position(heaps, rule_sets)
    return tuple(
        NimMove(heap=index + 1, count=take)
        for index, (size, takes) in enumerate(zip(state, rules))
        for take in takes
        if take <= size
    )


def _legal_moves_fast(state: HeapState, rules: RuleSets) -> tuple[NimMove, ...]:
    return tuple(
        NimMove(heap=index + 1, count=take)
        for index, (size, takes) in enumerate(zip(state, rules))
        for take in takes
        if take <= size
    )


def _apply_move_fast(
    state: HeapState,
    move: NimMove,
    rules: RuleSets,
) -> HeapState | None:
    index = move.heap - 1
    if not 0 <= index < len(state):
        return None
    if move.count not in rules[index] or move.count > state[index]:
        return None
    return (
        *state[:index],
        state[index] - move.count,
        *state[index + 1 :],
    )


def apply_nim_move(
    heaps: Iterable[int],
    move: NimMove,
    rule_sets: Iterable[Iterable[int]],
) -> HeapState | None:
    state, rules = _normalize_position(heaps, rule_sets)
    index = move.heap - 1
    if not 0 <= index < len(state):
        return None
    if move.count not in rules[index] or move.count > state[index]:
        return None
    result = list(state)
    result[index] -= move.count
    return tuple(result)


def position_grundy(
    heaps: Iterable[int],
    rule_sets: Iterable[Iterable[int]],
) -> tuple[tuple[int, ...], int]:
    state, rules = _normalize_position(heaps, rule_sets)
    values = tuple(
        grundy_value(size, takes)
        for size, takes in zip(state, rules)
    )
    nim_sum = 0
    for value in values:
        nim_sum ^= value
    return values, nim_sum


def _outcome_solver(
    rule_sets: RuleSets,
    mode: str,
) -> Callable[[HeapState], bool]:
    normalized_mode = _mode(mode)

    def winning(state: HeapState) -> bool:
        return _winning_cached(state, rule_sets, normalized_mode)

    return winning


@lru_cache(maxsize=250_000)
def _winning_cached(
    state: HeapState,
    rule_sets: RuleSets,
    mode: str,
) -> bool:
    moves = _legal_moves_fast(state, rule_sets)
    if not moves:
        # In misère play the player who took the last counter loses, so a
        # player handed a position with no legal move is the winner.
        return mode == MISERE_MODE
    return any(
        not _winning_cached(
            _apply_move_fast(state, move, rule_sets) or state,
            rule_sets,
            mode,
        )
        for move in moves
    )


def solve_nim_position(
    *,
    heaps: Iterable[int],
    rule_sets: Iterable[Iterable[int]],
    mode: str,
) -> NimSolution:
    state, rules = _normalize_position(heaps, rule_sets)
    normalized_mode = _mode(mode)
    moves = legal_moves(state, rules)
    grundy_values, nim_sum = position_grundy(state, rules)

    if normalized_mode == NORMAL_MODE:
        winning = nim_sum != 0
        winning_moves = tuple(
            move
            for move in moves
            if position_grundy(
                apply_nim_move(state, move, rules) or state,
                rules,
            )[1]
            == 0
        )
    else:
        outcome = _outcome_solver(rules, normalized_mode)
        winning = outcome(state)
        winning_moves = tuple(
            move
            for move in moves
            if not outcome(apply_nim_move(state, move, rules) or state)
        )

    if winning != bool(winning_moves):
        raise RuntimeError("Exact outcome and winning-move set disagree")
    return NimSolution(
        mode=normalized_mode,
        winning=winning,
        legal_moves=moves,
        winning_moves=winning_moves,
        grundy_values=grundy_values,
        nim_sum=nim_sum,
    )


def _heap_count(rng: random.Random, difficulty: int) -> int:
    minimum = 1 if difficulty == 1 else min(4, (difficulty + 1) // 2)
    maximum = min(4, 1 + (difficulty + 1) // 2)
    return rng.randint(minimum, maximum)


def _sample_subtraction_set(
    rng: random.Random,
    *,
    difficulty: int,
) -> tuple[int, ...]:
    upper = min(7, 2 + difficulty)
    count = min(upper, 2 + difficulty // 2)
    # Keeping 1 in most sets makes the rules readable while the remaining
    # random gaps control the Grundy period.
    selected = {1}
    selected.update(rng.sample(range(2, upper + 1), k=count - 1))
    return tuple(sorted(selected))


def _sample_rules(
    rng: random.Random,
    *,
    difficulty: int,
    heap_count: int,
) -> tuple[RuleSets, str]:
    per_heap = difficulty >= 3 and rng.random() < 0.55
    if not per_heap:
        global_set = _sample_subtraction_set(rng, difficulty=difficulty)
        return tuple(global_set for _ in range(heap_count)), "global"
    return (
        tuple(
            _sample_subtraction_set(rng, difficulty=difficulty)
            for _ in range(heap_count)
        ),
        "per_heap",
    )


def _find_position(
    *,
    rng: random.Random,
    difficulty: int,
    heap_count: int,
    rule_sets: RuleSets,
    mode: str,
    desired_winning: bool,
) -> tuple[HeapState, NimSolution] | None:
    maximum = 6 + difficulty
    if mode == MISERE_MODE:
        outcome = _outcome_solver(rule_sets, mode)
    else:
        outcome = None

    def classify(state: HeapState) -> bool:
        if outcome is not None:
            return outcome(state)
        return position_grundy(state, rule_sets)[1] != 0

    random_candidates = [
        tuple(rng.randint(1, maximum) for _ in range(heap_count))
        for _ in range(160)
    ]
    for state in random_candidates:
        if len(legal_moves(state, rule_sets)) < 2:
            continue
        if classify(state) != desired_winning:
            continue
        solution = solve_nim_position(
            heaps=state,
            rule_sets=rule_sets,
            mode=mode,
        )
        return state, solution

    # Deterministic exhaustive fallback for unusually sparse losing classes.
    all_candidates = product(range(1, maximum + 1), repeat=heap_count)
    matches = [
        state
        for state in all_candidates
        if len(legal_moves(state, rule_sets)) >= 2
        and classify(state) == desired_winning
    ]
    if not matches:
        return None
    state = rng.choice(matches)
    return state, solve_nim_position(
        heaps=state,
        rule_sets=rule_sets,
        mode=mode,
    )


def generate_nim_like_task(
    *,
    seed: int,
    difficulty: int,
    mode: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Generate a deterministic one-decision impartial-game task."""

    difficulty = _difficulty(difficulty)
    selected_mode = _mode(
        mode if mode is not None else MODES[(seed // 5) % len(MODES)]
    )
    rng = _rng(seed, selected_mode)
    desired_winning = _desired_winning(seed, selected_mode)

    generated: tuple[
        HeapState,
        RuleSets,
        str,
        NimSolution,
    ] | None = None
    for _attempt in range(MAX_GENERATION_ATTEMPTS):
        heap_count = _heap_count(rng, difficulty)
        rule_sets, rule_kind = _sample_rules(
            rng,
            difficulty=difficulty,
            heap_count=heap_count,
        )
        found = _find_position(
            rng=rng,
            difficulty=difficulty,
            heap_count=heap_count,
            rule_sets=rule_sets,
            mode=selected_mode,
            desired_winning=desired_winning,
        )
        if found is None:
            continue
        heaps, solution = found
        generated = heaps, rule_sets, rule_kind, solution
        break
    if generated is None:
        raise RuntimeError("Unable to generate a non-degenerate nim-like task")

    heaps, rule_sets, rule_kind, solution = generated
    public_rules: dict[str, Any]
    if rule_kind == "global":
        public_rules = {
            "kind": "global",
            "take": list(rule_sets[0]),
        }
    else:
        public_rules = {
            "kind": "per_heap",
            "by_heap": [
                {"heap": index + 1, "take": list(takes)}
                for index, takes in enumerate(rule_sets)
            ],
        }
    mode_text = (
        "Последний допустимый ход выигрывает."
        if selected_mode == NORMAL_MODE
        else "Игрок, сделавший последний допустимый ход, проигрывает."
    )
    public_state: dict[str, Any] = {
        "kind": PUBLIC_KIND,
        "sub_kind": "subtraction_game",
        "prompt": (
            "Перед вами несколько куч фишек. Сделайте один решающий ход, "
            "после которого позиция соперника станет проигрышной, либо "
            "укажите, что текущая позиция уже проигрышная. "
            f"{mode_text}"
        ),
        "mode": selected_mode,
        "heaps": list(heaps),
        "rules": public_rules,
        "response_hint": "Ответ: take <номер кучи> <число> или «проигрышная».",
    }
    private_state: dict[str, Any] = {
        "family": FAMILY_KEY,
        "generator_version": GENERATOR_VERSION,
        "difficulty": difficulty,
        "mode": selected_mode,
        "heaps": list(heaps),
        "rule_sets": [list(takes) for takes in rule_sets],
        "winning": solution.winning,
        "legal_moves": [move.as_dict() for move in solution.legal_moves],
        "winning_moves": [move.as_dict() for move in solution.winning_moves],
        "grundy_values": list(solution.grundy_values),
        "nim_sum": solution.nim_sum,
    }
    return public_state, private_state


def parse_nim_answer(answer: str) -> ParsedNimAnswer:
    normalized = " ".join(answer.strip().casefold().split())
    if normalized in LOSING_ANSWERS:
        return ParsedNimAnswer(
            kind="losing",
            move=None,
            normalized="losing",
        )
    matched = MOVE_PATTERN.fullmatch(answer)
    if matched is None:
        return ParsedNimAnswer(
            kind="invalid",
            move=None,
            normalized=normalized,
        )
    move = NimMove(heap=int(matched.group(1)), count=int(matched.group(2)))
    return ParsedNimAnswer(
        kind="move",
        move=move,
        normalized=f"take {move.heap} {move.count}",
    )


def _private_position(
    private_state: dict[str, Any],
) -> tuple[HeapState, RuleSets, str]:
    state, rules = _normalize_position(
        private_state["heaps"],
        private_state["rule_sets"],
    )
    return state, rules, _mode(str(private_state["mode"]))


def _telemetry_base(private_state: dict[str, Any]) -> dict[str, Any]:
    return {
        "family": FAMILY_KEY,
        "generator_version": GENERATOR_VERSION,
        "difficulty": int(private_state["difficulty"]),
        "mode": str(private_state["mode"]),
        "position_winning": bool(private_state["winning"]),
    }


def _grundy_regret(
    *,
    state: HeapState,
    rules: RuleSets,
    selected_result: HeapState,
) -> tuple[int, int]:
    """Return selected-minus-best resulting Grundy value for a legal move."""

    resulting_grundies = [
        position_grundy(result, rules)[1]
        for move in legal_moves(state, rules)
        if (result := apply_nim_move(state, move, rules)) is not None
    ]
    selected_grundy = position_grundy(selected_result, rules)[1]
    best_grundy = min(resulting_grundies)
    return max(0, selected_grundy - best_grundy), best_grundy


def evaluate_nim_like_answer(
    *,
    answer: str,
    private_state: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate a move or a losing-position declaration.

    In normal play, ``regret`` is the exact difference between the Grundy value
    after the selected move and the smallest value available in the position.
    In misère play the normal-play Grundy number is only a diagnostic, so a
    winning move has zero regret and a losing move has regret of at least one.
    """

    parsed = parse_nim_answer(answer)
    state, rules, mode = _private_position(private_state)
    solution = solve_nim_position(heaps=state, rule_sets=rules, mode=mode)
    base = _telemetry_base(private_state)

    common = {
        **base,
        "answer_kind": parsed.kind,
        "normalized_answer": parsed.normalized,
        "legal": False,
        "correct": False,
        "score": 0.0,
        "continuous_score": 0.0,
        "regret": 1.0,
        "best_resulting_grundy": None,
        "resulting_grundy": None,
        "resulting_position_winning": None,
        "false_losing_claim": False,
        "freeze_seconds": 0,
        "should_finalize": False,
        "evidence": 0,
    }
    if parsed.kind == "invalid":
        return {
            **common,
            "reason": "invalid_answer",
            "feedback": "Используйте формат take <куча> <число> или «проигрышная».",
        }
    if parsed.kind == "losing":
        correct = not solution.winning
        return {
            **common,
            "legal": True,
            "correct": correct,
            "score": 1.0 if correct else 0.0,
            "continuous_score": 1.0 if correct else 0.0,
            "regret": 0.0 if correct else 1.0,
            "false_losing_claim": not correct,
            "freeze_seconds": 0 if correct else 15,
            "should_finalize": correct,
            "evidence": 1 if correct else -1,
            "reason": "correct_losing" if correct else "false_losing",
            "feedback": (
                "Ответ принят."
                if correct
                else "Ответ не принят. Повторите попытку через 15 секунд."
            ),
        }

    move = parsed.move
    if move is None:
        raise RuntimeError("Parsed move answer must contain a move")
    result = apply_nim_move(state, move, rules)
    if result is None:
        return {
            **common,
            "reason": "illegal_move",
            "feedback": "Такой ход не разрешён условием.",
        }

    result_solution = solve_nim_position(
        heaps=result,
        rule_sets=rules,
        mode=mode,
    )
    resulting_grundy = position_grundy(result, rules)[1]
    grundy_gap, best_resulting_grundy = _grundy_regret(
        state=state,
        rules=rules,
        selected_result=result,
    )
    correct = solution.winning and not result_solution.winning
    regret = (
        grundy_gap
        if mode == NORMAL_MODE
        else 0
        if correct
        else max(1, grundy_gap)
    )
    if mode == MISERE_MODE and correct:
        best_resulting_grundy = resulting_grundy
    return {
        **common,
        "legal": True,
        "correct": correct,
        "score": 1.0 if correct else 0.0,
        "continuous_score": 1.0 if correct else 0.0,
        "regret": float(regret),
        "best_resulting_grundy": best_resulting_grundy,
        "resulting_grundy": resulting_grundy,
        "resulting_position_winning": result_solution.winning,
        "selected_move": move.as_dict(),
        "should_finalize": True,
        "evidence": 1 if correct else -1,
        "reason": "winning_move" if correct else "non_winning_move",
        "feedback": "Ответ принят." if correct else "Ход не является решающим.",
    }


def validate_nim_like_instance(
    *,
    public_state: dict[str, Any],
    private_state: dict[str, Any],
) -> bool:
    """Recompute the complete one-move certificate stored in private state."""

    if public_state.get("kind") != PUBLIC_KIND:
        return False
    if public_state.get("heaps") != private_state.get("heaps"):
        return False
    if public_state.get("mode") != private_state.get("mode"):
        return False
    state, rules, mode = _private_position(private_state)
    public_rules = public_state.get("rules") or {}
    if public_rules.get("kind") == "global":
        public_rule_sets = tuple(
            tuple(int(take) for take in public_rules.get("take", []))
            for _ in state
        )
    elif public_rules.get("kind") == "per_heap":
        ordered = sorted(
            public_rules.get("by_heap", []),
            key=lambda item: int(item.get("heap", 0)),
        )
        public_rule_sets = tuple(
            tuple(int(take) for take in item.get("take", []))
            for item in ordered
        )
    else:
        return False
    if public_rule_sets != rules:
        return False
    solution = solve_nim_position(heaps=state, rule_sets=rules, mode=mode)
    stored_legal = {
        (int(move["heap"]), int(move["count"]))
        for move in private_state.get("legal_moves", [])
    }
    stored_winning = {
        (int(move["heap"]), int(move["count"]))
        for move in private_state.get("winning_moves", [])
    }
    return (
        len(solution.legal_moves) >= 2
        and solution.winning == private_state.get("winning")
        and list(solution.grundy_values) == private_state.get("grundy_values")
        and solution.nim_sum == private_state.get("nim_sum")
        and {(move.heap, move.count) for move in solution.legal_moves}
        == stored_legal
        and {(move.heap, move.count) for move in solution.winning_moves}
        == stored_winning
        and solution.winning == bool(solution.winning_moves)
    )
