from fractions import Fraction

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import Settings
from app.main import create_app
from app.models import Attempt, AttemptEvent, Contest, TaskInstance
from app.tasks import evaluate_task
from app.tasks.dice_chess import FAMILY_KEY as DICE_CHESS_FAMILY
from app.tasks.dice_chess import GENERATOR_VERSION as DICE_CHESS_GENERATOR_VERSION
from app.tasks.dice_chess.probability import parse_probability_answer


def auth(token: str) -> dict[str, str]:
    return {'Authorization': f'Bearer {token}'}


def _settings(database_path) -> Settings:
    return Settings(
        database_url=f'sqlite:///{database_path}',
        organizer_code='ORBIT-ADMIN',
        security_secret='test-token-secret-that-is-long',
        code_hmac_secret='test-code-secret-that-is-different',
    )


def _prepare_participant(client: TestClient, *, task_config: dict, external_ref: str) -> str:
    organizer = client.post('/api/v1/access/redeem', json={'code': 'ORBIT-ADMIN'}).json()['access_token']
    contest = client.post(
        '/api/v1/contests',
        headers=auth(organizer),
        json={'title': 'Шахматный мир', 'task_config': task_config},
    ).json()
    client.post(
        f'/api/v1/contests/{contest["id"]}/enrollments',
        headers=auth(organizer),
        json={'participants': [{'external_ref': external_ref, 'display_name': 'Участник'}]},
    )
    code = client.post(f'/api/v1/contests/{contest["id"]}/codes', headers=auth(organizer), json={}).json()[
        'items'
    ][0]['code']
    client.post(f'/api/v1/contests/{contest["id"]}/publish', headers=auth(organizer))
    return client.post('/api/v1/access/redeem', json={'code': code}).json()['access_token']


@pytest.mark.parametrize(
    ('answer', 'expected'),
    [
        ('1/3', Fraction(1, 3)),
        ('2 / 6', Fraction(1, 3)),
        ('0.333', Fraction(333, 1000)),
        ('0,333', Fraction(333, 1000)),
        ('33,3%', Fraction(333, 1000)),
        ('Вероятность равна 50 %', Fraction(1, 2)),
        ('После расчёта 36 исходов получил 0,5', Fraction(1, 2)),
        ('.25', Fraction(1, 4)),
        ('1/0', None),
        ('ответ неизвестен', None),
    ],
)
def test_probability_answer_parser(answer: str, expected: Fraction | None):
    assert parse_probability_answer(answer) == expected


@pytest.mark.parametrize(
    ('answer', 'correct'),
    [
        ('1/3', True),
        ('0,333', True),
        ('33%', True),
        ('0.32', False),
        ('40%', False),
        ('150%', False),
        ('не знаю', False),
    ],
)
def test_probability_evaluator_uses_reasonable_tolerance(answer: str, correct: bool):
    evaluation = evaluate_task(
        family=DICE_CHESS_FAMILY,
        generator_version=DICE_CHESS_GENERATOR_VERSION,
        answer=answer,
        private_state={'probability': {'numerator': 1, 'denominator': 3}},
    )
    assert evaluation['correct'] is correct


