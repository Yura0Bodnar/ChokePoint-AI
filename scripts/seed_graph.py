import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from chokepoint.graph.loader import GraphValidationError, load_seed_graph  # noqa: E402


def main() -> int:
    try:
        graph = load_seed_graph(ROOT / "src/chokepoint/graph/seed")
    except GraphValidationError as error:
        print(error, file=sys.stderr)
        return 1
    print(f"nodes={graph.number_of_nodes()} edges={graph.number_of_edges()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
