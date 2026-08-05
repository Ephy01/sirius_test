from __future__ import annotations

import random
from collections import Counter
from fractions import Fraction
from typing import Any

import chess

from .dice_chess import evaluate_dice_chess_answer

FAMILY_KEY = "dice_chess_position"
GENERATOR_VERSION = "dice-chess-position-probability-v1"

PIECE_CODES = ("K", "Q", "R", "B", "N", "P")
PIECE_LABELS = {
    "K": "король",
    "Q": "ферзь",
    "R": "ладья",
    "B": "слон",
    "N": "конь",
    "P": "пешка",
}
CHESS_PIECE_CODES = {
    chess.KING: "K",
    chess.QUEEN: "Q",
    chess.ROOK: "R",
    chess.BISHOP: "B",
    chess.KNIGHT: "N",
    chess.PAWN: "P",
}

MAX_POSITION_ATTEMPTS = 48
DIE_FACE_COUNT = 6


def _allowed_event_types(difficulty: int) -> tuple[str, ...]:
    event_types = ["legal_move"]
    if difficulty >= 3:
        event_types.append("capture")
    if difficulty >= 5:
        event_types.append("checking_move")
    return tuple(event_types)


def _event_matches(board: chess.Board, move: chess.Move, event_type: str) -> bool:
    if event_type == "legal_move":
        return True
    if event_type == "capture":
        return board.is_capture(move)
    if event_type == "checking_move":
        return board.gives_check(move)
    raise ValueError(f"Unsupported board-conditioned Dice & Chess event: {event_type!r}")


def _qualifying_move_counts(
    board: chess.Board,
    event_type: str,
) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for move in board.legal_moves:
        if not _event_matches(board, move, event_type):
            continue
        piece = board.piece_at(move.from_square)
        if piece is None:
            continue
        counts[CHESS_PIECE_CODES[piece.piece_type]] += 1
    return {piece_code: counts[piece_code] for piece_code in PIECE_CODES}


def _nontrivial_event_options(
    board: chess.Board,
    event_types: tuple[str, ...],
) -> list[tuple[str, dict[str, int], tuple[str, ...], tuple[str, ...]]]:
    options: list[tuple[str, dict[str, int], tuple[str, ...], tuple[str, ...]]] = []
    for event_type in event_types:
        counts = _qualifying_move_counts(board, event_type)
        eligible = tuple(code for code in PIECE_CODES if counts[code] > 0)
        ineligible = tuple(code for code in PIECE_CODES if counts[code] == 0)
        if eligible and ineligible:
            options.append((event_type, counts, eligible, ineligible))
    return options


def _random_position(
    rng: random.Random,
    difficulty: int,
) -> tuple[chess.Board, int] | None:
    board = chess.Board()
    minimum_plies = min(24, max(0, difficulty * 2 - 2))
    maximum_plies = min(64, minimum_plies + 10 + difficulty * 2)
    target_plies = rng.randint(minimum_plies, maximum_plies)

    for _ in range(target_plies):
        legal_moves = sorted(board.legal_moves, key=chess.Move.uci)
        if not legal_moves:
            return None
        board.push(rng.choice(legal_moves))
        if board.is_game_over(claim_draw=True):
            return None

    board.castling_rights = chess.BB_EMPTY
    board.ep_square = None
    board.clear_stack()
    if not board.is_valid() or board.is_game_over(claim_draw=True):
        return None
    return board, target_plies


def _serialize_board(board: chess.Board) -> list[list[str | None]]:
    rows: list[list[str | None]] = []
    for rank in range(7, -1, -1):
        row: list[str | None] = []
        for file_index in range(8):
            piece = board.piece_at(chess.square(file_index, rank))
            if piece is None:
                row.append(None)
                continue
            color_prefix = "w" if piece.color == chess.WHITE else "b"
            row.append(f"{color_prefix}{CHESS_PIECE_CODES[piece.piece_type]}")
        rows.append(row)
    return rows


def _build_die(
    rng: random.Random,
    eligible: tuple[str, ...],
    ineligible: tuple[str, ...],
) -> tuple[tuple[str, ...], int]:
    favorable_face_count = rng.randint(1, DIE_FACE_COUNT - 1)
    faces = [
        rng.choice(eligible)
        for _ in range(favorable_face_count)
    ]
    faces.extend(
        rng.choice(ineligible)
        for _ in range(DIE_FACE_COUNT - favorable_face_count)
    )
    rng.shuffle(faces)
    return tuple(faces), favorable_face_count


