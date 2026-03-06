"""Check that runtime code has no MCP dependency."""

from __future__ import annotations

import sys
from pathlib import Path

FORBIDDEN = (
    "mcp__",
    "stock-data-mcp",
    "list_tasks(",
    "execute_task(",
    "verify_task(",
    "mcp-router",
)

SCAN_DIRS = (
    "services",
    "scripts",
)

ALLOW_LIST = {
    "scripts/check_runtime_independence.py",
}


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    violations: list[tuple[str, int, str]] = []
    for rel in SCAN_DIRS:
        base = root / rel
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            rel_path = path.relative_to(root).as_posix()
            if rel_path in ALLOW_LIST:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for lineno, line in enumerate(text.splitlines(), start=1):
                low = line.lower()
                for token in FORBIDDEN:
                    if token in low:
                        violations.append((rel_path, lineno, token))
    if violations:
        print("RUNTIME_INDEPENDENCE_CHECK=FAILED")
        for rel_path, lineno, token in violations:
            print(f"{rel_path}:{lineno}: forbidden token '{token}'")
        return 1
    print("RUNTIME_INDEPENDENCE_CHECK=PASSED")
    print("Runtime data source layer is independent from MCP.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

