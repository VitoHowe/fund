"""Shared JSON config store with atomic writes and version history."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def mask_secret(value: str | None, keep: int = 3) -> str:
    if not value:
        return ""
    if len(value) <= keep * 2:
        return "*" * len(value)
    return f"{value[:keep]}{'*' * (len(value) - keep * 2)}{value[-keep:]}"


class JsonConfigStore:
    """Persist JSON config files with cache, atomic replace and history."""

    def __init__(
        self,
        config_path: str,
        default_factory: Callable[[], dict[str, Any]],
        *,
        kind: str,
        max_history: int = 12,
    ) -> None:
        self.config_path = self._resolve_path(config_path)
        self.default_factory = default_factory
        self.kind = kind
        self.max_history = max_history
        self._lock = threading.RLock()
        self._cached_mtime_ns: int | None = None
        self._cached_state: dict[str, Any] | None = None
        self._ensure_file()

    def get_state(self, *, force_reload: bool = False) -> dict[str, Any]:
        with self._lock:
            self._ensure_file()
            stat = self.config_path.stat()
            should_reload = (
                force_reload
                or self._cached_state is None
                or self._cached_mtime_ns != stat.st_mtime_ns
            )
            if should_reload:
                text = self.config_path.read_text(encoding="utf-8")
                raw = json.loads(text)
                self._cached_state = self._normalize_loaded_state(raw)
                self._cached_mtime_ns = stat.st_mtime_ns
            return copy.deepcopy(self._cached_state or {})

    def save_state(
        self,
        next_state: dict[str, Any],
        *,
        record_current_snapshot: bool = True,
    ) -> dict[str, Any]:
        with self._lock:
            current = self.get_state(force_reload=False)
            history = list(current.get("history") or [])
            if record_current_snapshot:
                history.insert(0, self._snapshot_from_state(current))
            normalized = self._prepare_for_write(next_state, history=history)
            self._write_state(normalized)
            return copy.deepcopy(normalized)

    def reload(self) -> dict[str, Any]:
        return self.get_state(force_reload=True)

    def list_versions(self) -> list[dict[str, Any]]:
        state = self.get_state(force_reload=False)
        return copy.deepcopy(state.get("history") or [])

    def rollback(self, version: str) -> dict[str, Any]:
        current = self.get_state(force_reload=False)
        history = list(current.get("history") or [])
        target = next((item for item in history if item.get("version") == version), None)
        if target is None:
            raise ValueError(f"version not found: {version}")
        remaining = [item for item in history if item.get("version") != version]
        restored = {
            **copy.deepcopy(target),
            "history": [self._snapshot_from_state(current), *remaining][: self.max_history],
        }
        normalized = self._prepare_for_write(restored, history=restored["history"])
        self._write_state(normalized)
        return copy.deepcopy(normalized)

    def _prepare_for_write(
        self,
        state: dict[str, Any],
        *,
        history: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if self._cached_state is not None:
            current = self._cached_state
        elif self.config_path.exists():
            try:
                current = self.get_state(force_reload=False)
            except Exception:
                current = {}
        else:
            current = {}
        normalized = {
            "kind": self.kind,
            "default_id": state.get("default_id"),
            "items": copy.deepcopy(state.get("items") or []),
            "history": copy.deepcopy(history if history is not None else state.get("history") or []),
            "updated_at": now_utc_iso(),
            "revision": int(state.get("revision") or current.get("revision") or 0) + 1,
        }
        normalized["history"] = normalized["history"][: self.max_history]
        normalized["version"] = self._build_version(normalized)
        return normalized

    def _normalize_loaded_state(self, state: dict[str, Any]) -> dict[str, Any]:
        normalized = {
            "kind": str(state.get("kind") or self.kind),
            "default_id": state.get("default_id"),
            "items": copy.deepcopy(state.get("items") or []),
            "history": copy.deepcopy(state.get("history") or []),
            "updated_at": str(state.get("updated_at") or now_utc_iso()),
            "revision": int(state.get("revision") or 0),
        }
        normalized["version"] = str(state.get("version") or self._build_version(normalized))
        return normalized

    def _snapshot_from_state(self, state: dict[str, Any]) -> dict[str, Any]:
        return {
            "kind": state.get("kind") or self.kind,
            "version": state.get("version") or self._build_version(state),
            "updated_at": state.get("updated_at") or now_utc_iso(),
            "default_id": state.get("default_id"),
            "items": copy.deepcopy(state.get("items") or []),
            "revision": int(state.get("revision") or 0),
        }

    def _build_version(self, state: dict[str, Any]) -> str:
        body = {
            "kind": state.get("kind") or self.kind,
            "default_id": state.get("default_id"),
            "items": state.get("items") or [],
            "revision": int(state.get("revision") or 0),
        }
        text = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:10]
        return f"r{body['revision']}:{digest}"

    def _ensure_file(self) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        if self.config_path.exists():
            return
        initial = self._prepare_for_write(self.default_factory(), history=[])
        self._write_state(initial)

    def _write_state(self, state: dict[str, Any]) -> None:
        text = json.dumps(state, ensure_ascii=False, indent=2)
        temp_fd, temp_path = tempfile.mkstemp(
            prefix=f".{self.config_path.name}.",
            suffix=".tmp",
            dir=str(self.config_path.parent),
        )
        try:
            with os.fdopen(temp_fd, "w", encoding="utf-8") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self.config_path)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
        self._cached_state = copy.deepcopy(state)
        self._cached_mtime_ns = self.config_path.stat().st_mtime_ns

    @staticmethod
    def _resolve_path(config_path: str) -> Path:
        path = Path(config_path)
        if path.is_absolute():
            return path
        root = Path(__file__).resolve().parents[2]
        return root / path
