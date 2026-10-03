"""dice_chess: probability of an event on a chess board with a piece die.

Levels one and two ask about the pieces present on a drawn board, higher
levels about legal moves in a position reached by random play.
"""

from __future__ import annotations

from ..answers import probability_debug_details, probability_reference_answer
from ..family import State, TaskFamily
from .inventory import generate_dice_chess_inventory_task
from .position import generate_dice_chess_position_task
from .probability import evaluate_dice_chess_answer

FAMILY_KEY = 'dice_chess'
GENERATOR_VERSION = 'dice-chess-world-v3'
POSITION_TASK_MIN_DIFFICULTY = 3

AI_VISIBLE_KEYS = ('board', 'die', 'dice', 'side_to_move', 'event_description', 'sample_space_size')


def generate_dice_chess_task(*, seed: int, difficulty: int) -> tuple[State, State]:
    if difficulty < 1:
        raise ValueError('difficulty must be at least 1')
    if difficulty < POSITION_TASK_MIN_DIFFICULTY:
        return generate_dice_chess_inventory_task(seed=seed, difficulty=difficulty)
    public_state, private_state = generate_dice_chess_position_task(seed=seed, difficulty=difficulty)
    return public_state, {**private_state, 'mission_variant': 'legal_position_probability'}


FAMILY = TaskFamily(
    key=FAMILY_KEY,
    version=GENERATOR_VERSION,
    generate=lambda seed, difficulty, context: generate_dice_chess_task(seed=seed, difficulty=difficulty),
    evaluate=lambda answer, private_state: evaluate_dice_chess_answer(
        answer=answer, private_state=private_state
    ),
    aliases=('dice-chess', 'dice&chess'),
    reference_answer=probability_reference_answer,
    debug_details=probability_debug_details,
    ai_context=lambda public_state: {
        key: public_state.get(key) for key in AI_VISIBLE_KEYS if key in public_state
    },
)
