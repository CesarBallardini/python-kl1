"""python-kl1 core runtime.

The concurrency substrate: single-assignment logic variables
(:mod:`~python_kl1.core.logicvar`), streams over them
(:mod:`~python_kl1.core.stream`), and a cooperative interleaving engine
(:mod:`~python_kl1.core.engine`). Everything else in KL1 -- objects, merge,
client-server, futures -- is meant to be built as patterns on top of these.
"""

from python_kl1.core.engine import Engine, Goal
from python_kl1.core.goal import (
    Commit,
    NoMatchingClauseError,
    Predicate,
    Suspend,
    bind_from,
    call,
    commit,
    fail,
    suspend,
)
from python_kl1.core.logicvar import UnificationError, Var, bind, deref, is_bound, unify
from python_kl1.core.stream import (
    Producer,
    close,
    collect,
    drain,
    each,
    filter_stream,
    map_stream,
    open_stream,
    put,
    stream_from,
    to_list,
)
from python_kl1.core.terms import NIL, Atom, Cons, Nil, Struct, Value

__all__ = [
    'NIL',
    'Atom',
    'Commit',
    'Cons',
    'Engine',
    'Goal',
    'Nil',
    'NoMatchingClauseError',
    'Predicate',
    'Producer',
    'Struct',
    'Suspend',
    'UnificationError',
    'Value',
    'Var',
    'bind',
    'bind_from',
    'call',
    'close',
    'collect',
    'commit',
    'deref',
    'drain',
    'each',
    'fail',
    'filter_stream',
    'is_bound',
    'map_stream',
    'open_stream',
    'put',
    'stream_from',
    'suspend',
    'to_list',
    'unify',
]