def test_dice_task_api_does_not_leak_exact_answer(tmp_path):
    application = create_app(_settings(tmp_path / 'dice-api.db'))
    with TestClient(application) as client:
        participant = _prepare_participant(
            client,
            external_ref='dice-only',
            task_config={
                'families': [
                    {
                        'key': 'dice_chess',
                        'enabled': True,
                        'weight': 1,
                        'initial_difficulty': 1,
                        'max_difficulty': 7,
                    }
                ]
            },
        )
        client.post('/api/v1/participant/attempts/start', headers=auth(participant))
        task = client.get('/api/v1/participant/tasks/current', headers=auth(participant)).json()['task']

        assert task['family'] == 'dice_chess'
        assert task['generator_version'] == 'dice-chess-world-v3'
        assert set(task['public_state']) == {
            'kind',
            'prompt',
            'board',
            'die',
            'sample_space_size',
            'event_description',
            'response_hint',
        }
        assert task['public_state']['kind'] == 'dice_chess_board_inventory_probability'
        assert 'seed' not in task
        assert 'probability' not in task['public_state']

        with application.state.database.session_factory() as session:
            stored = session.get(TaskInstance, task['id'])
            assert stored is not None
            exact = stored.private_state['probability']
            answer = f'{exact["numerator"]}/{exact["denominator"]}'

        response = client.post(
            f'/api/v1/participant/tasks/{task["id"]}/answer',
            headers=auth(participant),
            json={'answer': answer},
        )
        assert response.status_code == 200
        body = response.json()
        assert set(body) == {'task', 'message'}
        assert 'private_state' not in body['task']
        assert 'evaluation_state' not in body['task']
        assert 'participant_answer' not in body['task']
        assert 'correct' not in body
        assert 'probability' not in body['task']['public_state']

        with application.state.database.session_factory() as session:
            stored = session.get(TaskInstance, task['id'])
            assert stored is not None
            assert stored.evaluation_state['correct'] is True
            events = list(session.scalars(select(AttemptEvent).order_by(AttemptEvent.sequence)).all())
            assert [event.event_type for event in events] == [
                'attempt_started',
                'task_generated',
                'answer_submitted',
                'answer_evaluated',
            ]


def test_dice_position_task_flows_through_participant_api(tmp_path):
    application = create_app(_settings(tmp_path / 'dice-position-api.db'))
    with TestClient(application) as client:
        participant = _prepare_participant(
            client,
            external_ref='dice-position',
            task_config={
                'families': [
                    {
                        'key': 'dice_chess',
                        'enabled': True,
                        'weight': 1,
                        'initial_difficulty': 4,
                        'max_difficulty': 8,
                    }
                ]
            },
        )
        client.post('/api/v1/participant/attempts/start', headers=auth(participant))
        task = client.get('/api/v1/participant/tasks/current', headers=auth(participant)).json()['task']

        assert task['family'] == 'dice_chess'
        assert task['generator_version'] == 'dice-chess-world-v3'
        assert task['difficulty'] == 4
        assert set(task['public_state']) == {
            'kind',
            'prompt',
            'board',
            'side_to_move',
            'die',
            'sample_space_size',
            'event_description',
            'response_hint',
        }
        assert task['public_state']['kind'] == 'dice_chess_position_probability'
        assert len(task['public_state']['board']) == 8
        assert all(len(row) == 8 for row in task['public_state']['board'])
        assert len(task['public_state']['die']['faces']) == 6
        assert task['public_state']['sample_space_size'] == 6
        assert 'probability' not in task['public_state']
        assert 'eligible_piece_types' not in task['public_state']
        assert 'seed' not in task

        with application.state.database.session_factory() as session:
            stored = session.get(TaskInstance, task['id'])
            assert stored is not None
            assert stored.private_state['mission_variant'] == 'legal_position_probability'
            exact = stored.private_state['probability']
            answer = f'{exact["numerator"]}/{exact["denominator"]}'

        answered = client.post(
            f'/api/v1/participant/tasks/{task["id"]}/answer',
            headers=auth(participant),
            json={'answer': answer},
        )
        assert answered.status_code == 200
        assert answered.json()['task']['status'] == 'answered'
        assert 'correct' not in answered.json()

        with application.state.database.session_factory() as session:
            stored = session.get(TaskInstance, task['id'])
            assert stored is not None
            assert stored.evaluation_state['correct'] is True


def test_legacy_family_list_remains_usable(tmp_path):
    application = create_app(_settings(tmp_path / 'legacy-families.db'))
    with TestClient(application) as client:
        participant = _prepare_participant(
            client, external_ref='legacy', task_config={'families': ['dice-chess', 'machine-reach']}
        )
        client.post('/api/v1/participant/attempts/start', headers=auth(participant))
        task = client.get('/api/v1/participant/tasks/current', headers=auth(participant)).json()['task']
        assert task['family'] in {'dice_chess', 'machine_reach'}
        assert task['difficulty'] == 1


