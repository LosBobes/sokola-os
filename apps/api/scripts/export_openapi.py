"""Regenerate the committed OpenAPI document. Run after any API surface change."""

from __future__ import annotations

from scripts.openapi_doc import COMMITTED_PATH, generate, serialize


def main() -> None:
    COMMITTED_PATH.parent.mkdir(parents=True, exist_ok=True)
    COMMITTED_PATH.write_text(serialize(generate()))
    print(f"wrote {COMMITTED_PATH}")


if __name__ == "__main__":
    main()
