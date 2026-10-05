"""Explicit adapter for an immutable application value.

Run from an installed checkout:

    python examples/adapters.py
"""

from dataclasses import dataclass

from revlet import Database, ValueAdapter, tracked


@dataclass(frozen=True)
class Point:
    x: int
    y: int


class PointAdapter(ValueAdapter):
    """Publish the point itself. Replacement, not editing, changes it."""

    stable = True

    def read(self, value, guard):
        return value

    def equivalent(self, old, new):
        return old == new


def main():
    db = Database()
    adapter = PointAdapter()
    point = db.input(Point(1, 2), adapter=adapter)
    runs = []

    @tracked(result_adapter=adapter)
    def identity(value):
        return value.value

    @tracked
    def horizontal(value):
        runs.append(1)
        return identity(value).x

    assert horizontal(point) == 1
    point.value = Point(1, 2)
    assert horizontal(point) == 1
    assert runs == [1]
    point.value = Point(4, 9)
    assert horizontal(point) == 4
    assert runs == [1, 1]
    print("adapters: equal Point reused; changed x recomputed")


if __name__ == "__main__":
    main()
