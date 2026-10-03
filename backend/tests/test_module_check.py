from __future__ import annotations

from task_module_samples import PLUS_ONE

from app.tasks import FAMILIES
from sirius_gate import check

WITH_REFERENCE = PLUS_ONE.replace(
    '    evaluate=evaluate,\n',
    '    evaluate=evaluate,\n    reference_answer=lambda private_state: (str(private_state["answer"]), []),\n',
)


def _write(directory, source):
    (directory / 'plus_one.py').write_text(source, encoding='utf-8')


def test_check_accepts_a_sound_module_and_reports_how_guessable_it_is(tmp_path, capsys):
    _write(tmp_path, WITH_REFERENCE)

    assert check.main([str(tmp_path), '--seeds', '14']) == 0

    output = capsys.readouterr().out
    assert 'plus_one (Плюс один), версия plus-one-v1' in output
    assert 'Ошибок нет.' in output
    levels = check.check_family(FAMILIES['plus_one'], seeds=14)
    assert [level.generated for level in levels] == [14] * 5
    assert [level.reference_accepted for level in levels] == [14] * 5
    assert all(level.distinct == 7 and level.top_answer_share == 2 / 14 for level in levels)


def test_check_reports_a_reference_answer_that_is_not_accepted(tmp_path, capsys):
    _write(tmp_path, WITH_REFERENCE.replace('(str(private_state["answer"]), [])', '("0", [])'))

    assert check.main([str(tmp_path), '--seeds', '5']) == 1

    output = capsys.readouterr().out
    assert 'эталонное решение не засчитано' in output
    assert 'Есть ошибки.' in output


def test_check_reports_an_evaluator_that_accepts_an_empty_answer(tmp_path, capsys):
    _write(tmp_path, PLUS_ONE.replace('answer.strip() == str(private_state["answer"])', 'True'))

    assert check.main([str(tmp_path), 'plus_one', '--seeds', '3']) == 1
    assert "ответ '' засчитан как верный" in capsys.readouterr().out


def test_check_reports_a_module_that_does_not_load(tmp_path, capsys):
    _write(tmp_path, 'VALUE = 1\n')

    assert check.main([str(tmp_path)]) == 1
    assert 'plus_one: не загружен.' in capsys.readouterr().out


def test_reference_solutions_of_every_builtin_family_pass_the_check():
    for family in FAMILIES.values():
        levels = check.check_family(family, seeds=3)

        assert [level.reference_accepted for level in levels] == [3] * 5, family.key
        assert all(not level.problems for level in levels), family.key
