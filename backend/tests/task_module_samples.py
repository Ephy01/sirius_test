"""Sources of task modules written to a temporary directory by the tests."""

PLUS_ONE = """
from sirius_gate import FamilyCard, TaskFamily, blocks


def generate(seed, difficulty, context):
    total = seed % 7 + difficulty
    public = blocks.scene(f"Сколько будет {total} + 1?", [blocks.text("Ответьте числом.")])
    return public, {"answer": total + 1}


def evaluate(answer, private_state):
    return {"correct": answer.strip() == str(private_state["answer"])}


FAMILY = TaskFamily(
    key="plus_one",
    version="plus-one-v1",
    generate=generate,
    evaluate=evaluate,
    card=FamilyCard(title="Плюс один", description="Учебный модуль."),
)
"""

# The same kind of task written against the plugin interface of the hackathon brief.
COUNT_UP = """
from sirius_gate import NotYet, Plugin, Rejected, TaskType, answers, blocks

LIMITS = {1: 3, 2: 5, 3: 6, 4: 8, 5: 9}


def generate(level, rng):
    return {"target": rng.randint(2, LIMITS[level]), "count": 0}


def validate(variant):
    return variant["target"] % 2 == 0


def view(variant):
    return blocks.scene(
        f"Доведите счётчик до {variant['target']}.",
        [blocks.facts(f"Счётчик: {variant['count']}"), blocks.buttons([blocks.button("+1", "/op plus")])],
        commands=["done"],
    )


def move(variant, text):
    if text != "plus":
        raise Rejected("Можно только прибавлять.")
    variant["count"] += 1
    return variant, "Прибавили один."


def check(answer, variant):
    if answers.text(answer) == "done":
        if variant["count"] < variant["target"]:
            raise NotYet("Счётчик ещё не дошёл до цели.")
        return variant["count"] == variant["target"]
    return answers.integer(answer) == variant["target"]


PLUGIN = Plugin(
    name="counting",
    version="1.2",
    author="Команда 7",
    description="Учебный плагин со счётчиком.",
    task_types=[
        TaskType(
            key="count_up",
            title="Счётчик",
            generate=generate,
            validate=validate,
            check=check,
            view=view,
            move=move,
            solution=lambda variant: ("done", ["/op plus"] * (variant["target"] - variant["count"])),
        )
    ],
)
"""

# A task where the participant drags a point of a drawing.
MIDPOINT = """
from sirius_gate import Plugin, Rejected, TaskType, answers, blocks


def generate(level, rng):
    left = rng.randint(0, 2)
    return {"a": [left, 1], "b": [left + 2 * level, 5], "m": [0, 0]}


def view(variant):
    a, b, m = variant["a"], variant["b"], variant["m"]
    return blocks.scene(
        "Перетащите точку M в середину отрезка AB и напишите done.",
        [
            blocks.picture(
                [blocks.line(*a, *b), blocks.point(*a, label="A"), blocks.point(*b, label="B"),
                 blocks.point(*m, label="M", tone="good", drag="M")],
                x=(0, 12), y=(0, 6), grid=True,
            )
        ],
        commands=["done"],
    )


def drag(variant, name, x, y):
    if x == variant["a"][0] and y == variant["a"][1]:
        raise Rejected("Точка M не может совпадать с A.")
    variant["m"] = [x, y]
    return variant, f"Точка {name} теперь в ({x}, {y})."


def check(answer, variant):
    a, b, m = variant["a"], variant["b"], variant["m"]
    return answers.text(answer) == "done" and [2 * m[0], 2 * m[1]] == [a[0] + b[0], a[1] + b[1]]


def solution(variant):
    a, b = variant["a"], variant["b"]
    return "done", [f"/op drag:M:{(a[0] + b[0]) // 2}:{(a[1] + b[1]) // 2}"]


PLUGIN = Plugin(
    name="midpoint", version="1.0", author="Команда 7", description="Середина отрезка.",
    task_types=[TaskType(key="midpoint", title="Середина отрезка", generate=generate, check=check,
                         view=view, drag=drag, solution=solution)],
)
"""
