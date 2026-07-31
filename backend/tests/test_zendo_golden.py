"""Byte-for-byte reproducibility lock for the geo_zendo v2 generator.

The fixture was captured before the Universe-protocol refactoring of the
zendo core. Any change to ``core/rule_dsl``, ``core/rule_space`` or the
engine itself must keep these one hundred cases identical, because stored
attempts replay tasks by ``(seed, difficulty, generator_version)``.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.environments.geometry_world.zendo_v2 import (
    GENERATOR_VERSION,
    generate_geo_zendo_v2_task,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "geo_zendo_v2_golden.json"


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def test_geo_zendo_v2_reproduces_golden_fixture_byte_for_byte():
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert payload["generator_version"] == GENERATOR_VERSION
    cases = payload["cases"]
    assert len(cases) == 100

    for case in cases:
        public, private = generate_geo_zendo_v2_task(
            seed=case["seed"],
            difficulty=case["difficulty"],
        )
        assert _canonical(public) == _canonical(case["public_state"]), (
            f"public_state diverged for seed={case['seed']} "
            f"difficulty={case['difficulty']}"
        )
        assert _canonical(private) == _canonical(case["private_state"]), (
            f"private_state diverged for seed={case['seed']} "
            f"difficulty={case['difficulty']}"
        )
