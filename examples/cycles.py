"""Cycle reporting, then an application-supplied fixed-point solver.

The engine does not choose the iteration or prove convergence.

Run from an installed checkout:

    python examples/cycles.py
"""

from revlet import CycleError, Database, tracked


def solve(context):
    value = 0
    repeated = context.calls[-1]
    for _ in range(100):
        nxt = context.evaluate({repeated: value})
        if nxt == value:
            return nxt
        value = nxt
    raise RuntimeError("solver did not converge")


@tracked
def left(flag):
    return right(flag) if flag.value else 0


@tracked
def right(flag):
    return left(flag)


@tracked(solver=solve)
def climb(limit_input):
    return min(limit_input.value, climb(limit_input) + 1)


def main():
    db = Database()
    enabled = db.input(True)
    try:
        left(enabled)
    except CycleError as error:
        names = [call.name for call in error.calls]
    else:
        raise AssertionError("cycle was accepted as an ordinary result")
    assert names[0] == names[-1]
    assert names[0].endswith("left")
    assert names[1].endswith("right")
    print(f"cycle: {' -> '.join(names)}")

    limit = db.input(3)
    assert climb(limit) == 3
    assert db.cache_info().entries == 1
    limit.value = 5
    assert climb(limit) == 5
    print("cycles: solver published 3, then 5")


if __name__ == "__main__":
    main()
