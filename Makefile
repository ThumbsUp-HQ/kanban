.PHONY: check fmt

check:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy
	uv run lint-imports
	uv run python -m scripts.check_no_dashes --all

fmt:
	uv run ruff format .
	uv run ruff check --fix .
