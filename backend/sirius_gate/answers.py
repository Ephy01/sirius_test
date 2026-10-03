"""Reading the answer a participant typed."""

from app.tasks.answers import parse_integer as integer
from app.tasks.answers import strip_answer_command as text

__all__ = ['integer', 'text']
