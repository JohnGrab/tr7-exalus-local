#!/usr/bin/env bash
#
# Validate hacs.json and manifest.json against the official HACS schemas,
# locally, using the hacs/action container image — no GitHub token and no
# commit/push required. This covers the two file-based checks that the
# "Validate with HACS" workflow runs (hacsjson + integration_manifest).
#
# Usage:
#   ./scripts/hacs_validate.sh
#
# Requires a container runtime (podman or docker). Override with
# CONTAINER_RUNTIME=docker if both are present.
#
# Note: the full hacs/action additionally runs GitHub-API checks (brands,
# description, topics, releases) against the *pushed* repository; those cannot
# be reproduced from local files alone.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="${HACS_ACTION_IMAGE:-ghcr.io/hacs/action:main}"

RUNTIME="${CONTAINER_RUNTIME:-}"
if [ -z "$RUNTIME" ]; then
  if command -v podman >/dev/null 2>&1; then RUNTIME=podman
  elif command -v docker >/dev/null 2>&1; then RUNTIME=docker
  else echo "error: no podman or docker found on PATH" >&2; exit 2
  fi
fi

echo "Validating HACS manifests with $RUNTIME ($IMAGE)..."
"$RUNTIME" run --rm -i -v "$REPO_ROOT":/repo:ro --entrypoint python3 "$IMAGE" - <<'PY'
import json
import sys

sys.path.insert(0, "/hacs")
from custom_components.hacs.utils.validate import (  # noqa: E402
    HACS_MANIFEST_JSON_SCHEMA,
    INTEGRATION_MANIFEST_JSON_SCHEMA,
)
from voluptuous import Invalid  # noqa: E402
from voluptuous.humanize import humanize_error  # noqa: E402

CHECKS = (
    ("hacs.json", "/repo/hacs.json", HACS_MANIFEST_JSON_SCHEMA),
    (
        "manifest.json",
        "/repo/custom_components/tr7_exalus_local/manifest.json",
        INTEGRATION_MANIFEST_JSON_SCHEMA,
    ),
)

failed = False
for label, path, schema in CHECKS:
    try:
        data = json.loads(open(path).read())
        schema(data)
    except FileNotFoundError:
        failed = True
        print(f"  {label:14s} MISSING ({path})")
    except json.JSONDecodeError as err:
        failed = True
        print(f"  {label:14s} INVALID JSON: {err}")
    except Invalid as err:
        failed = True
        print(f"  {label:14s} FAIL: {humanize_error(data, err)}")
    else:
        print(f"  {label:14s} OK")

sys.exit(1 if failed else 0)
PY
echo "All HACS manifest checks passed."
