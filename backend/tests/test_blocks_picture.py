"""The picture block: a drawing a plugin describes with the shapes named in the hackathon brief."""

from __future__ import annotations

import json

import pytest

from sirius_gate import blocks


def _picture():
    return blocks.picture(
        [
            blocks.polygon([(1, 1), (5, 1), (3, 4)], tone='accent'),
            blocks.point(1, 1, label='A', command='/op pick:A'),
            blocks.line(0, 0, 6, 0, dashed=True),
            blocks.circle(3, 2, 1),
            blocks.ellipse(3, 2, 2, 1, filled=True),
            blocks.sector(3, 2, 1, 0, 90),
            blocks.arc(3, 2, 1.5, 90, 180),
            blocks.label(3, 5, 'подпись'),
        ],
        x=(0, 6),
        y=(-1, 6),
        grid=True,
        caption='Чертёж',
    )


def test_picture_is_plain_data_with_every_shape_of_the_brief():
    picture = _picture()

    assert json.loads(json.dumps(picture, allow_nan=False)) == picture
    assert {key: value for key, value in picture.items() if key != 'shapes'} == {
        'type': 'picture',
        'x': [0, 6],
        'y': [-1, 6],
        'grid': True,
        'snap': 1,
        'caption': 'Чертёж',
    }
    assert {shape['shape'] for shape in picture['shapes']} == set(blocks.SHAPES)
    assert picture['shapes'][1] == {
        'shape': 'point',
        'x': 1,
        'y': 1,
        'label': 'A',
        'tone': 'accent',
        'command': '/op pick:A',
        'drag': None,
    }
    assert picture['shapes'][0]['points'] == [[1, 1], [5, 1], [3, 4]]


def test_language_model_gets_the_shapes_without_the_commands_behind_them():
    told = blocks.for_assistant(blocks.scene('Условие', [_picture()]))

    shapes = told['blocks'][0]['shapes']
    assert len(shapes) == 8
    assert all('command' not in shape and 'drag' not in shape for shape in shapes)
    assert shapes[1] == {'shape': 'point', 'x': 1, 'y': 1, 'label': 'A', 'tone': 'accent'}


@pytest.mark.parametrize(
    ('build', 'expected'),
    [
        (lambda: blocks.circle(0, 0, 0), 'radius должно быть больше нуля'),
        (lambda: blocks.ellipse(0, 0, 1, -1), 'radius_y должно быть больше нуля'),
        (lambda: blocks.polygon([(0, 0), (1, 1)]), 'не меньше трёх вершин'),
        (lambda: blocks.point('a', 1), 'x должно быть числом'),
        (lambda: blocks.line(0, 0, float('nan'), 1), 'x2 должно быть числом'),
        (lambda: blocks.point(0, 0, tone='red'), 'оттенок должен быть одним из'),
        (lambda: blocks.point(0, 0, command='pick'), 'должна начинаться с "/"'),
        (lambda: blocks.picture([{'shape': 'star'}]), 'рисунок собирается из фигур'),
        (lambda: blocks.picture([], x=(3, 3)), 'левая граница должна быть меньше правой'),
        (lambda: blocks.picture([], snap=0), 'snap должно быть больше нуля'),
        (lambda: blocks.point(0, 0, drag='точка D'), 'имя переносимого объекта'),
    ],
)
def test_shape_the_client_could_not_draw_is_refused_when_it_is_built(build, expected):
    with pytest.raises(ValueError, match=expected):
        build()
