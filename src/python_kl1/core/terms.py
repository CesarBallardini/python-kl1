"""Logic-value types and the ``Value`` alias.

A **logic value** (:data:`Value`) is what a variable can be bound to and what flows
through streams: another :class:`~python_kl1.core.logicvar.Var`, a compound
:class:`Cons` cell, the empty-list marker :data:`NIL`, or an :data:`Atom` (a plain
Python scalar used as a KL1 constant). Keeping this an explicit union -- rather than
``object`` -- lets the type checkers follow values end to end.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from python_kl1.core.logicvar import Var


type Atom = int | float | str | bool | None
"""An atomic logic value: a scalar Python constant (KL1 integer, float, atom, string)."""


@dataclass(frozen=True, slots=True)
class Cons:
    """A stream/list cell: a ``head`` value and a ``tail`` (a stream Var, Cons, or NIL)."""

    head: Value
    tail: Value


@dataclass(frozen=True, slots=True)
class Struct:
    """A compound term (functor): a ``name`` applied to ``args``, e.g. ``deposit(100)``.

    Two structs unify only when their names and arities match and their arguments
    unify pairwise -- the KL1 ``f(A, B)`` term. Use it for tagged messages and records
    (``Cons`` is the specialised functor for lists/streams).
    """

    name: str
    args: tuple[Value, ...]


class Nil:
    """The empty-stream / end-of-list type. Use the singleton :data:`NIL`."""

    __slots__ = ()

    def __repr__(self) -> str:
        """Render as ``NIL``."""
        return 'NIL'


NIL = Nil()
"""The single end-of-stream marker (like Prolog's ``[]``)."""


type Value = Var | Cons | Struct | Nil | Atom
"""Anything a logic variable can hold: a variable, a cons cell, a struct, NIL, or an atom."""
