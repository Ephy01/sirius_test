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
from sirius_gate import EASY, HARD, MEDIUM, Plugin, Rejected, TaskType, answers, blocks

LIMITS = {EASY: 3, MEDIUM: 6, HARD: 9}


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
