"""Static caller contract; checked with modern tools, not imported by pytest."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import assert_type

from revlet import Database, Input, ReadGuard, ValueAdapter, tracked

db = Database()
price = db.input(12)
items = db.input([1, 2])
assert_type(price.value, int)
assert_type(items.value, Sequence[int])
items.value.append(3)  # type: ignore[attr-defined]
items.value[0] = 3  # type: ignore[index]
with items.edit() as writable:
    assert_type(writable, list[int])
    writable.append(3)
items.value = [4, 5]


@tracked
def total(value: Input[Sequence[int], list[int]], *, factor: int = 1) -> int:
    return sum(value.value) * factor


assert_type(total(items, factor=2), int)
total(items, missing=1)  # type: ignore[call-arg]
total(items, factor="2")  # type: ignore[arg-type]
assert_type(db.bind(total)(items), int)


@tracked
def result() -> list[int]:
    return [1]


@tracked()
def mapping() -> dict[str, int]:
    return {"x": 1}


@tracked
def nested() -> list[list[int]]:
    return [[1]]


assert_type(db.bind(result)(), Sequence[int])
assert_type(db.bind(mapping)(), Mapping[str, int])
assert_type(db.bind(nested)(), Sequence[object])
db.bind(result)().append(1)  # type: ignore[attr-defined]
db.bind(nested)()[0].append(1)  # type: ignore[attr-defined]


@dataclass(frozen=True)
class Point:
    x: int


class PointAdapter(ValueAdapter[Point, int]):
    stable = True

    def read(self, value: Point, guard: ReadGuard) -> int:
        return value.x


@tracked(result_adapter=PointAdapter())
def point() -> Point:
    return Point(1)


assert_type(db.bind(point)(), int)
assert_type(db.input(Point(1), adapter=PointAdapter()).value, int)


class Model:
    @tracked
    def compute(self, factor: int = 1) -> int:
        return factor


assert_type(Model().compute(factor=2), int)
