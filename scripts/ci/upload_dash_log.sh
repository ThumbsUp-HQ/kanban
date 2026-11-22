#!/usr/bin/env bash
# Upload this job's CI step logs to Dash (POST /api/logs), best effort (KB-P0-06).
#
# Usage: upload_dash_log.sh <job-name>
#
# Environment:
#   DASH_TOKEN      API bearer token (never echoed). Missing token => skip, exit 0.
#   DASH_ENDPOINT   Base URL (default: https://dash.hackedyour.info, or DASH_URL).
#   DASH_URL        Legacy alias for DASH_ENDPOINT.
#   GITHUB_SHA      Commit SHA used to pin the log to this build (Dash `sha` parameter).
#   CI_LOG_DIR      Log dir to read (default ci-logs/<job-name>).
#
# Contract:
#   - Always exits 0: a Dash outage must never turn a green job red.
#   - Jobs run in parallel and Dash keeps one log per (repo, sha), so the script reads the
#     existing log for this SHA first and prepends it (best effort, last writer wins on a race).
#   - Certificate verification stays ON (no curl -k).
set -uo pipefail

job="${1:-}"
if ! [[ "$job" =~ ^[a-z0-9-]+$ ]]; then
  echo "upload_dash_log.sh: invalid job name (must match ^[a-z0-9-]+\$)" >&2
  exit 64
fi

DASH_ENDPOINT="${DASH_ENDPOINT:-${DASH_URL:-https://dash.hackedyour.info}}"

if [ -z "${DASH_TOKEN:-}" ] || [ -z "${DASH_ENDPOINT:-}" ]; then
  echo "Notice: DASH_TOKEN missing - Notice: DASH_TOKEN or DASH_ENDPOINT missing; skipping Dash upload"
  exit 0
fi

log_dir="${CI_LOG_DIR:-ci-logs/$job}"
shopt -s nullglob
logs=("$log_dir"/*.log)
if [ "${#logs[@]}" -eq 0 ]; then
  echo "Notice: no $log_dir/*.log files to upload"
  exit 0
fi

dash_url="$DASH_ENDPOINT"
query="provider=forgejo&owner=ThumbsUp-HQ&repo=kanban"
if [ -n "${GITHUB_SHA:-}" ]; then
  query="$query&sha=${GITHUB_SHA}"
fi

body="$(mktemp)"
trap 'rm -f -- "$body"' EXIT

existing="$(curl -s --max-time 20 -H "Authorization: Bearer ${DASH_TOKEN}" \
  "${dash_url}/api/logs?${query}" 2>/dev/null \
  | python3 -c 'import json,sys
try:
    log = json.load(sys.stdin).get("log", "")
    if "Forgejo/Gitea logs are not natively available" not in log:
        print(log, end="")
except Exception:
    pass' 2>/dev/null || true)"
if [ -n "$existing" ]; then
  printf '%s\n' "$existing" > "$body"
fi

{
  printf '##### job: %s #####\n' "$job"
  for f in "${logs[@]}"; do
    printf '=== %s (exit %s) ===\n' "$f" "$(cat "${f%.log}.exit" 2>/dev/null || echo '?')"
    cat -- "$f"
  done
} >> "$body"

echo "Uploading $job logs to Dash..."
curl -s --max-time 60 -X POST "${dash_url}/api/logs?${query}" \
  -H "Authorization: Bearer ${DASH_TOKEN}" \
  -H "Content-Type: text/plain" \
  --data-binary @"$body" >/dev/null || echo "Notice: Dash upload failed"
exit 0
