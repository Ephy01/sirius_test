from __future__ import annotations

from fractions import Fraction
from math import gcd

import chess
import pytest

from app.environments.chess_world.dice_chess_position import (
    CHESS_PIECE_CODES,
    PIECE_CODES,
    evaluate_dice_chess_position_answer,
    generate_dice_chess_position_task,
)

PUBLIC_KEYS = {
    "kind",
    "prompt",
    "board",
    "side_to_move",
    "die",
    "sample_space_size",
    "event_description",
    "response_hint",
}
PIECE_TYPES_BY_CODE = {
    code: piece_type
    for piece_type, code in CHESS_PIECE_CODES.items()
}


def _rebuild_public_board(public_state: dict) -> chess.Board:
    board = chess.Board(None)
    for row_index, row in enumerate(public_state["board"]):
        rank = 7 - row_index
        for file_index, code in enumerate(row):
            if code is None:
                continue
            color = chess.WHITE if code[0] == "w" else chess.BLACK
            piece_type = PIECE_TYPES_BY_CODE[code[1]]
            board.set_piece_at(
                chess.square(file_index, rank),
                chess.Piece(piece_type, color),
            )
    board.turn = public_state["side_to_move"] == "white"
    board.castling_rights = chess.BB_EMPTY
    board.ep_square = None
    return board


def _independent_eligible_piece_types(
    board: chess.Board,
    event_type: str,
) -> set[str]:
    eligible: set[str] = set()
    for move in board.legal_moves:
        if event_type == "legal_move":
            qualifies = True
        elif event_type == "capture":
            qualifies = board.is_capture(move)
        elif event_type == "checking_move":
            qualifies = board.gives_check(move)
        else:
            raise AssertionError(f"Unexpected event type: {event_type}")
        if not qualifies:
            continue
        piece = board.piece_at(move.from_square)
        assert piece is not None
        eligible.add(CHESS_PIECE_CODES[piece.piece_type])
    return eligible


def _nested_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {
            nested_key
            for nested_value in value.values()
            for nested_key in _nested_keys(nested_value)
        }
    if isinstance(value, list):
        return {
            nested_key
            for item in value
            for nested_key in _nested_keys(item)
        }
    return set()


def test_position_generator_is_deterministic_legal_exact_and_nontrivial():
    observed_event_types: set[str] = set()
    observed_sides: set[str] = set()
    observed_probabilities: set[Fraction] = set()

    for difficulty in (1, 3, 5, 8):
        for seed in range(120):
            public, private = generate_dice_chess_position_task(
                seed=seed,
                difficulty=difficulty,
            )
            assert (public, private) == generate_dice_chess_position_task(
                seed=seed,
                difficulty=difficulty,
            )

            assert set(public) == PUBLIC_KEYS
            assert public["kind"] == "dice_chess_position_probability"
            assert public["side_to_move"] in {"white", "black"}
            assert public["sample_space_size"] == 6
            assert set(public["die"]) == {"id", "label", "faces"}
            assert len(public["die"]["faces"]) == 6
            assert set(public["die"]["faces"]) <= set(PIECE_CODES)
            assert len(public["board"]) == 8
            assert all(len(row) == 8 for row in public["board"])
            assert all(
                cell is None
                or (
                    len(cell) == 2
                    and cell[0] in {"w", "b"}
                    and cell[1] in PIECE_CODES
                )
                for row in public["board"]
                for cell in row
            )

            board = _rebuild_public_board(public)
            assert board.is_valid()
            assert not board.is_game_over(claim_draw=True)
            assert board.turn == (public["side_to_move"] == "white")

            event_type = private["event_type"]
            independently_eligible = _independent_eligible_piece_types(
                board,
                event_type,
            )
            assert independently_eligible == set(private["eligible_piece_types"])
            assert (
                set(private["ineligible_piece_types"])
                == set(PIECE_CODES) - independently_eligible
            )

            independently_favorable = sum(
                face in independently_eligible
                for face in public["die"]["faces"]
            )
            assert independently_favorable == private["favorable_faces"]
            assert 0 < independently_favorable < 6
            assert private["total_faces"] == 6

            exact = private["probability"]
            assert gcd(exact["numerator"], exact["denominator"]) == 1
            probability = Fraction(
                exact["numerator"],
                exact["denominator"],
            )
            assert probability == Fraction(independently_favorable, 6)
            assert 0 < probability < 1

            assert _nested_keys(public).isdisjoint(
                {
                    "probability",
                    "favorable_faces",
                    "eligible_piece_types",
                    "qualifying_move_counts",
                    "fen",
                    "seed",
                    "evaluation",
                    "correct",
                }
            )

            if difficulty < 3:
                assert event_type == "legal_move"
            elif difficulty < 5:
                assert event_type in {"legal_move", "capture"}
            else:
                assert event_type in {
                    "legal_move",
                    "capture",
                    "checking_move",
                }
            observed_event_types.add(event_type)
            observed_sides.add(public["side_to_move"])
            observed_probabilities.add(probability)

    assert observed_event_types == {"legal_move", "capture", "checking_move"}
    assert observed_sides == {"white", "black"}
    assert len(observed_probabilities) == 5


def test_public_board_order_is_rank_eight_to_one_and_file_a_to_h():
    public, private = generate_dice_chess_position_task(seed=19, difficulty=6)
    board = chess.Board(private["diagnostics"]["fen"])

    for row_index, row in enumerate(public["board"]):
        rank = 7 - row_index
        for file_index, code in enumerate(row):
            piece = board.piece_at(chess.square(file_index, rank))
            if piece is None:
                assert code is None
            else:
                color_prefix = "w" if piece.color == chess.WHITE else "b"
                assert code == f"{color_prefix}{CHESS_PIECE_CODES[piece.piece_type]}"


@pytest.mark.parametrize(
    ("answer", "correct", "parsed"),
    [
        ("1/2", True, True),
        ("0,5", True, True),
        ("50%", True, True),
        ("0.49", False, True),
        ("2/3", False, True),
        ("150%", False, False),
        ("не знаю", False, False),
    ],
)
def test_position_probability_evaluator_reuses_probability_contract(
    answer: str,
    correct: bool,
    parsed: bool,
):
    evaluation = evaluate_dice_chess_position_answer(
        answer=answer,
        private_state={
            "probability": {
                "numerator": 1,
                "denominator": 2,
            }
        },
    )
    assert evaluation["correct"] is correct
    assert evaluation["parsed"] is parsed
