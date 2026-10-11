"""Architectural Guard Test.

Guarantees that backend/apigateway/ is the ONLY code in the repository allowed
to import requests or httpx.
"""

import ast
from pathlib import Path

FORBIDDEN_MODULES = {"requests", "httpx", "urllib.request"}
REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_apigateway_isolation_guard():
    """Verify no python files outside backend/apigateway import network libraries."""
    backend_dir = REPO_ROOT / "backend"
    violations = []

    for py_file in backend_dir.rglob("*.py"):
        # Allow files inside backend/apigateway/
        if "apigateway" in py_file.parts:
            continue

        with open(py_file, "r", encoding="utf-8") as f:
            try:
                tree = ast.parse(f.read(), filename=str(py_file))
            except SyntaxError:
                continue

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name in FORBIDDEN_MODULES:
                            violations.append(
                                f"{py_file.relative_to(REPO_ROOT)} imports '{alias.name}' at line {node.lineno}"
                            )
                elif isinstance(node, ast.ImportFrom):
                    if node.module and any(
                        node.module == mod or node.module.startswith(f"{mod}.")
                        for mod in FORBIDDEN_MODULES
                    ):
                        violations.append(
                            f"{py_file.relative_to(REPO_ROOT)} imports from '{node.module}' at line {node.lineno}"
                        )

    assert not violations, (
        f"Architectural boundary violation! The following files outside apigateway import forbidden network libraries:\n"
        + "\n".join(violations)
    )
