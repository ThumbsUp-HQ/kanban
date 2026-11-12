.PHONY: check fmt testdb-up testdb-down license

check:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy
	uv run lint-imports
	uv run python -m scripts.check_no_dashes --all

license:
	uv run python -m scripts.license_gate


fmt:
	uv run ruff format .
	uv run ruff check --fix .

testdb-up:
	install -d -m 0700 $${KB_TEST_PGSOCKET_DIR:-/tmp/kb-pgsock} 2>/dev/null || test -d $${KB_TEST_PGSOCKET_DIR:-/tmp/kb-pgsock}
	docker compose -f docker-compose.test.yml up -d --wait

testdb-down:
	docker compose -f docker-compose.test.yml down
