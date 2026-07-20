"""Unit tests for the logic-value term types."""

import pytest

from python_kl1.core import NIL, Cons, Nil, Struct


@pytest.mark.unit
def test_nil_repr() -> None:
    assert repr(NIL) == 'NIL'


@pytest.mark.unit
def test_nil_is_an_instance_of_the_nil_type() -> None:
    assert isinstance(NIL, Nil)


@pytest.mark.unit
def test_cons_holds_head_and_tail() -> None:
    cell = Cons(1, NIL)

    assert cell.head == 1
    assert cell.tail is NIL


@pytest.mark.unit
def test_cons_equality_is_structural() -> None:
    assert Cons(1, Cons(2, NIL)) == Cons(1, Cons(2, NIL))
    assert Cons(1, NIL) != Cons(2, NIL)


@pytest.mark.unit
def test_struct_holds_name_and_args() -> None:
    point = Struct('point', (1, 2))

    assert point.name == 'point'
    assert point.args == (1, 2)


@pytest.mark.unit
def test_struct_equality_is_structural() -> None:
    assert Struct('f', (1, 2)) == Struct('f', (1, 2))
    assert Struct('f', (1,)) != Struct('g', (1,))  # different name
    assert Struct('f', (1,)) != Struct('f', (2,))  # different args
