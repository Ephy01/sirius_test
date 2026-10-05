"""Public interface of the platform for task modules.

A module imports everything it needs from here::

    from sirius_gate import FamilyCard, TaskFamily, answers, blocks

Names exported from this package keep their meaning within one ``API`` version.
The package depends on the standard library only, so the same files run on the
server, in a terminal and in the browser of a task author.
"""

from . import answers, blocks
from .family import FamilyCard, State, TaskFamily, Transition, Variant, optional_text, required_text

API = 1

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
