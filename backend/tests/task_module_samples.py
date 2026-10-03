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
