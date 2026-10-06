"""Checks a task module the way the platform will use it and prints a report for its author.

    python -m sirius_gate.check <modules directory> [module name] [--seeds 40]

For every family and difficulty it generates tasks for many seeds and verifies
that generation is reproducible, that the reference answer is accepted (playing
the reference commands first) and that an empty answer is not. A level with few
distinct tasks or with one answer that fits most of them gets a remark.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .family import MIN_DIFFICULTY, TaskFamily
from .loading import load_directory

ACTION_OF_COMMAND = {'/op': 'apply_op', '/test': 'probe', '/hint': 'hint', '/undo': 'undo', '/reset': 'reset'}
PAYLOAD_KEY = {'apply_op': 'op_id', 'probe': 'probe'}
WRONG_ANSWERS = ('', 'не знаю')
FEW_TASKS_SHARE = 0.5
GUESSABLE_SHARE = 0.5


@dataclass
class LevelReport:
    difficulty: int
    generated: int = 0
    slowest_seconds: float = 0.0
    distinct: int = 0
    reference_accepted: int | None = None
    top_answer_share: float | None = None
    problems: list[str] = field(default_factory=list)
    remarks: list[str] = field(default_factory=list)


def _reference_verdict(family: TaskFamily, public_state: dict, private_state: dict) -> dict:
    """Evaluation the platform gives to the reference solution.

    The reference is an answer and a list of chat commands. Commands are played in
    order: an action changes the state, ``/answer ...`` or a bare word is the answer.
    Without an answer among the commands the reference answer itself is submitted.
    """

    answer, commands = family.reference_answer(private_state)
    for number, command in enumerate(commands, start=1):
        name, _, argument = command.strip().partition(' ')
        if name == '/answer' or not name.startswith('/'):
            return family.evaluate(command, private_state)
        action = family.actions.get(ACTION_OF_COMMAND.get(name, ''))
        if action is None:
            raise ValueError(f'эталонная команда {command!r} не поддерживается задачей')
        key = PAYLOAD_KEY.get(ACTION_OF_COMMAND[name])
        payload = {'client_action_id': f'check-{number}', 'first_action_latency_ms': 0}
        transition = action(
            {**payload, key: argument.strip()} if key else payload, public_state, private_state
        )
        if not transition.accepted:
            raise ValueError(f'эталонная команда {command!r} отклонена: {transition.message}')
        if transition.completed:
            return transition.evaluation_state or {}
        public_state, private_state = transition.public_state, transition.private_state
    return family.evaluate(answer, private_state)


def _check_task(
    family: TaskFamily, seed: int, difficulty: int, context: dict, report: LevelReport
) -> str | None:
    """Checks one generated task; returns its reference answer when the task is answered in one message."""

    started = time.perf_counter()
    public_state, private_state = family.generate(seed, difficulty, context)
    report.slowest_seconds = max(report.slowest_seconds, time.perf_counter() - started)
    if json.dumps(family.generate(seed, difficulty, context), ensure_ascii=False) != json.dumps(
        (public_state, private_state), ensure_ascii=False
    ):
        raise ValueError('одинаковый seed дал разные задачи')
    for wrong in WRONG_ANSWERS:
        if family.evaluate(wrong, private_state).get('correct') is True:
            raise ValueError(f'ответ {wrong!r} засчитан как верный')
    if family.reference_answer is None:
        return None
    if _reference_verdict(family, public_state, private_state).get('correct') is not True:
        raise ValueError('эталонное решение не засчитано')
    report.reference_accepted = (report.reference_accepted or 0) + 1
    answer, commands = family.reference_answer(private_state)
    return answer if not commands else None


def _remarks(report: LevelReport) -> list[str]:
    remarks = []
    if report.distinct < report.generated * FEW_TASKS_SHARE:
        remarks.append(f'разных задач мало: {report.distinct} из {report.generated}')
    if report.top_answer_share is not None and report.top_answer_share > GUESSABLE_SHARE:
        remarks.append(f'один ответ подходит к {report.top_answer_share:.0%} задач, его можно угадать')
    return remarks


def check_level(family: TaskFamily, difficulty: int, seeds: int, context: dict | None = None) -> LevelReport:
    report = LevelReport(difficulty=difficulty)
    tasks: set[str] = set()
    answers: Counter[str] = Counter()
    for seed in range(1, seeds + 1):
        try:
            answer = _check_task(family, seed, difficulty, context or {}, report)
            public_state, _private = family.generate(seed, difficulty, context or {})
        except Exception as error:
            if len(report.problems) < 3:
                report.problems.append(f'seed {seed}: {type(error).__name__}: {error}')
            continue
        report.generated += 1
        tasks.add(json.dumps(public_state, ensure_ascii=False, sort_keys=True))
        if answer is not None:
            answers[answer] += 1
    report.distinct = len(tasks)
    if answers:
        report.top_answer_share = answers.most_common(1)[0][1] / sum(answers.values())
    report.remarks = _remarks(report)
    return report


def check_family(family: TaskFamily, seeds: int = 40) -> list[LevelReport]:
    context = {'sub_kinds': [family.sub_kinds[0]]} if family.scripted_only and family.sub_kinds else None
    levels = range(MIN_DIFFICULTY, family.max_difficulty + 1)
    return [check_level(family, difficulty, seeds, context) for difficulty in levels]


def _level_name(family: TaskFamily, difficulty: int) -> str:
    titles = family.level_titles
    return titles[difficulty - MIN_DIFFICULTY] if titles else str(difficulty)


def render(family: TaskFamily, levels: list[LevelReport], seeds: int) -> str:
    title = family.card.title if family.card else family.key
    names = [_level_name(family, level.difficulty) for level in levels]
    width = max(len('сложность'), *map(len, names))
    lines = [
        f'{family.key} ({title}), версия {family.version}',
        f'  {"сложность":<{width}}  создано  разных  эталон принят  самый частый ответ  дольше всего',
    ]
    for name, level in zip(names, levels, strict=True):
        reference = '—' if level.reference_accepted is None else f'{level.reference_accepted}/{seeds}'
        share = '—' if level.top_answer_share is None else f'{level.top_answer_share:.0%}'
        lines.append(
            f'  {name:<{width}}  {level.generated:>3}/{seeds:<3}  {level.distinct:^6}  {reference:^13}'
            f'  {share:^18}  {level.slowest_seconds * 1000:>7.0f} мс'
        )
        lines.extend(f'      ошибка: {problem}' for problem in level.problems)
        lines.extend(f'      замечание: {remark}' for remark in level.remarks)
    return '\n'.join(lines)


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='python -m sirius_gate.check', description='Проверка модулей задач')
    parser.add_argument('directory', help='папка с модулями')
    parser.add_argument('module', nargs='?', help='имя одного модуля, по умолчанию проверяются все')
    parser.add_argument('--seeds', type=int, default=40, help='сколько вариантов создать на каждой сложности')
    options = parser.parse_args(arguments)

    directory = Path(options.directory).expanduser()
    if not directory.is_dir():
        print(f'Папки {directory} нет.')
        return 1
    failed = remarked = False
    for module in load_directory(directory):
        if options.module and module.name != options.module:
            continue
        if module.error:
            print(f'{module.name}: не загружен. {module.error}\n')
            failed = True
            continue
        for family in module.families:
            levels = check_family(family, options.seeds)
            failed = failed or any(level.problems for level in levels)
            remarked = remarked or any(level.remarks for level in levels)
            print(render(family, levels, options.seeds), end='\n\n')
    print('Есть ошибки.' if failed else 'Ошибок нет, есть замечания.' if remarked else 'Ошибок нет.')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
