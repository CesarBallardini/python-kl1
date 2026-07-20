"""Unit tests for the single-assignment logic variable core."""

import pytest

from python_kl1.core import Engine
from python_kl1.core.logicvar import UnificationError, Var, bind, deref, is_bound, unify
from python_kl1.core.terms import NIL, Cons, Struct


@pytest.mark.unit
def test_fresh_var_is_unbound() -> None:
    x = Var()

    assert not is_bound(x)
    assert deref(x) is x


@pytest.mark.unit
def test_bind_makes_it_bound() -> None:
    x = Var()

    bind(x, 42)

    assert is_bound(x)
    assert deref(x) == 42


@pytest.mark.unit
def test_write_once_same_value_is_idempotent() -> None:
    x = Var()
    bind(x, 42)

    unify(x, 42)  # consistent -- no error

    assert deref(x) == 42


@pytest.mark.unit
def test_conflicting_bind_raises() -> None:
    x = Var()
    bind(x, 42)

    with pytest.raises(UnificationError):
        unify(x, 43)


@pytest.mark.unit
def test_var_to_var_alias_then_bind_propagates() -> None:
    x = Var()
    y = Var()

    unify(x, y)  # alias, both still unbound
    bind(y, 'hello')

    assert deref(x) == 'hello'
    assert deref(y) == 'hello'


@pytest.mark.unit
def test_binding_wakes_a_suspended_goal() -> None:
    engine = Engine()
    x = Var()
    log: list[object] = []

    engine.when_bound(x, lambda: log.append(deref(x)))
    engine.run()  # nothing yet -- x is unbound, goal is parked
    assert log == []

    bind(x, 7)
    engine.run()  # the parked goal is now runnable
    assert log == [7]


@pytest.mark.unit
def test_when_bound_runs_immediately_if_already_bound() -> None:
    engine = Engine()
    x = Var()
    bind(x, 1)
    log: list[object] = []

    engine.when_bound(x, lambda: log.append(deref(x)))
    engine.run()

    assert log == [1]


@pytest.mark.unit
def test_cons_cells_unify_structurally() -> None:
    a = Var()
    b = Var()

    unify(Cons(1, a), Cons(1, Cons(2, b)))

    assert deref(a) == Cons(2, b)
    unify(b, NIL)
    assert deref(b) is NIL


@pytest.mark.unit
def test_incompatible_cons_heads_raise() -> None:
    with pytest.raises(UnificationError):
        unify(Cons(1, Var()), Cons(2, Var()))


@pytest.mark.unit
def test_deref_follows_a_chain_of_aliases() -> None:
    a = Var()
    b = Var()
    c = Var()

    unify(a, b)
    unify(b, c)
    bind(c, 99)

    assert deref(a) == 99


@pytest.mark.unit
def test_unify_a_var_with_itself_is_a_noop() -> None:
    x = Var()

    unify(x, x)

    assert not is_bound(x)


@pytest.mark.unit
def test_aliasing_transfers_a_parked_waiter() -> None:
    engine = Engine()
    a = Var()
    b = Var()
    log: list[object] = []

    engine.when_bound(a, lambda: log.append(deref(a)))
    unify(a, b)  # a's parked waiter must move onto b
    bind(b, 7)
    engine.run()

    assert log == [7]


@pytest.mark.unit
def test_every_waiter_fires_on_bind() -> None:
    engine = Engine()
    x = Var()
    log: list[str] = []

    engine.when_bound(x, lambda: log.append('a'))
    engine.when_bound(x, lambda: log.append('b'))
    bind(x, 1)
    engine.run()

    assert sorted(log) == ['a', 'b']


@pytest.mark.unit
def test_unify_cons_with_nil_raises() -> None:
    with pytest.raises(UnificationError):
        unify(Cons(1, Var()), NIL)


@pytest.mark.unit
def test_deeply_nested_cons_unify() -> None:
    tail = Var()

    unify(Cons(1, Cons(2, Cons(3, tail))), Cons(1, Cons(2, Cons(3, NIL))))

    assert deref(tail) is NIL


@pytest.mark.unit
def test_var_repr_distinguishes_bound_and_unbound() -> None:
    x = Var()
    assert repr(x).startswith('Var(_')

    bind(x, 42)
    assert repr(x) == 'Var(=42)'


@pytest.mark.unit
def test_structs_unify_by_name_and_arguments() -> None:
    a = Var()

    unify(Struct('point', (a, 2)), Struct('point', (1, 2)))

    assert deref(a) == 1


@pytest.mark.unit
def test_structs_with_a_different_name_clash() -> None:
    with pytest.raises(UnificationError):
        unify(Struct('f', (1,)), Struct('g', (1,)))


@pytest.mark.unit
def test_structs_with_a_different_arity_clash() -> None:
    with pytest.raises(UnificationError):
        unify(Struct('f', (1,)), Struct('f', (1, 2)))
