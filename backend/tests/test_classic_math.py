from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import Settings
from app.environments import (
    CLASSIC_MATH_FAMILY,
    CLASSIC_MATH_GENERATOR_VERSION,
    evaluate_task,
    generate_task,
)
from app.environments.classic_math import BAR_SEATING, SHARE_PARADOX
from app.main import create_app
from app.models import AttemptEvent, TaskInstance


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def settings(database_path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{database_path}",
        organizer_code="ORBIT-ADMIN",
        security_secret="test-token-secret-that-is-long",
        code_hmac_secret="test-code-secret-that-is-different",
    )


def organizer_token(client: TestClient) -> str:
    response = client.post(
        "/api/v1/access/redeem",
        json={"code": "ORBIT-ADMIN"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def prepare_participant(client: TestClient, *, scripted_task: dict) -> str:
    organizer = organizer_token(client)
    contest_response = client.post(
        "/api/v1/contests",
        headers=auth(organizer),
        json={
            "title": "Заскриптованный якорь",
            "environment_key": "mixed",
            "task_config": {
                "families": [{"family": "dice_chess", "weight": 1}],
                "scripted_tasks": [scripted_task],
            },
        },
    )
    assert contest_response.status_code == 201, contest_response.text
    contest = contest_response.json()
    client.post(
        f"/api/v1/contests/{contest['id']}/enrollments",
        headers=auth(organizer),
        json={
            "participants": [
                {"external_ref": "classic-001", "display_name": "Участник"}
            ]
        },
    )
    code = client.post(
        f"/api/v1/contests/{contest['id']}/codes",
        headers=auth(organizer),
        json={},
    ).json()["items"][0]["code"]
    client.post(
        f"/api/v1/contests/{contest['id']}/publish",
        headers=auth(organizer),
    )
    redeemed = client.post("/api/v1/access/redeem", json={"code": code})
    assert redeemed.status_code == 200
    return redeemed.json()["access_token"]


CORRECT_SHARE_ANSWER = (
    "/answer Сравнения: 5/6 > 8/10; 6/14 > 4/10; 11/20 < 12/20 "
    "Обоснование: "
    "Общая доля является взвешенным средним. Распределение числа задач "
    "разное: у Егора 6 и 14 задач, а у Васи 10 и 10, поэтому веса месяцев "
    "различаются."
)

CORRECT_BAR_ANSWER = (
    "/answer Ответ: первое место 9; максимум 13 "
    "Обоснование: затем получаются "
    "все нечетные места 1, 3, 5, 7, 9, 11, 13, 15, 17, 19, 21, 23, 25 — "
    "всего максимум 13 человек. Больше 13 невозможно: между соседними "
    "посетителями должно оставаться свободное место, поэтому на 25 местах "
    "можно посадить не более 13 человек."
)


@pytest.mark.parametrize(
    ("sub_kind", "correct_answer", "incomplete_answer"),
    [
        (
            SHARE_PARADOX,
            CORRECT_SHARE_ANSWER,
            (
                "/answer Сравнения: 5/6 > 8/10; 6/14 > 4/10; "
                "11/20 < 12/20\nОбоснование: мало"
            ),
        ),
        (
            BAR_SEATING,
            CORRECT_BAR_ANSWER,
            "/answer Ответ: первое место 9; максимум 13\nОбоснование: мало",
        ),
    ],
)
def test_fixed_classic_math_generation_and_rule_based_judge(
    sub_kind: str,
    correct_answer: str,
    incomplete_answer: str,
) -> None:
    generated = generate_task(
        family=CLASSIC_MATH_FAMILY,
        generator_version=CLASSIC_MATH_GENERATOR_VERSION,
        seed=1,
        difficulty=1,
        context={"sub_kinds": [sub_kind]},
    )
    repeated = generate_task(
        family=CLASSIC_MATH_FAMILY,
        generator_version=CLASSIC_MATH_GENERATOR_VERSION,
        seed=999,
        difficulty=1,
        context={"sub_kinds": [sub_kind]},
    )
    assert generated == repeated
    assert generated.public_state["kind"] == "classic_math_free_response"
    assert generated.public_state["sub_kind"] == sub_kind
    assert generated.public_state["scripted"] is True
    assert "rubric" not in generated.public_state
    assert "answer" not in generated.private_state

    correct = evaluate_task(
        family=CLASSIC_MATH_FAMILY,
        generator_version=CLASSIC_MATH_GENERATOR_VERSION,
        answer=correct_answer,
        private_state=generated.private_state,
    )
    assert correct["correct"] is True
    assert correct["continuous_score"] == 1.0
    assert all(correct["conclusion_checks"].values())
    assert correct["reasoning_checked"] is False

    incomplete = evaluate_task(
        family=CLASSIC_MATH_FAMILY,
        generator_version=CLASSIC_MATH_GENERATOR_VERSION,
        answer=incomplete_answer,
        private_state=generated.private_state,
    )
    assert incomplete["correct"] is False
    assert incomplete["result_status"] == "incomplete_reasoning"
    assert incomplete["continuous_score"] == 0.0


@pytest.mark.parametrize(
    ("sub_kind", "answer"),
    [
        (
            SHARE_PARADOX,
            (
                "/answer Сравнения: 5/6 < 8/10; 6/14 > 4/10; "
                "11/20 < 12/20\n"
                "Обоснование: Это длинное, но намеренно неверное "
                "объяснение с неправильным знаком."
            ),
        ),
        (
            SHARE_PARADOX,
            (
                "/answer Сравнения: не 5/6 > 8/10; 6/14 > 4/10; "
                "11/20 < 12/20\n"
                "Обоснование: Отрицание перед сравнением не должно "
                "проходить точный машинный вывод."
            ),
        ),
        (
            BAR_SEATING,
            (
                "/answer Ответ: первое место 13; максимум 13\n"
                "Обоснование: Здесь достаточно длинный текст, но первое "
                "место выбрано неверно."
            ),
        ),
        (
            BAR_SEATING,
            (
                "/answer Ответ: первое место не 9; максимум не 13\n"
                "Обоснование: Отрицания не должны ошибочно считаться "
                "правильным структурированным выводом."
            ),
        ),
    ],
)
def test_structured_judge_rejects_adversarial_conclusions(
    sub_kind: str,
    answer: str,
) -> None:
    generated = generate_task(
        family=CLASSIC_MATH_FAMILY,
        generator_version=CLASSIC_MATH_GENERATOR_VERSION,
        seed=1,
        difficulty=1,
        context={"sub_kinds": [sub_kind]},
    )
    evaluation = evaluate_task(
        family=CLASSIC_MATH_FAMILY,
        generator_version=CLASSIC_MATH_GENERATOR_VERSION,
        answer=answer,
        private_state=generated.private_state,
    )
    assert evaluation["correct"] is False
    assert evaluation["result_status"] == "incorrect"
    assert evaluation["conclusion_checks"]["conclusion_valid"] is False


@pytest.mark.parametrize(
    "scripted_tasks",
    [
        {"family": "classic_math", "sub_kind": SHARE_PARADOX, "position": 1},
        [
            {"family": "classic_math", "sub_kind": SHARE_PARADOX, "position": 1},
            {"family": "classic_math", "sub_kind": BAR_SEATING, "position": 2},
        ],
        [{"family": "dice_chess", "sub_kind": SHARE_PARADOX, "position": 1}],
        [{"family": "classic_math", "sub_kind": "unknown", "position": 1}],
        [{"family": "classic_math", "sub_kind": SHARE_PARADOX, "position": 0}],
        [{"family": "classic_math", "sub_kind": SHARE_PARADOX, "position": 101}],
        [{"family": "classic_math", "sub_kind": SHARE_PARADOX, "position": True}],
    ],
)
def test_contest_rejects_invalid_scripted_task_config(
    tmp_path,
    scripted_tasks,
) -> None:
    application = create_app(settings(tmp_path / "invalid-script.db"))
    with TestClient(application) as client:
        organizer = organizer_token(client)
        response = client.post(
            "/api/v1/contests",
            headers=auth(organizer),
            json={
                "title": "Некорректный сценарий",
                "environment_key": "mixed",
                "task_config": {
                    "families": ["dice_chess"],
                    "scripted_tasks": scripted_tasks,
                },
            },
        )
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "SCRIPTED_TASK_CONFIG_INVALID"


def test_classic_math_is_inserted_once_and_all_closed_tasks_get_binary_score(
    tmp_path,
) -> None:
    application = create_app(settings(tmp_path / "classic-route.db"))
    with TestClient(application) as client:
        participant = prepare_participant(
            client,
            scripted_task={
                "family": "classic_math",
                "sub_kind": BAR_SEATING,
                "position": 2,
            },
        )
        started = client.post(
            "/api/v1/participant/attempts/start",
            headers=auth(participant),
        )
        assert started.status_code == 200

        first = client.get(
            "/api/v1/participant/tasks/current",
            headers=auth(participant),
        ).json()["task"]
        assert first["ordinal"] == 1
        assert first["family"] == "dice_chess"
        with application.state.database.session_factory() as session:
            stored = session.get(TaskInstance, first["id"])
            probability = stored.private_state["probability"]
            correct_probability = (
                f"{probability['numerator']}/{probability['denominator']}"
            )
        answered_first = client.post(
            f"/api/v1/participant/tasks/{first['id']}/answer",
            headers=auth(participant),
            json={"answer": correct_probability},
        )
        assert answered_first.status_code == 200

        scripted = client.post(
            "/api/v1/participant/tasks/next",
            headers=auth(participant),
        ).json()["task"]
        assert scripted["ordinal"] == 2
        assert scripted["family"] == CLASSIC_MATH_FAMILY
        assert scripted["public_state"]["sub_kind"] == BAR_SEATING
        answered_script = client.post(
            f"/api/v1/participant/tasks/{scripted['id']}/answer",
            headers=auth(participant),
            json={"answer": CORRECT_BAR_ANSWER},
        )
        assert answered_script.status_code == 200
        assert answered_script.json()["task"]["status"] == "answered"
        assert "evaluation_state" not in answered_script.json()["task"]

        for expected_ordinal in range(3, 7):
            task = client.post(
                "/api/v1/participant/tasks/next",
                headers=auth(participant),
            ).json()["task"]
            assert task["ordinal"] == expected_ordinal
            assert task["family"] == "dice_chess"
            skipped = client.post(
                f"/api/v1/participant/tasks/{task['id']}/skip",
                headers=auth(participant),
            )
            assert skipped.status_code == 200

        with application.state.database.session_factory() as session:
            tasks = list(
                session.scalars(
                    select(TaskInstance).order_by(TaskInstance.ordinal)
                ).all()
            )
            assert [task.family for task in tasks].count(CLASSIC_MATH_FAMILY) == 1
            assert all(task.evaluation_state is not None for task in tasks)
            assert [task.evaluation_state["score"] for task in tasks] == [
                1,
                1,
                0,
                0,
                0,
                0,
            ]
            classic = next(
                task for task in tasks if task.family == CLASSIC_MATH_FAMILY
            )
            assert classic.evaluation_state["correct"] is True
            evaluated_event = session.scalar(
                select(AttemptEvent).where(
                    AttemptEvent.task_instance_id == classic.id,
                    AttemptEvent.event_type == "answer_evaluated",
                )
            )
            assert evaluated_event is not None
            assert evaluated_event.payload["score"] == 1
            assert evaluated_event.payload["conclusion_checks"] == {
                "conclusion_valid": True,
                "reasoning_supplied": True,
            }
            assert evaluated_event.payload["reasoning_checked"] is False
