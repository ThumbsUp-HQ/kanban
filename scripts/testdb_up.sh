#!/usr/bin/env bash
set -euo pipefail

SOCKET_DIR="${KB_TEST_PGSOCKET_DIR:-${KB_TEST_PGHOST:-/tmp/kb-pgsock}}"

if [ -n "${CI:-}" ] || [ -f /.dockerenv ]; then
  # Sibling container in CI / act_runner:
  # Share workspace volume via --volumes-from to allow socket access
  WS_SOCK_DIR="$(pwd)/.kb-pgsock"
  mkdir -p "${WS_SOCK_DIR}"
  chmod 0777 "${WS_SOCK_DIR}"
  if [ -n "${GITHUB_ENV:-}" ]; then
    echo "KB_TEST_PGHOST=${WS_SOCK_DIR}" >> "${GITHUB_ENV}"
    echo "KB_TEST_PGSOCKET_DIR=${WS_SOCK_DIR}" >> "${GITHUB_ENV}"
  fi
  
  CID=$(hostname)
  docker rm -f kanban-pg-test-1 2>/dev/null || true
  docker run -d --name kanban-pg-test-1 \
    --volumes-from "${CID}" \
    --label com.docker.compose.service=pg-test \
    -e POSTGRES_USER=kanban_test \
    -e POSTGRES_DB=postgres \
    -e POSTGRES_HOST_AUTH_METHOD=trust \
    --tmpfs /var/lib/postgresql/data:rw,size=1g \
    pgvector/pgvector:pg16@sha256:0dd3149a06e4579a0d70d8fef9945636cd514005e7237deb27f9b67886f8dc4f \
    postgres -c fsync=off -c synchronous_commit=off -c full_page_writes=off -c max_connections=200 \
    -c listen_addresses= -c "unix_socket_directories=/var/run/postgresql,${WS_SOCK_DIR}" -c unix_socket_permissions=0777

  # Wait for readiness
  for i in $(seq 1 45); do
    if docker exec kanban-pg-test-1 pg_isready -h /var/run/postgresql -U kanban_test >/dev/null 2>&1 && test -S "${WS_SOCK_DIR}/.s.PGSQL.5432"; then
      echo "PostgreSQL test container is healthy at ${WS_SOCK_DIR}"
      exit 0
    fi
    sleep 1
  done
  echo "PostgreSQL failed to become ready in time. Container logs:" >&2
  docker logs kanban-pg-test-1 >&2 || true
  exit 1
else
  # Local host environment
  install -d -m 0700 "${SOCKET_DIR}" 2>/dev/null || test -d "${SOCKET_DIR}"
  docker compose -f docker-compose.test.yml up -d --wait
fi
