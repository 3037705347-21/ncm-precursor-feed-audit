#!/usr/bin/env bash
set -u

reward_file=/logs/verifier/reward.txt
JUNIT_FILE=/logs/verifier/junit.xml
mkdir -p /logs/verifier

write_reward_zero() {
  chmod 0644 "$reward_file" 2>/dev/null || true
  echo "0" > "$reward_file"
  chmod 0444 "$reward_file"
}

write_reward_zero

trap 'write_reward_zero' EXIT
trap 'write_reward_zero; exit 130' INT TERM HUP

if ! python -m pip install --user --no-cache-dir --disable-pip-version-check \
  --require-hashes --only-binary=:all: -r /tests/requirements.txt; then
  write_reward_zero
  exit 0
fi

cd /workspace
timeout 240s python -m pytest --junitxml "$JUNIT_FILE" /tests/test_outputs.py -q

if ! test -s "$JUNIT_FILE"; then
  printf 'INCOMPLETE: structured run report was not produced\n' >&2
  write_reward_zero
  exit 0
fi

python3 - "$JUNIT_FILE" "$reward_file" <<'PY'
import os
import sys
import xml.etree.ElementTree as ElementTree

junit_path, reward_path = sys.argv[1:]
groups = {
    "C1": (0.09, "test_c1_"),
    "C2": (0.14, "test_c2_"),
    "C3": (0.09, "test_c3_"),
    "C4": (0.12, "test_c4_"),
    "C5": (0.06, "test_c5_"),
    "C6": (0.09, "test_c6_"),
    "C7": (0.10, "test_c7_"),
    "C8": (0.10, "test_c8_"),
    "C9": (0.11, "test_c9_"),
    "E2E": (0.10, "test_e2e_"),
}
try:
    root = ElementTree.parse(junit_path).getroot()
except (OSError, ElementTree.ParseError):
    root = None

statuses = {}
if root is not None:
    for case in root.iter("testcase"):
        name = str(case.get("name", ""))
        failed = any(
            child.tag in {"failure", "error", "skipped"} for child in case
        )
        statuses[name] = not failed

earned = 0.0
for weight, prefix in groups.values():
    relevant = [passed for name, passed in statuses.items() if name.startswith(prefix)]
    if relevant and all(relevant):
        earned += weight

earned = min(1.0, max(0.0, earned))
os.chmod(reward_path, 0o644)
with open(reward_path, "w", encoding="utf-8") as handle:
    handle.write(f"{earned:.6f}\n")
os.chmod(reward_path, 0o444)
PY

trap - EXIT INT TERM HUP
exit 0
