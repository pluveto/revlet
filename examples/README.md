# Examples

Clone the repository and install it with Python 3.9+:

```bash
git clone https://github.com/pluveto/revlet.git
cd revlet
python -m pip install .
```

Run the examples from the repository root:

```bash
python examples/basic.py
python examples/adapters.py
python examples/cycles.py
```

| Example | What it demonstrates |
| --- | --- |
| [basic.py](basic.py) | Cached queries, input updates, collection editing, and custom result comparison. |
| [adapters.py](adapters.py) | A value adapter for an immutable application type. |
| [cycles.py](cycles.py) | Cycle diagnostics and a custom iterative solver. |

Each script checks its results with assertions and prints a short summary.
