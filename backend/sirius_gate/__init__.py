"""Public interface of the platform for task modules.

A module imports everything it needs from here::

    from sirius_gate import FamilyCard, TaskFamily, blocks

Names exported from this package keep their meaning within one ``API`` version.
"""

from app.tasks.answers import strip_answer_command
from app.tasks.family import FamilyCard, State, TaskFamily, Transition, Variant, optional_text, required_text
from app.tasks.modules import API_VERSION

from . import blocks

API = API_VERSION

__all__ = [
    'API',
    'FamilyCard',
    'State',
    'TaskFamily',
    'Transition',
    'Variant',
    'blocks',
    'optional_text',
    'required_text',
    'strip_answer_command',
]
