"""What the text of a plugin may use is checked before the plugin is run."""

from __future__ import annotations

import pytest
from task_module_samples import COUNT_UP

from sirius_gate.loading import load_directory, load_source


@pytest.mark.parametrize(
    ('line', 'expected'),
    [
        ('import os', 'модуль os в плагине использовать нельзя'),
        ('from urllib.request import urlopen', 'модуль urllib.request в плагине использовать нельзя'),
        ('import app.models', 'модуль app.models в плагине использовать нельзя'),
        ('DATA = open("notes.txt")', 'функцию open в плагине использовать нельзя'),
        ('RUN = eval', 'функцию eval в плагине использовать нельзя'),
        ('KIND = (1).__class__', 'имя __class__ в плагине использовать нельзя'),
    ],
)
def test_plugin_that_reaches_outside_the_platform_is_refused(line, expected):
    module = load_source(f'{line}\n{COUNT_UP}', name='counting')

    assert module.families == ()
    assert module.error == f'{module.error.splitlines()[0]}\ncounting.py, строка 1'
    assert expected in module.error


def test_standard_modules_for_mathematics_are_allowed():
    source = 'import math\nfrom fractions import Fraction\nfrom itertools import product\n' + COUNT_UP

    module = load_source(source, name='counting')

    assert module.error is None


def test_every_file_of_a_plugin_folder_is_checked(tmp_path):
    folder = tmp_path / 'counting'
    folder.mkdir()
    (folder / 'helper.py').write_text('import socket\n\nLIMIT = 3\n', encoding='utf-8')
    (folder / 'task.py').write_text('from .helper import LIMIT\n' + COUNT_UP, encoding='utf-8')

    (module,) = load_directory(tmp_path)

    assert module.families == ()
    assert 'модуль socket в плагине использовать нельзя' in module.error
    assert 'helper.py, строка 1' in module.error