def _run_mixed_sequence(database_path) -> tuple[list[str], list[int]]:
    application = create_app(_settings(database_path))
    with TestClient(application) as client:
        participant = _prepare_participant(
            client,
            external_ref='mixed',
            task_config={
                'adaptation_threshold': 2,
                'families': [
                    {
                        'key': 'geo_transform',
                        'enabled': True,
                        'weight': 1,
                        'initial_difficulty': 1,
                        'max_difficulty': 5,
                    },
                    {
                        'key': 'dice_chess',
                        'enabled': True,
                        'weight': 3,
                        'initial_difficulty': 3,
                        'max_difficulty': 5,
                    },
                ],
            },
        )
        with application.state.database.session_factory() as session:
            contest = session.scalar(select(Contest))
            assert contest is not None
            contest.task_config = {
                **contest.task_config,
                'families': [
                    *contest.task_config['families'],
                    {
                        'key': 'future_family',
                        'enabled': True,
                        'weight': 100,
                        'initial_difficulty': 1,
                        'max_difficulty': 10,
                    },
                ],
            }
            session.commit()
        started = client.post('/api/v1/participant/attempts/start', headers=auth(participant))
        attempt_id = started.json()['attempt']['id']
        with application.state.database.session_factory() as session:
            attempt = session.get(Attempt, attempt_id)
            assert attempt is not None
            attempt.seed = 424_242
            session.commit()

        families: list[str] = []
        difficulties: list[int] = []
        seen = {'geo_transform': 0, 'dice_chess': 0}
        initial = {'geo_transform': 1, 'dice_chess': 3}
        maximum = {'geo_transform': 5, 'dice_chess': 5}

        for ordinal in range(1, 25):
            endpoint = (
                '/api/v1/participant/tasks/current' if ordinal == 1 else '/api/v1/participant/tasks/next'
            )
            request = (
                client.get(endpoint, headers=auth(participant))
                if ordinal == 1
                else client.post(endpoint, headers=auth(participant))
            )
            task = request.json()['task']
            family = task['family']
            assert family in seen
            assert task['difficulty'] == min(maximum[family], initial[family] + seen[family] // 2)
            families.append(family)
            difficulties.append(task['difficulty'])

            with application.state.database.session_factory() as session:
                stored = session.get(TaskInstance, task['id'])
                assert stored is not None
                if family == 'geo_transform':
                    answer = str(stored.private_state['correct_card_id'])
                else:
                    probability = stored.private_state['probability']
                    answer = f'{probability["numerator"]}/{probability["denominator"]}'

            answered = client.post(
                f'/api/v1/participant/tasks/{task["id"]}/answer',
                headers=auth(participant),
                json={'answer': answer},
            )
            assert answered.status_code == 200
            seen[family] += 1

        with application.state.database.session_factory() as session:
            events = list(session.scalars(select(AttemptEvent).order_by(AttemptEvent.sequence)).all())
            assert len(events) == 1 + 24 * 3
            generated_events = [event for event in events if event.event_type == 'task_generated']
            assert [event.payload['family'] for event in generated_events] == families
            assert all(
                event.payload['family_route_version'] == 'weighted-family-route-v1'
                for event in generated_events
            )
    return families, difficulties


def test_weighted_mixed_route_is_reproducible_and_adapts_per_family(tmp_path):
    first_families, first_difficulties = _run_mixed_sequence(tmp_path / 'mixed-first.db')
    second_families, second_difficulties = _run_mixed_sequence(tmp_path / 'mixed-second.db')

    assert first_families == second_families
    assert first_difficulties == second_difficulties
    assert set(first_families) == {'geo_transform', 'dice_chess'}
    assert all(
        current != previous for previous, current in zip(first_families, first_families[1:], strict=False)
    )
    assert first_families.count('dice_chess') == first_families.count('geo_transform')
