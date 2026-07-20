"""Single-assignment logic variables -- the one synchronization primitive.

A :class:`Var` is *write-once*: it starts unbound and can be bound at most once,
by unification. Binding a variable is both the sole act of communication between
concurrent goals and the sole wake-up signal: every goal that suspended on a
variable is woken when it becomes bound.

Reading a term always goes through :func:`deref`, which follows the union-find
forwarding chain to the representative value (or the unbound representative Var).
Bindings are made only through :func:`unify` (KL1 *tell*); ``Var.ref`` is never
mutated directly by callers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from python_kl1.core.terms import Cons, Struct

if TYPE_CHECKING:
    from collections.abc import Callable

    from python_kl1.core.terms import Value


class UnificationError(Exception):
    """Raised when two incompatible terms are unified (a binding clash)."""


class Var:
    """A write-once logic variable with a wake-list of suspended callbacks.

    A variable is *unbound* when ``ref is None`` and *forwarded* otherwise --
    ``ref`` then points at another value or Var (union-find). Never read ``ref``
    directly; use :func:`deref`. Never assign it directly; use :func:`unify`.
    """

    __slots__ = ('ref', 'waiters')

    def __init__(self) -> None:
        """Create a fresh unbound variable with an empty wake-list."""
        self.ref: Value | None = None
        self.waiters: list[Callable[[], None]] = []

    def __repr__(self) -> str:
        """Show the bound value, or a stable identity for an unbound variable."""
        term = deref(self)
        if term is self:
            return f'Var(_{id(self) & 0xFFFFFF:06x})'
        return f'Var(={term!r})'


def deref(term: Value) -> Value:
    """Follow the forwarding chain to a representative value or unbound :class:`Var`."""
    while isinstance(term, Var) and term.ref is not None:
        term = term.ref
    return term


def is_bound(term: Value) -> bool:
    """Return ``True`` if ``term`` dereferences to a non-variable value."""
    return not isinstance(deref(term), Var)


def bind(var: Value, value: Value) -> None:
    """Bind ``var`` to ``value`` -- a readable alias for ``unify(var, value)``."""
    unify(var, value)


def unify(a: Value, b: Value) -> None:
    """Unify two terms (KL1 *tell*).

    Write-once and structural: aliases two unbound variables, binds an unbound
    variable to a value (waking its suspended callbacks), or recurses into cons
    cells. Raises :class:`UnificationError` on an inconsistent binding.
    """
    a = deref(a)
    b = deref(b)
    if a is b:
        return
    if isinstance(a, Var) and isinstance(b, Var):
        # Link a -> b, carrying a's suspended callbacks over to b.
        b.waiters.extend(a.waiters)
        a.waiters = []
        a.ref = b
        return
    if isinstance(a, Var):
        _resolve(a, b)
        return
    if isinstance(b, Var):
        _resolve(b, a)
        return
    if isinstance(a, Cons) and isinstance(b, Cons):
        unify(a.head, b.head)
        unify(a.tail, b.tail)
        return
    if isinstance(a, Struct) and isinstance(b, Struct):
        if a.name != b.name or len(a.args) != len(b.args):
            raise UnificationError(f'cannot unify {a!r} with {b!r}')
        for arg_a, arg_b in zip(a.args, b.args, strict=True):
            unify(arg_a, arg_b)
        return
    if a == b:
        return
    raise UnificationError(f'cannot unify {a!r} with {b!r}')


def _resolve(var: Var, value: Value) -> None:
    """Bind an unbound ``var`` to a non-variable ``value`` and fire its wake-list."""
    var.ref = value
    waiters = var.waiters
    var.waiters = []
    for wake in waiters:
        wake()
