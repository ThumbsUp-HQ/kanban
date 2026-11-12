.PHONY: check testdb-up testdb-down

check:
	uv lock --locked
	uv sync --locked
	uv run lint-imports
	! grep -rnP '[\x{2013}\x{2014}]' --exclude="build-check.txt" database/ docs/ pyproject.toml conftest.py Makefile docker-compose.test.yml

testdb-up:
	install -d -m 0700 $${KB_TEST_PGSOCKET_DIR:-/tmp/kb-pgsock} 2>/dev/null || test -d $${KB_TEST_PGSOCKET_DIR:-/tmp/kb-pgsock}
	docker compose -f docker-compose.test.yml up -d --wait

testdb-down:
	docker compose -f docker-compose.test.yml down
