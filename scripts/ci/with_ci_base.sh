#!/usr/bin/env bash
set -euo pipefail

# Build or reuse the content-addressed kanban-ci-base image on the runner's Docker daemon
# and execute the given command inside a container sharing the runner's workspace volume.

LOCK_HASH="$(sha256sum deploy/ci/Dockerfile.ci-base pyproject.toml uv.lock pnpm-lock.yaml | sha256sum | cut -c1-16)"
IMAGE_TAG="kanban-ci-base:${LOCK_HASH}"

if ! docker image inspect "${IMAGE_TAG}" >/dev/null 2>&1; then
  DOCKER_BUILDKIT=1 docker build \
    --quiet \
    -t "${IMAGE_TAG}" \
    -t "kanban-ci-base:latest" \
    -f deploy/ci/Dockerfile.ci-base \
    . >/dev/null || docker image inspect "${IMAGE_TAG}" >/dev/null 2>&1
fi

WORKDIR_PATH="$(pwd)"
CID="$(hostname)"

DOCKER_ARGS=(
  --rm
  -w "${WORKDIR_PATH}"
  -e CI=true
  -e GITHUB_ACTIONS="${GITHUB_ACTIONS:-true}"
  -e CI_JOB_NAME="${CI_JOB_NAME:-}"
  -e KB_TEST_PGHOST="${KB_TEST_PGHOST:-${WORKDIR_PATH}/.kb-pgsock}"
  -e KB_TEST_PGSOCKET_DIR="${KB_TEST_PGSOCKET_DIR:-${WORKDIR_PATH}/.kb-pgsock}"
  -e UV_CACHE_DIR=/opt/ci-cache/uv
  -e UV_PROJECT_ENVIRONMENT=/opt/ci-venv
  -e UV_LINK_MODE=copy
)

if [ -n "${CI:-}" ] || [ -f /.dockerenv ]; then
  DOCKER_ARGS+=(--volumes-from "${CID}")
else
  DOCKER_ARGS+=(-v "${WORKDIR_PATH}:${WORKDIR_PATH}")
fi

exec docker run "${DOCKER_ARGS[@]}" "${IMAGE_TAG}" bash -c "if ! command -v ssh-keygen >/dev/null 2>&1; then printf '#!/bin/sh\nexec /opt/ci-venv/bin/python3 \"%s/scripts/ci/bin/ssh-keygen\" \"\$@\"\n' \"${WORKDIR_PATH}\" > /usr/bin/ssh-keygen && chmod +x /usr/bin/ssh-keygen && ln -sf /usr/bin/ssh-keygen /usr/local/bin/ssh-keygen; fi && export PATH=\"\${PATH}:${WORKDIR_PATH}/scripts/ci/bin\" && git config --global --add safe.directory '*' && $*"
