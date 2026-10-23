#!/usr/bin/env bash
set -euo pipefail

task_dir="$(cd "$(dirname "$0")/.." && pwd)"
evidence_dir="$task_dir/solution/evidence"
image="harbor-ncm-feed-quality:$$"
mkdir -p "$evidence_dir"

docker build -q -t "$image" "$task_dir/environment" >/dev/null
cleanup() {
  docker image rm -f "$image" >/dev/null 2>&1 || true
}
trap cleanup EXIT

prepare_workspace() {
  local name="$1"
  shift
  local directory
  directory="$(mktemp -d "${TMPDIR:-/tmp}/ncm-feed-${name}.XXXXXX")"
  cp -R "$task_dir/environment/workspace/." "$directory"/
  for module in "$@"; do
    cp "$task_dir/solution/$module" "$directory/precursor_feed/$module"
  done
  printf '%s\n' "$directory"
}

run_case() {
  local name="$1"
  local workspace="$2"
  local logs
  local reward
  logs="$(mktemp -d "${TMPDIR:-/tmp}/ncm-feed-logs-${name}.XXXXXX")"
  chmod 0777 "$logs"
  {
    printf '$ docker run --rm -v %s:/workspace -v %s/tests:/tests:ro -v %s:/logs %s bash /tests/test.sh\n' \
      "$workspace" "$task_dir" "$logs" "$image"
    docker run --rm \
      -v "$workspace:/workspace" \
      -v "$task_dir/tests:/tests:ro" \
      -v "$logs:/logs" \
      "$image" \
      bash /tests/test.sh
    reward="$(cat "$logs/verifier/reward.txt")"
    printf 'reward=%s\n' "$reward"
    printf 'summary='
    python3 - "$logs/verifier/ctrf.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    summary = json.load(handle)["results"]["summary"]
print(
    f"tests={summary['tests']} passed={summary['passed']} "
    f"failed={summary['failed']}"
)
PY
  } >"$evidence_dir/$name.log" 2>&1
}

baseline_workspace="$(prepare_workspace baseline)"
run_case baseline "$baseline_workspace"

oracle_workspace="$(prepare_workspace oracle measurements.py blending.py charging.py stoichiometry.py conditioning.py crystallization.py washing.py multistage_washing.py validation.py)"
run_case oracle "$oracle_workspace"

c1_workspace="$(prepare_workspace c1 measurements.py)"
run_case partial-c1 "$c1_workspace"

c2_workspace="$(prepare_workspace c2 blending.py)"
run_case partial-c2 "$c2_workspace"

c3_workspace="$(prepare_workspace c3 charging.py)"
run_case partial-c3 "$c3_workspace"

c4_workspace="$(prepare_workspace c4 stoichiometry.py)"
run_case partial-c4 "$c4_workspace"

c5_workspace="$(prepare_workspace c5 validation.py)"
run_case partial-c5 "$c5_workspace"

c6_workspace="$(prepare_workspace c6 conditioning.py)"
run_case partial-c6 "$c6_workspace"

c7_workspace="$(prepare_workspace c7 crystallization.py)"
run_case partial-c7 "$c7_workspace"

c8_workspace="$(prepare_workspace c8 washing.py)"
run_case partial-c8 "$c8_workspace"

c9_workspace="$(prepare_workspace c9 multistage_washing.py)"
run_case partial-c9 "$c9_workspace"

empty_workspace="$(prepare_workspace empty measurements.py blending.py charging.py stoichiometry.py conditioning.py crystallization.py washing.py multistage_washing.py validation.py)"
cp "$task_dir/solution/bypasses/empty/cli.py" "$empty_workspace/precursor_feed/cli.py"
run_case bypass-empty "$empty_workspace"

malformed_workspace="$(prepare_workspace malformed measurements.py blending.py charging.py stoichiometry.py conditioning.py crystallization.py washing.py multistage_washing.py validation.py)"
cp "$task_dir/solution/bypasses/malformed/cli.py" "$malformed_workspace/precursor_feed/cli.py"
run_case bypass-malformed "$malformed_workspace"

hardcoded_workspace="$(prepare_workspace hardcoded measurements.py blending.py charging.py stoichiometry.py conditioning.py crystallization.py washing.py multistage_washing.py validation.py)"
cp "$task_dir/solution/bypasses/hardcoded/cli.py" "$hardcoded_workspace/precursor_feed/cli.py"
run_case bypass-hardcoded "$hardcoded_workspace"
