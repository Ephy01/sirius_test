"""hidden_wiring: recover a hidden GF(2) wiring through paired button chords.

A panel has L lamps and B buttons. The wiring is a matrix M over GF(2):
column j lists which lamps button j toggles. Buttons only fire in chords
of two (UI legend: «кнопки срабатывают только парами»), so one probe
reveals the XOR of two columns.

Design note, for the record of this decision: with single presses one
probe would expose a full column of M and the mechanic trivializes into
B lookups. Chords turn recovery into solving a linear system over GF(2)
— the hypothesis space is an affine subspace of matrices consistent with
the observed chords, its dimension in bits is the exact entropy H, and
ΔH per probe is computed from the rank of the chord-indicator span. That
per-probe ΔH is the measurable reasoning signal.

The first chord is a free training probe (highlighted in the UI); the
budget counts from the second chord onwards.
"""

from __future__ import annotations

import itertools
import random
from collections import deque
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

FAMILY_KEY = "hidden_wiring"
GENERATOR_VERSION = "hidden-wiring-v1"
PUBLIC_KIND = "hidden_wiring"

CHORD_BUDGET = 8
EXAM_CHORD_COUNT = 3
REACH_VARIANT = "reach_target"
PREDICT_VARIANT = "predict_chords"

# Fixed hint dictionary for the wiring panel (stage C.2): a structural
# category of the hidden matrix, recorded in private at generation time.
HINT_SCORE_MULTIPLIER = 0.7
WIRING_HINT_CATEGORIES = {
    "sparse_wiring": "каждая кнопка переключает не больше двух ламп",
    "dense_wiring": "есть кнопка, переключающая три и более ламп",
}


def _chord_id(first: int, second: int) -> str:
    return f"b{first + 1}+b{second + 1}"


def _lamp_list(value: int, lamp_count: int) -> list[int]:
    return [(value >> index) & 1 for index in range(lamp_count)]


def _span_rank(vectors: list[int]) -> int:
    basis: list[int] = []
    for vector in vectors:
        reduced = vector
        for base in basis:
            reduced = min(reduced, reduced ^ base)
        if reduced:
            basis.append(reduced)
            basis.sort(reverse=True)
    return len(basis)


def _in_span(vector: int, vectors: list[int]) -> bool:
    return _span_rank([*vectors, vector]) == _span_rank(vectors)


def _panel_shape(rng: random.Random, difficulty: int) -> tuple[int, int]:
    if difficulty <= 2:
        return 4, 4
    if difficulty == 3:
        return 5, rng.choice((4, 5))
    return 6, 5


def _sample_matrix(
    rng: random.Random,
    lamp_count: int,
    button_count: int,
) -> list[int] | None:
    """Sample non-degenerate columns: no zero and no duplicate columns."""

    columns = [
        rng.randrange(1, 1 << lamp_count)
        for _ in range(button_count)
    ]
    if len(set(columns)) != button_count:
        return None
    return columns


def _chord_effects(
    columns: list[int],
) -> dict[str, int]:
    return {
        _chord_id(first, second): columns[first] ^ columns[second]
        for first, second in itertools.combinations(range(len(columns)), 2)
    }


def _chord_indicator(chord_id: str, button_count: int) -> int:
    first_token, second_token = chord_id.split("+")
    first = int(first_token[1:]) - 1
    second = int(second_token[1:]) - 1
    return (1 << first) | (1 << second)


def _reach_certificate(
    *,
    effects: dict[str, int],
    allowed_chords: list[str],
    start: int,
    target: int,
) -> list[str] | None:
    """Shortest chord sequence from ``start`` to ``target`` (BFS)."""

    if start == target:
        return []
    parents: dict[int, tuple[int, str]] = {start: (start, "")}
    queue: deque[int] = deque([start])
    while queue:
        current = queue.popleft()
        for chord in allowed_chords:
            nxt = current ^ effects[chord]
            if nxt in parents:
                continue
            parents[nxt] = (current, chord)
            if nxt == target:
                sequence: list[str] = []
                cursor = nxt
                while cursor != start:
                    previous, used = parents[cursor]
                    sequence.append(used)
                    cursor = previous
                sequence.reverse()
                return sequence
            queue.append(nxt)
    return None


