.PHONY: check fmt testdb-up testdb-down license image-slim image-standalone hadolint compose-check

check:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy
	uv run lint-imports
	uv run python -m scripts.check_no_dashes --all

fmt:
	uv run ruff format .
	uv run ruff check --fix .

license:
	uv run python -m scripts.license_gate

testdb-up:
	./scripts/testdb_up.sh

testdb-down:
	./scripts/testdb_down.sh

image-slim:
	docker build --target runtime-slim -t kanban:runtime-slim .

image-standalone:
	docker build -t kanban:latest .

hadolint:
	docker run --rm -i hadolint/hadolint@sha256:32dac94127fd60b7b7e3fbfc65e1383b9b5e25c9bfd7b8536de7a539fe68a12d < Dockerfile

compose-check:
	install -d -m 0700 deploy/secrets
	test -f deploy/secrets/postgres_password.txt || echo "placeholder_postgres_password" > deploy/secrets/postgres_password.txt
	test -f deploy/secrets/master_kek.txt || echo "placeholder_master_kek_32_bytes_long" > deploy/secrets/master_kek.txt
	chmod 0600 deploy/secrets/*.txt
	docker compose -f docker-compose.yml --profile sandbox config --quiet
	uv run python -m scripts.check_compose_networks
