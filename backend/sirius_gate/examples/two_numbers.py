"""Сумма двух чисел: самый короткий пример задачи."""

import random

from sirius_gate import FamilyCard, TaskFamily, answers, blocks


def generate(seed, difficulty, context):
    # Все случайные решения берутся из rng, поэтому одинаковый seed даёт одинаковую задачу.
    rng = random.Random(seed)
    limit = 10**difficulty
    a, b = rng.randint(limit // 10, limit), rng.randint(limit // 10, limit)
    public = blocks.scene(
        f'Сколько будет {a} + {b}?',
        [blocks.table(['Слагаемое', 'Значение'], [['первое', a], ['второе', b]])],
        response_hint='/answer <число>',
    )
    # Первую часть видит участник, вторая хранит ответ.
    return public, {'answer': a + b}


def evaluate(answer, private_state):
    return {'correct': answers.integer(answer) == private_state['answer']}


FAMILY = TaskFamily(
    key='two_numbers',
    version='two-numbers-v1',
    generate=generate,
    evaluate=evaluate,
    reference_answer=lambda private_state: (f'/answer {private_state["answer"]}', []),
    card=FamilyCard(title='Сумма двух чисел', description='Учебный пример.'),
)