def generate_hidden_wiring_task(
    *,
    seed: int,
    difficulty: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if isinstance(difficulty, bool) or not 1 <= difficulty <= 5:
        raise ValueError("hidden_wiring difficulty must be from 1 to 5")
    rng = random.Random(seed)
    lamp_count, button_count = _panel_shape(rng, difficulty)
    if difficulty <= 2:
        variant = REACH_VARIANT
    elif difficulty >= 4:
        variant = PREDICT_VARIANT
    else:
        variant = rng.choice((REACH_VARIANT, PREDICT_VARIANT))

    for _ in range(512):
        columns = _sample_matrix(rng, lamp_count, button_count)
        if columns is None:
            continue
        effects = _chord_effects(columns)
        # Degenerate wirings where a chord does nothing are rejected with
        # the duplicate-column filter above, but keep the guard explicit.
        if any(effect == 0 for effect in effects.values()):
            continue
        all_chords = sorted(effects)
        start = rng.randrange(1 << lamp_count)

        if variant == PREDICT_VARIANT:
            exam_chords = sorted(rng.sample(all_chords, EXAM_CHORD_COUNT))
            allowed_chords = [
                chord for chord in all_chords if chord not in exam_chords
            ]
            allowed_indicators = [
                _chord_indicator(chord, button_count)
                for chord in allowed_chords
            ]
            # The exam must be solvable from probes alone: every exam
            # chord's indicator lies in the span of the allowed probes.
            if not all(
                _in_span(
                    _chord_indicator(chord, button_count),
                    allowed_indicators,
                )
                for chord in exam_chords
            ):
                continue
            target = None
            certificate: list[str] | None = None
        else:
            exam_chords = []
            allowed_chords = all_chords
            # The target is a XOR of chord effects by construction, so
            # variant (а) is always solvable; keep the shortest witness.
            chord_sample = rng.sample(
                all_chords,
                rng.randint(2, min(4, len(all_chords))),
            )
            delta = 0
            for chord in chord_sample:
                delta ^= effects[chord]
            if delta == 0:
                continue
            target = start ^ delta
            certificate = _reach_certificate(
                effects=effects,
                allowed_chords=allowed_chords,
                start=start,
                target=target,
            )
            if not certificate or len(certificate) > CHORD_BUDGET:
                continue

        ops = [
            {
                "id": chord,
                "label": (
                    "Кнопки "
                    f"{chord.split('+')[0][1:]} и {chord.split('+')[1][1:]}"
                ),
            }
            for chord in allowed_chords
        ]
        prompt_intro = (
            "Проводка панели скрыта: неизвестно, какая кнопка какие лампы "
            "переключает. Кнопки срабатывают только парами. "
        )
        if variant == REACH_VARIANT:
            prompt = prompt_intro + (
                "Приведите лампы к целевому узору комбинациями из двух кнопок."
            )
            response_hint = (
                "Нажимайте комбинации: /op b1+b2. Панель завершится "
                "сама, когда лампы совпадут с целью."
            )
        else:
            prompt = prompt_intro + (
                "Изучите проводку пробами, затем предскажите, какие лампы "
                "переключит каждая из трёх экзаменационных комбинаций."
            )
            response_hint = (
                "Пробы: /op b1+b2. Ответ — три битовые строки по лампам "
                f"(1 — переключится), например: /answer {'1' * lamp_count} "
                f"{'0' * lamp_count} {'1' + '0' * (lamp_count - 1)}."
            )

        public: dict[str, Any] = {
            "kind": PUBLIC_KIND,
            "family": FAMILY_KEY,
            "variant": variant,
            "prompt": prompt,
            "legend": "Кнопки срабатывают только парами.",
            "lamp_count": lamp_count,
            "button_count": button_count,
            "ops": ops,
            "start": _lamp_list(start, lamp_count),
            "current": _lamp_list(start, lamp_count),
            "chord_budget": CHORD_BUDGET,
            "chords_remaining": CHORD_BUDGET,
            "free_training_probe": True,
            "observations": [],
            "response_hint": response_hint,
        }
        if variant == REACH_VARIANT:
            assert target is not None
            public["target"] = _lamp_list(target, lamp_count)
        else:
            public["exam_chords"] = [
                {
                    "id": chord,
                    "label": (
                        "Кнопки "
                        f"{chord.split('+')[0][1:]} и "
                        f"{chord.split('+')[1][1:]}"
                    ),
                }
                for chord in exam_chords
            ]

        hint_key = (
            "dense_wiring"
            if any(column.bit_count() >= 3 for column in columns)
            else "sparse_wiring"
        )
        private: dict[str, Any] = {
            "family": FAMILY_KEY,
            "generator_version": GENERATOR_VERSION,
            "difficulty": difficulty,
            "variant": variant,
            "hint_category": WIRING_HINT_CATEGORIES[hint_key],
            "lamp_count": lamp_count,
            "button_count": button_count,
            "columns": columns,
            "chord_effects": effects,
            "allowed_chords": allowed_chords,
            "start": start,
            "current": start,
            "chord_budget": CHORD_BUDGET,
            "chords_used": 0,
            "observed_chords": [],
            "processed_actions": {},
        }
        if variant == REACH_VARIANT:
            private["target"] = target
            private["certificate"] = certificate
            private["min_len"] = len(certificate or [])
        else:
            private["exam_chords"] = exam_chords
            private["exam_effects"] = [
                effects[chord] for chord in exam_chords
            ]
        return public, private
    raise RuntimeError(
        f"Unable to generate hidden_wiring at difficulty {difficulty}"
    )


@dataclass(frozen=True)
class WiringTransition:
    public_state: dict[str, Any]
    private_state: dict[str, Any]
    accepted: bool
    completed: bool
    reason: str
    message: str
    normalized_input: str
    evaluation_state: dict[str, Any] | None


def _entropy_bits(private: dict[str, Any]) -> int:
    """Exact hypothesis entropy: L·(B−1−rank) bits.

    Chords only ever reveal sums of column pairs, so the recoverable
    knowledge lives in the even-weight indicator space of dimension B−1;
    every independent chord removes L bits.
    """

    lamp_count = int(private["lamp_count"])
    button_count = int(private["button_count"])
    indicators = [
        _chord_indicator(chord, button_count)
        for chord in private.get("observed_chords", [])
    ]
    rank = _span_rank(indicators)
    return lamp_count * (button_count - 1 - rank)


def transition_hidden_wiring_chord(
    *,
    op_id: str,
    public_state: dict[str, Any],
    private_state: dict[str, Any],
    client_action_id: str,
) -> WiringTransition:
    next_public = deepcopy(public_state)
    next_private = deepcopy(private_state)
    normalized = op_id.strip().lower().replace(" ", "")
    processed = next_private.setdefault("processed_actions", {})
    stored = processed.get(client_action_id)
    if stored is not None:
        if stored.get("normalized_input") != normalized:
            raise ValueError(
                f"client_action_id {client_action_id!r} was already used "
                "with a different chord"
            )
        return WiringTransition(
            public_state=next_public,
            private_state=next_private,
            accepted=bool(stored.get("accepted")),
            completed=bool(stored.get("completed")),
            reason=str(stored.get("reason")),
            message=str(stored.get("message")),
            normalized_input=normalized,
            evaluation_state=stored.get("telemetry"),
        )

    def reject(reason: str, message: str) -> WiringTransition:
        processed[client_action_id] = {
            "normalized_input": normalized,
            "accepted": False,
            "completed": False,
            "reason": reason,
            "message": message,
            "telemetry": None,
        }
        return WiringTransition(
            public_state=next_public,
            private_state=next_private,
            accepted=False,
            completed=False,
            reason=reason,
            message=message,
            normalized_input=normalized,
            evaluation_state=None,
        )

    effects = next_private["chord_effects"]
    allowed = [str(chord) for chord in next_private["allowed_chords"]]
    if normalized not in allowed:
        return reject(
            "unknown_chord",
            "Такой комбинации нет на панели (или она экзаменационная).",
        )
    chords_used = int(next_private.get("chords_used") or 0)
    # The first chord is a free training probe; the budget applies после.
    if chords_used >= CHORD_BUDGET + 1:
        return reject("chord_budget_exhausted", "Лимит комбинаций исчерпан.")

    lamp_count = int(next_private["lamp_count"])
    entropy_before = _entropy_bits(next_private)
    effect = int(effects[normalized])
    current = int(next_private["current"]) ^ effect
    next_private["current"] = current
    next_private["chords_used"] = chords_used + 1
    observed = [str(chord) for chord in next_private.get("observed_chords", [])]
    if normalized not in observed:
        next_private["observed_chords"] = [*observed, normalized]
    entropy_after = _entropy_bits(next_private)

    telemetry = {
        "vs_size_before": 1 << entropy_before,
        "vs_size_after": 1 << entropy_after,
        "gain_bits_actual": float(entropy_before - entropy_after),
        "gain_bits_best": float(
            lamp_count if entropy_before > 0 else 0
        ),
    }

    next_public["current"] = _lamp_list(current, lamp_count)
    if chords_used >= 1:
        next_public["chords_remaining"] = max(
            0,
            int(next_public.get("chords_remaining") or 0) - 1,
        )
    next_public["observations"].append(
        {
            "chord": normalized,
            "training": chords_used == 0,
            "effect": _lamp_list(effect, lamp_count),
            "lamps_after": _lamp_list(current, lamp_count),
        }
    )

    completed = False
    evaluation: dict[str, Any] | None = telemetry
    message = "Комбинация применена: лампы переключились."
    if (
        str(next_private.get("variant")) == REACH_VARIANT
        and current == int(next_private["target"])
    ):
        completed = True
        min_len = max(1, int(next_private.get("min_len") or 1))
        used_total = int(next_private["chords_used"])
        hint_used = bool(next_private.get("hint_used"))
        raw_score = min(1.0, 0.6 + 0.4 * min_len / used_total)
        evaluation = {
            **telemetry,
            "correct": True,
            "reason": "target_reached",
            "chords_used": used_total,
            "min_len": min_len,
            "len_ratio": used_total / min_len,
            "hint_used": hint_used,
            "continuous_score": (
                raw_score * HINT_SCORE_MULTIPLIER if hint_used else raw_score
            ),
            "efficient": used_total <= min_len,
            "evidence": 1 if used_total <= min_len + 1 else 0,
        }
        message = "Лампы совпали с целевым узором. Панель разгадана."

    processed[client_action_id] = {
        "normalized_input": normalized,
        "accepted": True,
        "completed": completed,
        "reason": "accepted",
        "message": message,
        "telemetry": evaluation,
    }
    return WiringTransition(
        public_state=next_public,
        private_state=next_private,
        accepted=True,
        completed=completed,
        reason="accepted",
        message=message,
        normalized_input=normalized,
        evaluation_state=evaluation,
    )


def _parse_prediction(
    answer: str,
    lamp_count: int,
    exam_count: int,
) -> list[int] | None:
    tokens = [
        token
        for token in answer.replace("/answer", " ").replace(",", " ").split()
        if token
    ]
    bit_tokens = [
        token
        for token in tokens
        if len(token) == lamp_count and set(token) <= {"0", "1"}
    ]
    if len(bit_tokens) != exam_count:
        return None
    return [
        sum(1 << index for index, char in enumerate(token) if char == "1")
        for token in bit_tokens
    ]


def evaluate_hidden_wiring_answer(
    *,
    answer: str,
    private_state: dict[str, Any],
) -> dict[str, Any]:
    lamp_count = int(private_state["lamp_count"])
    chords_used = int(private_state.get("chords_used") or 0)
    unused = max(0, CHORD_BUDGET + 1 - chords_used)
    base = {
        "family": FAMILY_KEY,
        "generator_version": GENERATOR_VERSION,
        "difficulty": int(private_state["difficulty"]),
        "variant": str(private_state.get("variant")),
        "chords_used": chords_used,
    }
    if str(private_state.get("variant")) == REACH_VARIANT:
        reached = int(private_state["current"]) == int(private_state["target"])
        return {
            **base,
            "correct": False,
            "parsed": True,
            "should_finalize": False,
            "reason": "target_reached" if reached else "target_not_reached",
            "continuous_score": 0.0,
            "evidence": 0,
            "feedback": (
                "Панель завершается автоматически, когда лампы совпадут "
                "с целью. Продолжайте нажимать комбинации."
            ),
        }
    expected = [int(value) for value in private_state["exam_effects"]]
    predictions = _parse_prediction(answer, lamp_count, len(expected))
    if predictions is None:
        return {
            **base,
            "correct": False,
            "parsed": False,
            "should_finalize": False,
            "reason": "invalid_answer",
            "continuous_score": 0.0,
            "evidence": 0,
            "feedback": (
                "Ответьте тремя битовыми строками по числу ламп, "
                "например: /answer "
                + " ".join("0" * lamp_count for _ in expected)
                + "."
            ),
        }
    total_bits = lamp_count * len(expected)
    correct_bits = sum(
        lamp_count - (prediction ^ target).bit_count()
        for prediction, target in zip(predictions, expected, strict=True)
    )
    accuracy = correct_bits / total_bits
    exact = correct_bits == total_bits
    hint_used = bool(private_state.get("hint_used"))
    raw_score = max(0.0, accuracy - 0.5) * 2
    return {
        **base,
        "correct": exact,
        "parsed": True,
        "predicted": [
            _lamp_list(prediction, lamp_count)
            for prediction in predictions
        ],
        "bit_accuracy": accuracy,
        "correct_bits": correct_bits,
        "total_bits": total_bits,
        "unused_chords": unused,
        "hint_used": hint_used,
        "continuous_score": (
            raw_score * HINT_SCORE_MULTIPLIER if hint_used else raw_score
        ),
        "efficient": exact and unused > 0,
        "evidence": 1 if exact else -1,
    }


def validate_hidden_wiring_instance(
    public_state: dict[str, Any],
    private_state: dict[str, Any],
) -> None:
    """Self-check used by tests: solvability certificates hold."""

    effects = {
        str(chord): int(effect)
        for chord, effect in private_state["chord_effects"].items()
    }
    columns = [int(column) for column in private_state["columns"]]
    assert len(set(columns)) == len(columns)
    assert all(column != 0 for column in columns)
    assert all(effect != 0 for effect in effects.values())
    if str(private_state.get("variant")) == REACH_VARIANT:
        certificate = [str(chord) for chord in private_state["certificate"]]
        state = int(private_state["start"])
        for chord in certificate:
            state ^= effects[chord]
        assert state == int(private_state["target"])
        assert 1 <= len(certificate) <= CHORD_BUDGET
        assert len(certificate) == int(private_state["min_len"])
    else:
        button_count = int(private_state["button_count"])
        allowed = [
            _chord_indicator(str(chord), button_count)
            for chord in private_state["allowed_chords"]
        ]
        for chord in private_state["exam_chords"]:
            assert str(chord) not in {
                str(item) for item in private_state["allowed_chords"]
            }
            assert _in_span(
                _chord_indicator(str(chord), button_count),
                allowed,
            )


__all__ = [
    "CHORD_BUDGET",
    "FAMILY_KEY",
    "GENERATOR_VERSION",
    "PREDICT_VARIANT",
    "PUBLIC_KIND",
    "REACH_VARIANT",
    "WiringTransition",
    "evaluate_hidden_wiring_answer",
    "generate_hidden_wiring_task",
    "transition_hidden_wiring_chord",
    "validate_hidden_wiring_instance",
]
