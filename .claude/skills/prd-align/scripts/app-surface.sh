#!/usr/bin/env bash
# app-surface.sh — dump the current app's implemented surface so a PRD can be
# aligned against reality (not against what someone remembers building).
#
# Prints four sections: backend domains, OpenAPI paths+methods, web routes,
# and Alembic migrations. Run from the repo root. Read-only; no side effects.
set -euo pipefail
cd "$(git rev-parse --show-toplevel 2>/dev/null || echo .)"

api_app="apps/api/app"
web_src="apps/web/src"
openapi_glob="openapi/*.openapi.json"

echo "### BACKEND DOMAINS (apps/api/app/domains)"
if [ -d "$api_app/domains" ]; then
  for d in "$api_app"/domains/*/; do
    name="$(basename "$d")"
    [ "$name" = "__pycache__" ] && continue
    files="$(ls "$d" 2>/dev/null | grep -E '\.py$' | grep -v __ | tr '\n' ' ')"
    echo "- $name: $files"
  done
else
  echo "(no domains dir found at $api_app/domains)"
fi

echo
echo "### OPENAPI PATHS (method path — operationId)"
shopt -s nullglob
for spec in $openapi_glob; do
  echo "# from $spec"
  python3 - "$spec" <<'PY'
import json, sys
spec = json.load(open(sys.argv[1]))
for path, ops in sorted(spec.get("paths", {}).items()):
    for method, op in ops.items():
        if method.lower() not in {"get","post","put","patch","delete"}:
            continue
        opid = op.get("operationId", "")
        print(f"  {method.upper():6} {path}  — {opid}")
PY
done
[ -z "$(echo $openapi_glob)" ] && echo "(no openapi spec found at $openapi_glob)"

echo
echo "### WEB ROUTES (apps/web/src/routes)"
if [ -d "$web_src/routes" ]; then
  find "$web_src/routes" -name '*.tsx' | sort | sed "s|$web_src/routes/||;s|^|- |"
else
  echo "(no web routes dir found)"
fi

echo
echo "### DB MIGRATIONS"
mig_dir="$(find apps/api -type d -name versions 2>/dev/null | head -1)"
if [ -n "$mig_dir" ]; then
  ls "$mig_dir" | grep -E '\.py$' | sed 's/^/- /'
else
  echo "(no alembic versions dir found)"
fi
