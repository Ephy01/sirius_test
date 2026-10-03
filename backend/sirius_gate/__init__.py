"""Public interface of the platform for task modules.

A module imports everything it needs from here::

    from sirius_gate import FamilyCard, TaskFamily, answers, blocks

Names exported from this package keep their meaning within one ``API`` version.
"""

from app.tasks.family import FamilyCard, State, TaskFamily, Transition, Variant, optional_text, required_text
from app.tasks.modules import API_VERSION

from . import answers, blocks

API = API_VERSION

__all__ = [
    'API',
    'FamilyCard',
    'State',
    'TaskFamily',
    'Transition',
    'Variant',
    'answers',
    'blocks',
    'optional_text',
    'required_text',
]
