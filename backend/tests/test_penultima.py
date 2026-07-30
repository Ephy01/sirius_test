from __future__ import annotations

from collections import Counter, deque
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.config import Settings
from app.environments.chess_world.penultima import (
    GENERATOR_VERSION,
    RULE_CATALOG_VERSION,
    generate_penultima_task,
    legal_destinations,
    parse_move,
    shortest_path,
    transition_penultima_move,
)
from app.main import create_app
from app.models import (
    Attempt,
    AttemptEvent,
    AttemptStatus,
    TaskInstance,
    TaskInteraction,
    TaskStatus,
    utc_now,
)

PUBLIC_KEYS = {
    "kind",
    "prompt",
    "board",
    "piece_name",
    "current_square",
    "goal_square",
    "chapter_stage",
    "stage_title",
    "accepted_moves",
    "rejected_moves",
    "recent_observations",
    "response_hint",
}
FORBIDDEN_PUBLIC_KEYS = {
    "seed",
    "rule_key",
    "rule_catalog_version",
    "blockers",
    "shortest_solution",
    "remaining_shortest_solution",
    "private_state",
    "evaluation_state",
    "context_hash",
    "parent_task_id",
}


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _settings(database_path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{database_path}",
        organizer_code="ORBIT-ADMIN",
        security_secret="test-token-secret-that-is-long",
        code_hmac_secret="test-code-secret-that-is-different",
    )


