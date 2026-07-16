"""OpenAPI parity gate.

Regenerates the OpenAPI document from the live FastAPI app and diffs it against
the committed copy. Any drift, plus any route missing an explicit ``operationId``,
fails the build. This keeps the checked-in contract honest.
"""

from __future__ import annotations

import sys

from scripts.openapi_doc import COMMITTED_PATH, generate, serialize


def _missing_operation_ids(doc: dict) -> list[str]:
    missing: list[str] = []
    for path, methods in doc.get("paths", {}).items():
        for method, op in methods.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                continue
            if not op.get("operationId"):
                missing.append(f"{method.upper()} {path}")
    return missing


def main() -> int:
    current = generate()

    missing = _missing_operation_ids(current)
    if missing:
        print("Routes missing operationId:", file=sys.stderr)
        for route in missing:
            print(f"  - {route}", file=sys.stderr)
        return 1

    if not COMMITTED_PATH.exists():
        print(
            f"Committed OpenAPI doc missing at {COMMITTED_PATH}. "
            "Run: python -m scripts.export_openapi",
            file=sys.stderr,
        )
        return 1

    if serialize(current) != COMMITTED_PATH.read_text():
        print(
            "OpenAPI drift detected. Regenerate with: python -m scripts.export_openapi",
            file=sys.stderr,
        )
        return 1

    print("OpenAPI parity OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
