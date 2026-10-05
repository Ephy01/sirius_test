"""How a family is described to the contest builder and to the author sandbox."""

from __future__ import annotations

from .family import MAX_DIFFICULTY, MIN_DIFFICULTY, FamilyCard, State, TaskFamily, Variant


def describe(family: TaskFamily, module: str | None = None) -> State:
    """Catalog entry of a family; ``module`` names the task module it came from."""

    card = family.card or FamilyCard(title=family.key)
    variants = [(key, card.variants.get(key, Variant(key))) for key in family.sub_kinds]
    return {
        'key': family.key,
        'title': card.title,
        'description': card.description,
        'version': family.version,
        'source': 'module' if module else 'builtin',
        'module': module,
        'listed': card.listed and not family.scripted_only,
        'scripted_only': family.scripted_only,
        'interactive': bool(family.actions),
        'default_weight': card.weight,
        'default_skin': card.skin,
        'min_difficulty': MIN_DIFFICULTY,
        'max_difficulty': MAX_DIFFICULTY,
        'variants': [
            {'key': key, 'title': variant.title, 'description': variant.description}
            for key, variant in variants
        ],
    }
