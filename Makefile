.PHONY: install validate trace test lint paper clean

install:
	uv sync --extra dev --extra paper

validate:
	uv run aegisbench validate configs/benchmark.quick.yaml

trace:
	uv run aegisbench generate configs/benchmark.quick.yaml --output results/trace.jsonl

test:
	uv run pytest

lint:
	uv run ruff check .

paper:
	uv run --extra paper python scripts/build_whitepaper.py

clean:
	rm -rf build dist htmlcov .coverage .pytest_cache
