"""P7 validation: observability, tests and compliance governance."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.data_hub import build_default_source_manager
from services.observability import SourceMonitor


def _parse_pyproject_dependencies(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    block_match = re.search(r"dependencies\s*=\s*\[(.*?)\]", text, flags=re.S)
    if not block_match:
        return []
    block = block_match.group(1)
    deps = re.findall(r'"([A-Za-z0-9_\-]+)', block)
    return sorted({item.lower() for item in deps})


def _parse_license_matrix_components(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    components: set[str] = set()
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [item.strip() for item in line.strip().split("|")]
        if len(cells) < 3:
            continue
        component = cells[1].strip().lower()
        if component and component not in {"component", "---"}:
            components.add(component)
    return components


def _run_unittest(paths: list[str]) -> dict[str, str]:
    cmd = [sys.executable, "-m", "unittest"] + paths
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, check=False)
    return {
        "ok": str(proc.returncode == 0).lower(),
        "returncode": str(proc.returncode),
        "stdout_tail": "\n".join(proc.stdout.splitlines()[-8:]),
        "stderr_tail": "\n".join(proc.stderr.splitlines()[-8:]),
    }


def main() -> None:
    manager = build_default_source_manager()
    monitor = SourceMonitor(source_manager=manager)
    snapshot = monitor.snapshot()
    prom_text = monitor.prometheus_text()
    deps = _parse_pyproject_dependencies(ROOT / "pyproject.toml")
    matrix_components = _parse_license_matrix_components(ROOT / "docs" / "compliance" / "license-matrix.md")
    missing = [dep for dep in deps if dep not in matrix_components]
    test_result = _run_unittest(
        [
            "tests.test_observability",
            "tests.integration.test_failover",
            "tests.regression.test_factor_scores",
        ]
    )
    checks = {
        "monitor_snapshot_available": bool(snapshot.get("sources") is not None),
        "monitor_alert_schema_ok": isinstance(snapshot.get("alerts"), list),
        "prometheus_metrics_available": "fund_data_source_enabled" in prom_text,
        "license_matrix_covers_runtime_dependencies": len(missing) == 0,
        "critical_test_suites_passed": test_result.get("ok") == "true",
    }
    output = {
        "checks": checks,
        "monitor_overall_status": snapshot.get("overall_status"),
        "source_count": snapshot.get("source_count"),
        "license_missing_components": missing,
        "test_result": test_result,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, default=str))
    if not all(checks.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()

