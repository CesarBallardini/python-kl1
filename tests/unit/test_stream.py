"""Unit tests for streams built over logic variables."""

import pytest

from python_kl1.core import (
    Engine,
    Value,
    close,
    collect,
    drain,
    each,
    filter_stream,
    map_stream,
    open_stream,
    put,
    stream_from,
)
from python_kl1.core.logicvar import Var


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
