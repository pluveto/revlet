"""Ordinary query calls and managed editing.

Run from an installed checkout:

    python examples/basic.py
"""

from revlet import Database, ReadOnlyError, StaleViewError, copy_value, tracked


def close_enough(old, new):
    """Application tolerance. The library does not assume one."""

    return abs(old - new) < 0.1


def main():
    db = Database()
    price = db.input(10)
    quantity = db.input(3)

    @tracked
    def subtotal(amount, count):
        return amount.value * count.value

    assert subtotal(price, quantity) == 30
    assert subtotal(price, quantity) == 30
    price.value = 12
    assert subtotal(price, quantity) == 36

    @tracked
    def invoice():
        return subtotal(price, quantity)

    assert db.bind(invoice)() == 36

    items = db.input([1, 2])

    @tracked
    def total(values):
        return sum(values.value)

    borrowed = items.value
    with items.edit() as values:
        values.append(3)
        assert total(items) == 6
    assert total(items) == 6
    try:
        len(borrowed)
    except StaleViewError:
        pass
    else:
        raise AssertionError("a borrowed view survived a managed write")

    current = items.value
    try:
        current.append(4)
    except ReadOnlyError:
        pass
    else:
        raise AssertionError("an input read accepted append")
    independent = copy_value(current)
    independent.append(4)
    assert list(items.value) == [1, 2, 3]

    source = db.input(10.0)
    downstream_runs = []

    @tracked
    def measured(value):
        return value.value

    @tracked(equivalent=close_enough)
    def stable(value):
        return measured(value)

    @tracked
    def downstream(value):
        downstream_runs.append(1)
        return stable(value) + 1.0

    assert downstream(source) == 11.0
    source.value = 10.06
    assert downstream(source) == 11.0
    source.value = 10.12
    assert downstream(source) == 11.12
    assert downstream_runs == [1, 1]
    print("basic: subtotal, edit, and cutoff ok")


if __name__ == "__main__":
    main()
