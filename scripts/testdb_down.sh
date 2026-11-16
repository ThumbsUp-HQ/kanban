#!/usr/bin/env bash
PG_NAME="kanban-pg-test-${CI_JOB_NAME:-1}"
docker rm -f "${PG_NAME}" 2>/dev/null || true
if [ -z "${CI_JOB_NAME:-}" ]; then
  docker compose -f docker-compose.test.yml down 2>/dev/null || true
fi
rm -rf .kb-pgsock 2>/dev/null || true
