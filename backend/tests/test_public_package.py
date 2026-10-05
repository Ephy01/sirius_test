"""The ``sirius_gate`` package on its own: it also runs in a terminal and in a browser."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from task_module_samples import PLUS_ONE

from sirius_gate import sandbox
from sirius_gate.loading import load_source

BACKEND = str(Path(__file__).resolve().parents[1])

STANDALONE = """
import sys
sys.path.insert(0, {backend!r})
sys.modules['app'] = None
from sirius_gate import sandbox
from sirius_gate.catalog import describe
from sirius_gate.check import check_family
from sirius_gate.loading import load_source

family = load_source({source!r}).families[0]
task = sandbox.generate(family, seed=3, difficulty=2)
checked = sandbox.answer(family, answer='6', state=task['state'])
print(describe(family)['title'], checked['evaluation']['correct'], len(check_family(family, seeds=3)))
"""


def test_package_needs_neither_the_platform_nor_installed_libraries():
    script = STANDALONE.format(backend=BACKEND, source=PLUS_ONE)

    result = subprocess.run([sys.executable, '-I', '-S', '-c', script], capture_output=True, text=True)

    assert result.stdout.split('\n')[0] == 'Плюс один True 5', result.stderr


def test_module_text_is_loaded_and_played_without_files():
    module = load_source(PLUS_ONE, name='plus_one')

    assert (module.error, [family.key for family in module.families]) == (None, ['plus_one'])
    task = sandbox.generate(module.families[0], seed=3, difficulty=2)
    assert task['public_state']['prompt'] == 'Сколько будет 5 + 1?'
    assert sandbox.answer(module.families[0], answer='7', state=task['state']) == {
        'evaluation': {'correct': False},
        'finalized': True,
    }


def test_error_in_task_code_names_the_line_of_the_module():
    source = PLUS_ONE.replace(
        '    return {"correct":', '    private_state["missing"]\n    return {"correct":'
    )
    line = source.splitlines().index('    private_state["missing"]') + 1
    family = load_source(source, name='plus_one').families[0]
    task = sandbox.generate(family, seed=3)

    with pytest.raises(sandbox.TaskCodeFailed) as failure:
        sandbox.answer(family, answer='1', state=task['state'])

    assert str(failure.value) == f"KeyError: 'missing'\nplus_one.py, строка {line}, функция evaluate"


@pytest.mark.parametrize(
    ('source', 'expected'),
    [
        ('def broken(:\n', 'task.py, строка 1'),
        ('VALUE = 1 / 0\n', 'ZeroDivisionError: division by zero\ntask.py, строка 1, функция <module>'),
        ('VALUE = 1\n', 'must define FAMILY'),
    ],
)
def test_module_text_that_fails_to_load_is_explained(source, expected):
    module = load_source(source)

    assert module.families == ()
    assert expected in module.error
