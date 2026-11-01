"""Unit tests for streams built over logic variables."""

from typing import TYPE_CHECKING

import pytest

from python_kl1.core import (
    NIL,
    Cons,
    DeadlockError,
    Engine,
    Value,
    close,
    collect,
    deref,
    drain,
    each,
    filter_stream,
    map_stream,
    merge_streams,
    open_stream,
    put,
    stream_from,
    to_list,
)
from python_kl1.core.logicvar import Var

if TYPE_CHECKING:
    from collections.abc import Callable


@pytest.mark.unit
def test_producer_consumer_roundtrip() -> None:
    engine = Engine()
    source = stream_from(engine, [1, 2, 3])

    result = collect(engine, source)
    engine.run()

    assert result == [1, 2, 3]


@pytest.mark.unit
def test_consumer_registered_before_producer_still_gets_all() -> None:
    # Order independence: the consumer suspends until the producer catches up.
    engine = Engine()
    stream = Var()
    result = collect(engine, stream)

    tail = put(stream, 'a')
    tail = put(tail, 'b')
    close(tail)
    engine.run()

    assert result == ['a', 'b']


@pytest.mark.unit
def test_producer_context_manager_closes_stream() -> None:
    engine = Engine()
    head, producer = open_stream()

    with producer:
        producer.put(10)
        producer.put(20)

    result = collect(engine, head)
    engine.run()

    assert result == [10, 20]


@pytest.mark.unit
def test_drain_is_a_plain_python_iterator() -> None:
    engine = Engine()
    source = stream_from(engine, range(5))

    # A suspending KL1 stream consumed as an ordinary Python iterator.
    assert list(drain(engine, source)) == [0, 1, 2, 3, 4]


def _is_even(n: Value) -> bool:
    assert isinstance(n, int)
    return n % 2 == 0


def _double(n: Value) -> Value:
    assert isinstance(n, int)
    return n * 2


@pytest.mark.unit
def test_map_and_filter_pipeline() -> None:
    engine = Engine()
    source = stream_from(engine, range(10))

    evens = filter_stream(engine, source, _is_even)
    doubled = map_stream(engine, evens, _double)

    assert list(drain(engine, doubled)) == [0, 4, 8, 12, 16]


@pytest.mark.unit
def test_generator_source_feeds_a_stream() -> None:
    engine = Engine()

    def gen():
        yield from ('x', 'y', 'z')

    source = stream_from(engine, gen())

    assert list(drain(engine, source)) == ['x', 'y', 'z']


@pytest.mark.unit
def test_empty_stream_collects_to_nothing() -> None:
    engine = Engine()
    source = stream_from(engine, [])

    result = collect(engine, source)
    engine.run()

    assert result == []


@pytest.mark.unit
def test_on_end_callback_fires_at_end_of_stream() -> None:
    engine = Engine()
    source = stream_from(engine, [1])
    ended: list[bool] = []

    each(engine, source, lambda _item: None, lambda: ended.append(True))
    engine.run()

    assert ended == [True]


@pytest.mark.unit
def test_manual_put_then_close_round_trips() -> None:
    engine = Engine()
    stream = Var()
    result = collect(engine, stream)

    close(put(stream, 'a'))
    engine.run()

    assert result == ['a']


@pytest.mark.unit
def test_transducer_passes_through_an_empty_stream() -> None:
    engine = Engine()
    empty_source = stream_from(engine, [])

    mapped = map_stream(engine, empty_source, _double)

    assert list(drain(engine, mapped)) == []


@pytest.mark.unit
def test_collect_list_fills_as_the_engine_runs() -> None:
    engine = Engine()
    source = stream_from(engine, [1, 2])

    result = collect(engine, source)
    assert result == []  # nothing consumed until the engine runs

    engine.run()
    assert result == [1, 2]


@pytest.mark.unit
def test_merge_interleaves_two_streams() -> None:
    # merge_new.kl1: generic:new(merge, {S1, S2}, Merged), S1 = [a], S2 = [b].
    engine = Engine()
    merged = merge_streams(engine, stream_from(engine, ['a']), stream_from(engine, ['b']))

    assert list(drain(engine, merged)) == ['a', 'b']


@pytest.mark.unit
def test_merge_forwards_each_input_as_it_arrives_and_closes_after_the_last() -> None:
    engine = Engine()
    left, right = Var(), Var()
    merged = merge_streams(engine, left, right)
    result = collect(engine, merged)
    ended: list[bool] = []
    each(engine, merged, lambda _item: None, lambda: ended.append(True))

    close(put(left, 1))
    engine.run()
    assert result == [1]  # left's element went through while right is still unbound...
    assert ended == []  # ...and the merge stays open for it

    close(put(right, 2))
    engine.run()
    assert result == [1, 2]
    assert ended == [True]


@pytest.mark.unit
def test_merge_of_no_streams_is_empty() -> None:
    engine = Engine()

    assert to_list(merge_streams(engine)) == []


@pytest.mark.unit
def test_merge_is_fair_between_ready_streams() -> None:
    # Both inputs are complete up front; neither starves the other -- they alternate.
    engine = Engine()
    numbers = Cons(1, Cons(2, Cons(3, NIL)))
    letters = Cons('a', Cons('b', Cons('c', NIL)))

    assert list(drain(engine, merge_streams(engine, numbers, letters))) == [1, 'a', 2, 'b', 3, 'c']


@pytest.mark.unit
def test_nested_merges_fan_in_more_streams() -> None:
    engine = Engine()
    inner = merge_streams(engine, stream_from(engine, [2]), stream_from(engine, [3]))
    merged = merge_streams(engine, stream_from(engine, [1]), inner)

    items = list(drain(engine, merged))

    assert len(items) == 3
    assert set(items) == {1, 2, 3}


@pytest.mark.unit
@pytest.mark.parametrize(
    ('name', 'consume'),
    [
        ('each', lambda engine, source: each(engine, source, lambda _: None)),
        ('map_stream', lambda engine, source: map_stream(engine, source, lambda x: x)),
        ('filter_stream', lambda engine, source: filter_stream(engine, source, lambda _: True)),
        ('merge_streams', lambda engine, source: merge_streams(engine, source)),
    ],
)
def test_a_consumer_waiting_on_an_open_stream_is_blocked(
    name: str, consume: Callable[[Engine, Var], Value | None]
) -> None:
    engine = Engine()
    source = Var()
    tail = put(source, 1)

    consume(engine, source)
    engine.run()
    assert engine.blocked == (f'{name}(waiting on {tail.label})',)  # the element was read; the tail is awaited

    close(tail)
    engine.run()
    assert engine.blocked == ()


@pytest.mark.unit
def test_a_merge_waiting_on_one_open_input_reports_only_that_input() -> None:
    engine = Engine()
    still_open = Var()

    merged = merge_streams(engine, stream_from(engine, [1, 2]), still_open)

    with pytest.raises(DeadlockError, match=rf'merge_streams\(waiting on {still_open.label}\)'):
        engine.run(check=True)
    assert len(engine.blocked) == 1
    assert deref(merged) is not NIL  # the closed input's elements went through


@pytest.mark.unit
def test_draining_a_stream_that_never_closes_leaves_its_reader_blocked() -> None:
    engine = Engine()
    source = Var()
    put(source, 1)

    assert list(drain(engine, source)) == [1]
    assert len(engine.blocked) == 1
