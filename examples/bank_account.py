"""KL1 bank account object (transaction server), ported to python-kl1.

Mirrors ``ch04-.../bank_account.kl1``::

    accumulator([], _)                     :- true.
    accumulator([deposit(A)|More], Total)  :- accumulator(More, Total + A).
    accumulator([debit(A)|More], Total)    :- Total - A >= 0 | accumulator(More, Total - A).
    accumulator([balance(Amt)|More], Total):- Amt = Total, accumulator(More, Total).

A long-lived process serves a stream of tagged messages (``deposit(A)``, ``debit(A)``,
``balance(Reply)``) carrying its state (the balance) as an argument. The client hands
over a fresh ``Reply`` variable inside ``balance(Reply)`` -- a "stamped, self-addressed
envelope" -- and the server binds it (back-communication). This is what the
compound-term / functor feature (``struct`` / ``unstruct``) is for. Run it with
``uv run python examples/bank_account.py``.
"""

from python_kl1.core import Struct, Value, Var, deref, stream_from
from python_kl1.dsl import Relation, Term, clause, empty, guard, session, tell, uncons, unstruct


class Account(Relation):
    """accumulator(Messages, Total): serve deposit/debit/balance over a message stream."""

    @clause
    def closed(self, msgs: Term, total: Term) -> None:
        """accumulator([], _) :- true."""
        empty(msgs)

    @clause
    def deposit(self, msgs: Term, total: Term) -> None:
        """accumulator([deposit(A)|More], Total) :- accumulator(More, Total + A)."""
        msg, more = uncons(msgs)
        (amount,) = unstruct(msg, 'deposit', 1)
        self(more, total + amount)

    @clause
    def debit(self, msgs: Term, total: Term) -> None:
        """accumulator([debit(A)|More], Total) :- Total - A >= 0 | accumulator(More, Total - A)."""
        msg, more = uncons(msgs)
        (amount,) = unstruct(msg, 'debit', 1)
        guard(total - amount >= 0)
        self(more, total - amount)

    @clause
    def balance(self, msgs: Term, total: Term) -> None:
        """accumulator([balance(Reply)|More], Total) :- Reply = Total, accumulator(More, Total)."""
        msg, more = uncons(msgs)
        (reply,) = unstruct(msg, 'balance', 1)
        tell(reply, total)  # back-communication: bind the client's reply variable
        self(more, total)


account = Account()


def main() -> None:
    """Deposit 100 and 50, debit 30, then ask the balance (matching bank_account.kl1)."""
    with session() as engine:
        reply = Var()
        messages: list[Value] = [
            Struct('deposit', (100,)),
            Struct('deposit', (50,)),
            Struct('debit', (30,)),
            Struct('balance', (reply,)),  # the reply variable rides inside the message
        ]
        stream = stream_from(engine, messages)

        account(stream, 0)  # spawn -- `reply` is bound inside the message stream
        engine.run()

        print('balance =', deref(reply))


if __name__ == '__main__':
    main()
