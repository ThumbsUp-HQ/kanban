#!/usr/bin/env bash
docker rm -f kanban-pg-test-1 2>/dev/null || true
docker compose -f docker-compose.test.yml down 2>/dev/null || true
rm -rf .kb-pgsock 2>/dev/null || true
