#!/usr/bin/env bash
# Verify the vendored v5.7 specification package against its own SHA-256 manifest.
#
# The package under docs/spec/v5.7 is the normative business/acceptance authority
# for this repository. It ships MANIFEST-SHA256.md covering all 72 content files
# (the manifest excludes itself by definition). This script re-checks every hash,
# so an accidental edit to a contract shows up as a failing hash rather than as a
# silent change of canon.
#
# Run: scripts/verify-spec-manifest.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SPEC="$ROOT/docs/spec/v5.7"
MANIFEST="$SPEC/MANIFEST-SHA256.md"

if [ ! -f "$MANIFEST" ]; then
  echo "error: manifest not found at $MANIFEST" >&2
  exit 1
fi

# The hashes live in the single fenced ```text block of the manifest document.
checksums="$(mktemp)"
trap 'rm -f "$checksums"' EXIT
sed -n '/^```text$/,/^```$/p' "$MANIFEST" | sed '/^```/d' > "$checksums"

expected=72
actual="$(grep -c . "$checksums")"
if [ "$actual" -ne "$expected" ]; then
  echo "error: manifest lists $actual files, expected $expected" >&2
  exit 1
fi

cd "$SPEC"
sha256sum -c "$checksums" > /dev/null
echo "Spec manifest OK: $actual/$expected files match docs/spec/v5.7/MANIFEST-SHA256.md"
