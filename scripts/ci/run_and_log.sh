#!/usr/bin/env bash
# Run a command, tee combined stdout/stderr to ci-logs/<job>/<logname>.log and
# record its exit code in ci-logs/<job>/<logname>.exit (KB-P0-06).
#
# Usage: run_and_log.sh <logname> -- <command> [args...]
#
# Contract:
#   - <logname> must match ^[a-z0-9-]+$ (else exit 64, nothing written).
#   - Log directory is $CI_LOG_DIR (default: ci-logs/${CI_JOB_NAME:-default}).
#   - Exit status is the wrapped command's exit status (pipefail semantics).
#   - No eval, no shell re-parsing: the command is executed as an argv vector.
set -euo pipefail

if [ "$#" -lt 3 ] || [ "$2" != "--" ]; then
  echo "usage: run_and_log.sh <logname> -- <command> [args...]" >&2
  exit 64
fi

logname="$1"
shift 2

if ! [[ "$logname" =~ ^[a-z0-9-]+$ ]]; then
  echo "run_and_log.sh: invalid log name (must match ^[a-z0-9-]+\$)" >&2
  exit 64
fi

log_dir="${CI_LOG_DIR:-ci-logs/${CI_JOB_NAME:-default}}"
mkdir -p -- "$log_dir"
log_file="$log_dir/$logname.log"
exit_file="$log_dir/$logname.exit"

rc=0
"$@" 2>&1 | tee -- "$log_file" || rc=$?
# pipefail makes the pipeline status the command's status; tee failure also surfaces here.
printf '%s\n' "$rc" > "$exit_file"
exit "$rc"
