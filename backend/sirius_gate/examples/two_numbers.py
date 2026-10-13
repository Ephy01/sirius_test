"""Сумма двух чисел: самый короткий плагин."""

from sirius_gate import Plugin, TaskType, answers, blocks

# Наибольшее слагаемое на каждом из пяти уровней сложности.
LIMITS = {1: 20, 2: 50, 3: 200, 4: 500, 5: 2000}


def generate(level, rng):
    """Вариант задачи: всё, что её определяет. Случайные числа берутся только из rng."""
    limit = LIMITS[level]
    return {'a': rng.randint(limit // 10, limit), 'b': rng.randint(limit // 10, limit)}


def validate(variant):
    """Годится ли вариант. Здесь отбрасываются варианты с одинаковыми слагаемыми."""
    return variant['a'] != variant['b']


def view(variant):
    """Что видит участник."""
    return blocks.scene(
        f'Сколько будет {variant["a"]} + {variant["b"]}?',
        [blocks.table(['Слагаемое', 'Значение'], [['первое', variant['a']], ['второе', variant['b']]])],
        response_hint='/answer <число>',
    )


def check(answer, variant):
    """Верен ли ответ участника."""
    return answers.integer(answer) == variant['a'] + variant['b']


def solution(variant):
    """Эталонный ответ. По нему работает автоматическая проверка плагина."""
    return f'/answer {variant["a"] + variant["b"]}'


PLUGIN = Plugin(
    name='two_numbers',
    version='1.0',
    author='Sirius Gate',
    description='Учебный пример: сумма двух чисел.',
    task_types=[
        TaskType(
            key='two_numbers',
            title='Сумма двух чисел',
            generate=generate,
            validate=validate,
            check=check,
            view=view,
            solution=solution,
        )
    ],
)
