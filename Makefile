.PHONY: lint test test-eval run-pipeline serve

lint:
	uv run ruff check .
	uv run mypy sis

test:
	uv run pytest -q -m "not llm"

test-eval:
	uv run pytest -q -m eval

# make run-pipeline FILE=path/to/delivery
run-pipeline:
	uv run sis ingest "$(FILE)"

serve:
	uv run sis serve