def _prepare_participant(client: TestClient, *, external_ref: str) -> str:
    organizer = client.post(
        "/api/v1/access/redeem",
        json={"code": "ORBIT-ADMIN"},
    ).json()["access_token"]
    contest = client.post(
        "/api/v1/contests",
        headers=auth(organizer),
        json={
            "title": "Micro-Penultima",
            "task_config": {
                "adaptation_threshold": 3,
                "families": [
                    {
                        "key": "penultima",
                        "enabled": True,
                        "weight": 1,
                        "initial_difficulty": 1,
                        "max_difficulty": 8,
                    }
                ],
            },
        },
    ).json()
    client.post(
        f"/api/v1/contests/{contest['id']}/enrollments",
        headers=auth(organizer),
        json={
            "participants": [
                {
                    "external_ref": external_ref,
                    "display_name": "Участник Penultima",
                }
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
    return client.post(
        "/api/v1/access/redeem",
        json={"code": code},
    ).json()["access_token"]


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


def _reachable_component(
    *,
    start: str,
    rule_key: str,
    blockers: tuple[str, ...],
) -> set[str]:
    reached = {start}
    queue: deque[str] = deque([start])
    while queue:
        current = queue.popleft()
        for destination in legal_destinations(
            square=current,
            rule_key=rule_key,
            blockers=blockers,
        ):
            assert current in legal_destinations(
                square=destination,
                rule_key=rule_key,
                blockers=blockers,
            )
            if destination not in reached:
                reached.add(destination)
                queue.append(destination)
    return reached


def _stored_task(application, task_id: str) -> TaskInstance:
    with application.state.database.session_factory() as session:
        task = session.get(TaskInstance, task_id)
        assert task is not None
        session.expunge(task)
        return task


def _solve_task(
    *,
    client: TestClient,
    application,
    participant: str,
    task_id: str,
    id_prefix: str,
) -> dict:
    stored = _stored_task(application, task_id)
    solution = list(stored.private_state["shortest_solution"])
    assert solution
    response_body: dict = {}
    for index, move in enumerate(solution, start=1):
        response = client.post(
            f"/api/v1/participant/tasks/{task_id}/interactions",
            headers=auth(participant),
            json={
                "client_action_id": f"{id_prefix}-{index}",
                "action_type": "move",
                "move": move,
            },
        )
        assert response.status_code == 200
        response_body = response.json()
        assert response_body["accepted"] is True
        assert response_body["completed"] is (index == len(solution))
    return response_body


def test_generator_is_deterministic_varied_reachable_and_private():
    observed_rules: Counter[str] = Counter()
    observed_positions: set[tuple[str, str]] = set()

    for difficulty in range(1, 8):
        for seed in range(24):
            public, private = generate_penultima_task(
                seed=seed,
                difficulty=difficulty,
            )
            assert (public, private) == generate_penultima_task(
                seed=seed,
                difficulty=difficulty,
            )
            assert set(public) == PUBLIC_KEYS
            assert public["kind"] == "penultima_induction"
            assert "Обычные шахматные правила здесь не действуют" in public["prompt"]
            assert len(public["board"]) == 8
            assert all(len(row) == 8 for row in public["board"])
            assert all(
                cell is None or cell in {"wN", "bK", "bP"}
                for row in public["board"]
                for cell in row
            )
            assert _nested_keys(public).isdisjoint(FORBIDDEN_PUBLIC_KEYS)

            assert private["rule_catalog_version"] == RULE_CATALOG_VERSION
            assert private["generation"]["branch"] == "initial"
            assert private["chapter_stage"] == 1
            assert 2 <= private["initial_shortest_path_length"] <= 8
            assert (
                len(private["shortest_solution"])
                == private["initial_shortest_path_length"]
            )
            assert len(
                legal_destinations(
                    square=private["current_square"],
                    rule_key=private["rule_key"],
                    blockers=private["blockers"],
                )
            ) >= 2

            path = shortest_path(
                start=private["current_square"],
                goal=private["goal_square"],
                rule_key=private["rule_key"],
                blockers=private["blockers"],
            )
            assert path is not None
            assert len(path) - 1 == private["initial_shortest_path_length"]
            component = _reachable_component(
                start=private["current_square"],
                rule_key=private["rule_key"],
                blockers=tuple(private["blockers"]),
            )
            assert private["goal_square"] in component
            assert all(
                shortest_path(
                    start=square,
                    goal=private["goal_square"],
                    rule_key=private["rule_key"],
                    blockers=private["blockers"],
                )
                is not None
                for square in component
            )

            observed_rules[private["rule_key"]] += 1
            observed_positions.add(
                (private["current_square"], private["goal_square"])
            )

    assert len(observed_rules) >= 10
    assert len(observed_positions) >= 80


def test_coordinate_parser_and_pure_transition_contract():
    assert parse_move("A1 b2") == ("a1", "b2", "a1b2")
    assert parse_move("a1-b2") == ("a1", "b2", "a1b2")
    assert parse_move("a1b2") == ("a1", "b2", "a1b2")
    assert parse_move("not a move") is None

    public, private = generate_penultima_task(seed=77, difficulty=3)
    original_public = public.copy()
    original_private = private.copy()
    current = private["current_square"]
    rejected = transition_penultima_move(
        move=f"{current}{current}",
        public_state=public,
        private_state=private,
    )
    assert rejected.accepted is False
    assert rejected.completed is False
    assert rejected.public_state["board"] == public["board"]
    assert rejected.public_state["current_square"] == current
    assert rejected.public_state["rejected_moves"] == 1
    assert public == original_public
    assert private == original_private

    state_public = public
    state_private = private
    solution = list(private["shortest_solution"])
    for index, move in enumerate(solution, start=1):
        transitioned = transition_penultima_move(
            move=move,
            public_state=state_public,
            private_state=state_private,
        )
        assert transitioned.accepted is True
        assert transitioned.completed is (index == len(solution))
        state_public = transitioned.public_state
        state_private = transitioned.private_state
        assert (
            shortest_path(
                start=state_private["current_square"],
                goal=state_private["goal_square"],
                rule_key=state_private["rule_key"],
                blockers=state_private["blockers"],
            )
            is not None
        )
    assert state_public["current_square"] == state_public["goal_square"]
    assert transitioned.evaluation_state is not None
    assert transitioned.evaluation_state["correct"] is True
    assert transitioned.evaluation_state["efficient"] is True


def test_api_interactions_are_private_idempotent_and_terminal(tmp_path):
    application = create_app(_settings(tmp_path / "penultima-api.db"))
    with TestClient(application) as client:
        participant = _prepare_participant(client, external_ref="penultima-api")
        started = client.post(
            "/api/v1/participant/attempts/start",
            headers=auth(participant),
        )
        assert started.status_code == 200
        assert "seed" not in started.json()["attempt"]
        context = client.get(
            "/api/v1/participant/context",
            headers=auth(participant),
        )
        assert "seed" not in context.json()["active_attempt"]

        current_response = client.get(
            "/api/v1/participant/tasks/current",
            headers=auth(participant),
        )
        task = current_response.json()["task"]
        assert task["family"] == "penultima"
        assert task["generator_version"] == GENERATOR_VERSION
        assert _nested_keys(task).isdisjoint(FORBIDDEN_PUBLIC_KEYS)

        answer_rejected = client.post(
            f"/api/v1/participant/tasks/{task['id']}/answer",
            headers=auth(participant),
            json={"answer": "правило коня"},
        )
        assert answer_rejected.status_code == 409
        assert (
            answer_rejected.json()["detail"]["code"]
            == "INTERACTIVE_TASK_REQUIRES_MOVE"
        )

        stored = _stored_task(application, task["id"])
        initial_board = task["public_state"]["board"]
        current_square = stored.private_state["current_square"]
        rejected_payload = {
            "client_action_id": "probe-1",
            "action_type": "move",
            "move": f"{current_square}{current_square}",
        }
        rejected = client.post(
            f"/api/v1/participant/tasks/{task['id']}/interactions",
            headers=auth(participant),
            json=rejected_payload,
        )
        assert rejected.status_code == 200
        assert rejected.json()["accepted"] is False
        assert rejected.json()["completed"] is False
        assert rejected.json()["task"]["public_state"]["board"] == initial_board
        assert rejected.json()["task"]["public_state"]["rejected_moves"] == 1

        repeated = client.post(
            f"/api/v1/participant/tasks/{task['id']}/interactions",
            headers=auth(participant),
            json=rejected_payload,
        )
        assert repeated.status_code == 200
        assert repeated.json()["task"]["public_state"]["rejected_moves"] == 1
        with application.state.database.session_factory() as session:
            assert session.scalar(
                select(func.count(TaskInteraction.id)).where(
                    TaskInteraction.task_instance_id == task["id"]
                )
            ) == 1

        mismatch = client.post(
            f"/api/v1/participant/tasks/{task['id']}/interactions",
            headers=auth(participant),
            json={
                **rejected_payload,
                "move": stored.private_state["shortest_solution"][0],
            },
        )
        assert mismatch.status_code == 409
        assert mismatch.json()["detail"]["code"] == "INTERACTION_ID_REUSED"

        solution = list(stored.private_state["shortest_solution"])
        final_response: dict = {}
        for index, move in enumerate(solution, start=1):
            response = client.post(
                f"/api/v1/participant/tasks/{task['id']}/interactions",
                headers=auth(participant),
                json={
                    "client_action_id": f"solve-{index}",
                    "action_type": "move",
                    "move": move,
                },
            )
            assert response.status_code == 200
            final_response = response.json()
            assert final_response["accepted"] is True
            assert final_response["completed"] is (index == len(solution))

        assert final_response["task"]["status"] == "answered"
        assert final_response["task"]["public_state"]["current_square"] == (
            final_response["task"]["public_state"]["goal_square"]
        )
        assert _nested_keys(final_response).isdisjoint(FORBIDDEN_PUBLIC_KEYS)

        final_duplicate = client.post(
            f"/api/v1/participant/tasks/{task['id']}/interactions",
            headers=auth(participant),
            json={
                "client_action_id": f"solve-{len(solution)}",
                "action_type": "move",
                "move": solution[-1],
            },
        )
        assert final_duplicate.status_code == 200
        assert final_duplicate.json()["completed"] is True

        after_close = client.post(
            f"/api/v1/participant/tasks/{task['id']}/interactions",
            headers=auth(participant),
            json={
                "client_action_id": "after-close",
                "action_type": "move",
                "move": solution[-1],
            },
        )
        assert after_close.status_code == 409
        assert after_close.json()["detail"]["code"] == "TASK_ALREADY_CLOSED"

        with application.state.database.session_factory() as session:
            stored = session.get(TaskInstance, task["id"])
            assert stored is not None
            assert stored.status == TaskStatus.ANSWERED
            assert stored.evaluation_state["correct"] is True
            assert stored.evaluation_state["rejected_moves"] == 1
            interactions = list(
                session.scalars(
                    select(TaskInteraction)
                    .where(TaskInteraction.task_instance_id == task["id"])
                    .order_by(TaskInteraction.sequence)
                )
            )
            assert len(interactions) == 1 + len(solution)
            assert [item.sequence for item in interactions] == list(
                range(1, len(interactions) + 1)
            )
            events = list(
                session.scalars(
                    select(AttemptEvent).order_by(AttemptEvent.sequence)
                )
            )
            assert [event.event_type for event in events] == [
                "attempt_started",
                "task_generated",
                *[
                    event_type
                    for _ in range(len(interactions))
                    for event_type in (
                        "task_interaction_submitted",
                        "task_interaction_resolved",
                    )
                ],
            ]
            resolved = [
                event
                for event in events
                if event.event_type == "task_interaction_resolved"
            ]
            assert all(
                event.payload["before_state_hash"]
                != event.payload["after_state_hash"]
                for event in resolved
            )


def test_three_goal_chapter_branches_and_starts_a_new_rule(tmp_path):
    application = create_app(_settings(tmp_path / "penultima-chapter.db"))
    with TestClient(application) as client:
        participant = _prepare_participant(client, external_ref="penultima-chapter")
        client.post(
            "/api/v1/participant/attempts/start",
            headers=auth(participant),
        )
        first = client.get(
            "/api/v1/participant/tasks/current",
            headers=auth(participant),
        ).json()["task"]
        first_stored = _stored_task(application, first["id"])
        _solve_task(
            client=client,
            application=application,
            participant=participant,
            task_id=first["id"],
            id_prefix="stage-1",
        )

        second = client.post(
            "/api/v1/participant/tasks/next",
            headers=auth(participant),
        ).json()["task"]
        second_stored = _stored_task(application, second["id"])
        assert second_stored.private_state["generation"]["branch"] == "advance"
        assert (
            second_stored.private_state["generation"]["parent_task_id"]
            == first["id"]
        )
        assert second_stored.private_state["chapter_stage"] == 2
        assert second_stored.private_state["chapter_id"] == (
            first_stored.private_state["chapter_id"]
        )
        assert second_stored.private_state["rule_key"] == (
            first_stored.private_state["rule_key"]
        )
        assert second_stored.private_state["blockers"] == (
            first_stored.private_state["blockers"]
        )
        assert second_stored.private_state["initial_square"] == (
            first_stored.private_state["goal_square"]
        )
        assert second_stored.private_state["initial_shortest_path_length"] > (
            first_stored.private_state["initial_shortest_path_length"]
        )

        rejection_count = (
            second_stored.private_state["initial_shortest_path_length"] + 2
        )
        for index in range(rejection_count):
            current_square = _stored_task(
                application,
                second["id"],
            ).private_state["current_square"]
            rejected = client.post(
                f"/api/v1/participant/tasks/{second['id']}/interactions",
                headers=auth(participant),
                json={
                    "client_action_id": f"noise-{index}",
                    "action_type": "move",
                    "move": f"{current_square}{current_square}",
                },
            )
            assert rejected.status_code == 200
            assert rejected.json()["accepted"] is False
        _solve_task(
            client=client,
            application=application,
            participant=participant,
            task_id=second["id"],
            id_prefix="stage-2",
        )

        third = client.post(
            "/api/v1/participant/tasks/next",
            headers=auth(participant),
        ).json()["task"]
        third_stored = _stored_task(application, third["id"])
        assert third_stored.private_state["generation"]["branch"] == "consolidate"
        assert third_stored.private_state["chapter_stage"] == 3
        assert third_stored.private_state["chapter_id"] == (
            first_stored.private_state["chapter_id"]
        )
        assert third_stored.private_state["rule_key"] == (
            first_stored.private_state["rule_key"]
        )
        assert third_stored.private_state["initial_square"] == (
            second_stored.private_state["goal_square"]
        )
        assert third_stored.public_state["recent_observations"]
        _solve_task(
            client=client,
            application=application,
            participant=participant,
            task_id=third["id"],
            id_prefix="stage-3",
        )

        fourth = client.post(
            "/api/v1/participant/tasks/next",
            headers=auth(participant),
        ).json()["task"]
        fourth_stored = _stored_task(application, fourth["id"])
        assert fourth_stored.private_state["generation"]["branch"] == "new_chapter"
        assert fourth_stored.private_state["chapter_stage"] == 1
        assert fourth_stored.private_state["chapter_id"] != (
            first_stored.private_state["chapter_id"]
        )
        assert fourth_stored.private_state["rule_key"] != (
            first_stored.private_state["rule_key"]
        )

        with application.state.database.session_factory() as session:
            generated_events = list(
                session.scalars(
                    select(AttemptEvent)
                    .where(AttemptEvent.event_type == "task_generated")
                    .order_by(AttemptEvent.sequence)
                )
            )
            assert [event.payload.get("branch") for event in generated_events] == [
                "initial",
                "advance",
                "consolidate",
                "new_chapter",
            ]
            for task, event in zip(
                (first_stored, second_stored, third_stored, fourth_stored),
                generated_events,
            ):
                assert event.payload["context_hash"] == (
                    task.private_state["generation"]["context_hash"]
                )
                assert "rule_key" not in event.payload
                assert "blockers" not in event.payload


def test_skip_remediates_from_exact_position_and_expiry_blocks_moves(tmp_path):
    application = create_app(_settings(tmp_path / "penultima-skip.db"))
    with TestClient(application) as client:
        participant = _prepare_participant(client, external_ref="penultima-skip")
        started = client.post(
            "/api/v1/participant/attempts/start",
            headers=auth(participant),
        ).json()
        task = client.get(
            "/api/v1/participant/tasks/current",
            headers=auth(participant),
        ).json()["task"]
        stored = _stored_task(application, task["id"])
        first_move = stored.private_state["shortest_solution"][0]
        moved = client.post(
            f"/api/v1/participant/tasks/{task['id']}/interactions",
            headers=auth(participant),
            json={
                "client_action_id": "before-skip",
                "action_type": "move",
                "move": first_move,
            },
        )
        assert moved.status_code == 200
        assert moved.json()["completed"] is False
        exact_square = moved.json()["task"]["public_state"]["current_square"]

        skipped = client.post(
            f"/api/v1/participant/tasks/{task['id']}/skip",
            headers=auth(participant),
        )
        assert skipped.status_code == 200
        with application.state.database.session_factory() as session:
            skipped_stored = session.get(TaskInstance, task["id"])
            assert skipped_stored is not None
            assert skipped_stored.evaluation_state["correct"] is False
            assert skipped_stored.evaluation_state["skipped"] is True

        remedial = client.post(
            "/api/v1/participant/tasks/next",
            headers=auth(participant),
        ).json()["task"]
        remedial_stored = _stored_task(application, remedial["id"])
        assert remedial_stored.private_state["generation"]["branch"] == "remediate"
        assert remedial_stored.private_state["initial_square"] == exact_square
        assert remedial_stored.private_state["rule_key"] == stored.private_state["rule_key"]
        assert remedial_stored.private_state["blockers"] == stored.private_state["blockers"]
        assert remedial_stored.private_state["chapter_stage"] == (
            stored.private_state["chapter_stage"]
        )
        assert 1 <= remedial_stored.private_state["initial_shortest_path_length"] <= 2
        assert remedial_stored.public_state["recent_observations"]

        with application.state.database.session_factory() as session:
            attempt = session.get(Attempt, started["attempt"]["id"])
            assert attempt is not None
            attempt.deadline_at = utc_now() - timedelta(seconds=1)
            session.commit()

        rejected = client.post(
            f"/api/v1/participant/tasks/{remedial['id']}/interactions",
            headers=auth(participant),
            json={
                "client_action_id": "too-late",
                "action_type": "move",
                "move": remedial_stored.private_state["shortest_solution"][0],
            },
        )
        assert rejected.status_code == 409
        assert rejected.json()["detail"]["code"] == "ACTIVE_ATTEMPT_REQUIRED"
        with application.state.database.session_factory() as session:
            attempt = session.get(Attempt, started["attempt"]["id"])
            assert attempt is not None
            assert attempt.status == AttemptStatus.EXPIRED
            assert session.scalar(
                select(func.count(TaskInteraction.id)).where(
                    TaskInteraction.task_instance_id == remedial["id"]
                )
            ) == 0
            assert session.scalar(
                select(func.count(AttemptEvent.id)).where(
                    AttemptEvent.attempt_id == attempt.id,
                    AttemptEvent.event_type == "attempt_expired",
                )
            ) == 1