def _fallback_task_inputs() -> tuple[
    chess.Board,
    str,
    dict[str, int],
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
    int,
]:
    board = chess.Board()
    board.castling_rights = chess.BB_EMPTY
    board.ep_square = None
    board.clear_stack()
    event_type = "legal_move"
    counts = _qualifying_move_counts(board, event_type)
    eligible = ("N", "P")
    ineligible = ("K", "Q", "R", "B")
    faces = ("P", "Q", "N", "R", "B", "K")
    return board, event_type, counts, eligible, ineligible, faces, 2


def _event_description(event_type: str) -> str:
    if event_type == "legal_move":
        return (
            "После броска будет доступен хотя бы один "
            "легальный ход фигурой выпавшего типа."
        )
    if event_type == "capture":
        return (
            "После броска будет доступен хотя бы один "
            "легальный ход со взятием фигурой выпавшего типа."
        )
    return (
        "После броска будет доступен хотя бы один легальный ход, "
        "объявляющий шах, фигурой выпавшего типа."
    )


def generate_dice_chess_position_task(
    *,
    seed: int,
    difficulty: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    rng = random.Random(seed)
    allowed_events = _allowed_event_types(difficulty)
    selected: tuple[
        chess.Board,
        str,
        dict[str, int],
        tuple[str, ...],
        tuple[str, ...],
        tuple[str, ...],
        int,
        int,
        str,
    ] | None = None

    for _ in range(MAX_POSITION_ATTEMPTS):
        position = _random_position(rng, difficulty)
        if position is None:
            continue
        board, plies_from_start = position
        options = _nontrivial_event_options(board, allowed_events)
        if not options:
            continue
        event_type, counts, eligible, ineligible = rng.choice(options)
        faces, favorable_face_count = _build_die(rng, eligible, ineligible)
        selected = (
            board,
            event_type,
            counts,
            eligible,
            ineligible,
            faces,
            favorable_face_count,
            plies_from_start,
            "random_legal_playout",
        )
        break

    if selected is None:
        (
            board,
            event_type,
            counts,
            eligible,
            ineligible,
            faces,
            favorable_face_count,
        ) = _fallback_task_inputs()
        selected = (
            board,
            event_type,
            counts,
            eligible,
            ineligible,
            faces,
            favorable_face_count,
            0,
            "deterministic_fallback",
        )

    (
        board,
        event_type,
        qualifying_move_counts,
        eligible,
        ineligible,
        faces,
        favorable_face_count,
        plies_from_start,
        position_source,
    ) = selected
    probability = Fraction(favorable_face_count, DIE_FACE_COUNT)
    side_to_move = "white" if board.turn == chess.WHITE else "black"
    side_label = "белых" if board.turn == chess.WHITE else "чёрных"

    public_state: dict[str, Any] = {
        "kind": "dice_chess_position_probability",
        "prompt": (
            "Перед вами легальная шахматная позиция. "
            f"Ход {side_label}. Бросают один шестигранный кубик: "
            "выпавшая грань задаёт тип фигуры. Все грани равновероятны. "
            "Найдите вероятность описанного события."
        ),
        "board": _serialize_board(board),
        "side_to_move": side_to_move,
        "die": {
            "id": "piece-die",
            "label": "Кубик фигур",
            "faces": list(faces),
        },
        "sample_space_size": DIE_FACE_COUNT,
        "event_description": _event_description(event_type),
        "response_hint": (
            "Введите вероятность сокращённой дробью a/b, "
            "десятичным числом или в процентах."
        ),
    }
    private_state: dict[str, Any] = {
        "event_type": event_type,
        "eligible_piece_types": list(eligible),
        "ineligible_piece_types": list(ineligible),
        "qualifying_move_counts": qualifying_move_counts,
        "favorable_faces": favorable_face_count,
        "total_faces": DIE_FACE_COUNT,
        "probability": {
            "numerator": probability.numerator,
            "denominator": probability.denominator,
        },
        "diagnostics": {
            "fen": board.fen(),
            "plies_from_start": plies_from_start,
            "position_source": position_source,
            "difficulty": difficulty,
        },
    }
    return public_state, private_state


def evaluate_dice_chess_position_answer(
    *,
    answer: str,
    private_state: dict[str, Any],
) -> dict[str, Any]:
    return evaluate_dice_chess_answer(
        answer=answer,
        private_state=private_state,
    )
