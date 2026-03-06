"""Persist latest generated reports for sync retrieval."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


class ReportCache:
    """Store latest and per-id reports as JSON files."""

    def __init__(self, root_path: str = "data/reports") -> None:
        root = Path(root_path)
        if not root.is_absolute():
            project_root = Path(__file__).resolve().parents[2]
            root = project_root / root
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.latest_path = self.root / "latest_daily_report.json"

    def save_daily_report(self, payload: dict[str, Any]) -> None:
        report_id = str(payload.get("report_id") or "latest")
        self._atomic_write(self.root / f"{report_id}.json", payload)
        self._atomic_write(self.latest_path, payload)

    def get_latest_daily_report(self) -> dict[str, Any] | None:
        return self._read_json(self.latest_path)

    def get_report(self, report_id: str) -> dict[str, Any] | None:
        return self._read_json(self.root / f"{report_id}.json")

    def _read_json(self, path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def _atomic_write(self, path: Path, payload: dict[str, Any]) -> None:
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        fd, temp_path = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, path)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
