"""Architecture fitness gate.

Enforces the dependency-direction and simplicity rules so the modular monolith
stays modular:

* a domain never imports another domain's ``service`` / ``repository`` / ``router``
  / ``policy`` (it may share ``models`` / ``enums`` / ``schemas`` records only);
* ``app.common`` never imports a product domain;
* no ``service.py`` exceeds the size ratchet;
* no local-password / reset-token columns exist in the schema.

Run: ``python -m scripts.check_architecture``.
"""

from __future__ import annotations

import ast
import pathlib
import re
import sys

APP = pathlib.Path(__file__).resolve().parents[1] / "app"
DOMAINS = APP / "domains"

FORBIDDEN_CROSS_DOMAIN = ("service", "repository", "router", "policy")
MAX_SERVICE_LINES = 600
PASSWORD_PATTERN = re.compile(r"(password_hash|reset_token|password_reset)", re.IGNORECASE)


def _imports(path: pathlib.Path) -> list[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
        elif isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
    return names


def check_domain_boundaries() -> list[str]:
    problems: list[str] = []
    for py in DOMAINS.rglob("*.py"):
        domain = py.relative_to(DOMAINS).parts[0]
        for module in _imports(py):
            m = re.match(r"app\.domains\.([a-z_]+)\.([a-z_]+)", module)
            if not m:
                continue
            other, submodule = m.group(1), m.group(2)
            if other != domain and submodule in FORBIDDEN_CROSS_DOMAIN:
                problems.append(
                    f"{py.relative_to(APP.parent)}: domain '{domain}' imports "
                    f"'{other}.{submodule}' (only models/enums/schemas may cross domains)"
                )
    return problems


def check_common_purity() -> list[str]:
    problems: list[str] = []
    for py in (APP / "common").rglob("*.py"):
        for module in _imports(py):
            if module.startswith("app.domains"):
                problems.append(f"{py.relative_to(APP.parent)}: common imports a domain ({module})")
    return problems


def check_service_sizes() -> list[str]:
    problems: list[str] = []
    for py in DOMAINS.rglob("service.py"):
        lines = len(py.read_text().splitlines())
        if lines > MAX_SERVICE_LINES:
            problems.append(f"{py.relative_to(APP.parent)}: {lines} lines > {MAX_SERVICE_LINES}")
    return problems


def check_no_local_passwords() -> list[str]:
    problems: list[str] = []
    for py in APP.rglob("models.py"):
        if PASSWORD_PATTERN.search(py.read_text()):
            problems.append(f"{py.relative_to(APP.parent)}: local-password/reset column detected")
    return problems


def main() -> int:
    checks = [
        check_domain_boundaries(),
        check_common_purity(),
        check_service_sizes(),
        check_no_local_passwords(),
    ]
    problems = [p for group in checks for p in group]
    if problems:
        print("Architecture gate failed:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1
    print("Architecture gate OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
