"""Model provider settings management."""

from __future__ import annotations

import copy
from typing import Any

from services.config.store import JsonConfigStore, mask_secret, now_utc_iso


def _default_model_state() -> dict[str, Any]:
    return {
        "default_id": "openai-default",
        "items": [
            {
                "id": "openai-default",
                "name": "OpenAI Default",
                "url": "https://api.openai.com/v1",
                "apiKey": "",
                "model": "gpt-4.1-mini",
                "enabled": False,
                "is_default": True,
                "updated_at": now_utc_iso(),
            },
            {
                "id": "gemini-default",
                "name": "Gemini Default",
                "url": "https://generativelanguage.googleapis.com",
                "apiKey": "",
                "model": "gemini-2.0-flash",
                "enabled": False,
                "is_default": False,
                "updated_at": now_utc_iso(),
            },
        ],
    }


class ModelSettingsManager:
    """CRUD wrapper around the shared config store."""

    def __init__(self, config_path: str = "config/model_providers.json") -> None:
        self.store = JsonConfigStore(
            config_path=config_path,
            default_factory=_default_model_state,
            kind="model_providers",
        )

    def list_models(self, *, force_reload: bool = False) -> dict[str, Any]:
        state = self.store.get_state(force_reload=force_reload)
        return self._public_state(state)

    def get_model(self, provider_id: str) -> dict[str, Any]:
        state = self.store.get_state(force_reload=False)
        item = self._find_item(state, provider_id)
        return copy.deepcopy(item)

    def create_model(self, payload: dict[str, Any]) -> dict[str, Any]:
        state = self.store.get_state(force_reload=False)
        item = self._normalize_model(payload, existing=None)
        if any(existing.get("id") == item["id"] for existing in state["items"]):
            raise ValueError(f"model id already exists: {item['id']}")
        state["items"].append(item)
        self._sync_default_flags(state, preferred_id=item["id"] if item["is_default"] else state.get("default_id"))
        saved = self.store.save_state(state)
        return self._public_state(saved)

    def update_model(self, provider_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        state = self.store.get_state(force_reload=False)
        item = self._find_item(state, provider_id)
        updated = self._normalize_model(payload, existing=item)
        for index, current in enumerate(state["items"]):
            if current.get("id") == provider_id:
                state["items"][index] = updated
                break
        preferred_id = provider_id if updated["is_default"] else state.get("default_id")
        self._sync_default_flags(state, preferred_id=preferred_id)
        saved = self.store.save_state(state)
        return self._public_state(saved)

    def set_default(self, provider_id: str) -> dict[str, Any]:
        state = self.store.get_state(force_reload=False)
        self._find_item(state, provider_id)
        self._sync_default_flags(state, preferred_id=provider_id)
        saved = self.store.save_state(state)
        return self._public_state(saved)

    def set_enabled(self, provider_id: str, enabled: bool) -> dict[str, Any]:
        state = self.store.get_state(force_reload=False)
        item = self._find_item(state, provider_id)
        item["enabled"] = bool(enabled)
        item["updated_at"] = now_utc_iso()
        saved = self.store.save_state(state)
        return self._public_state(saved)

    def rollback(self, version: str) -> dict[str, Any]:
        saved = self.store.rollback(version)
        return self._public_state(saved)

    def reload(self) -> dict[str, Any]:
        state = self.store.reload()
        return self._public_state(state)

    def _public_state(self, state: dict[str, Any]) -> dict[str, Any]:
        items = [self._sanitize_item(item) for item in state.get("items") or []]
        return {
            "version": state.get("version"),
            "updated_at": state.get("updated_at"),
            "default_id": state.get("default_id"),
            "items": items,
            "history": [
                {
                    "version": entry.get("version"),
                    "updated_at": entry.get("updated_at"),
                    "revision": entry.get("revision"),
                }
                for entry in (state.get("history") or [])
            ],
        }

    def _sanitize_item(self, item: dict[str, Any]) -> dict[str, Any]:
        public = copy.deepcopy(item)
        public["apiKey"] = mask_secret(str(public.get("apiKey") or ""))
        public["hasApiKey"] = bool(item.get("apiKey"))
        return public

    @staticmethod
    def _find_item(state: dict[str, Any], provider_id: str) -> dict[str, Any]:
        for item in state.get("items") or []:
            if item.get("id") == provider_id:
                return item
        raise ValueError(f"model id not found: {provider_id}")

    def _sync_default_flags(self, state: dict[str, Any], preferred_id: str | None) -> None:
        items = state.get("items") or []
        if not items:
            state["default_id"] = None
            return
        target_id = preferred_id or state.get("default_id") or items[0]["id"]
        state["default_id"] = target_id
        for item in items:
            item["is_default"] = item["id"] == target_id

    @staticmethod
    def _normalize_model(payload: dict[str, Any], existing: dict[str, Any] | None) -> dict[str, Any]:
        raw_name = str(payload.get("name") or (existing or {}).get("name") or "").strip()
        raw_model = str(payload.get("model") or (existing or {}).get("model") or "").strip()
        raw_url = str(payload.get("url") or (existing or {}).get("url") or "").strip().rstrip("/")
        if not raw_name:
            raise ValueError("model name is required")
        if not raw_url:
            raise ValueError("model url is required")
        if not raw_model:
            raise ValueError("model field is required")
        api_key = payload.get("apiKey")
        if api_key in (None, "") and existing is not None:
            api_key = existing.get("apiKey") or ""
        provider_id = str(payload.get("id") or (existing or {}).get("id") or raw_name.lower().replace(" ", "-"))
        return {
            "id": provider_id,
            "name": raw_name,
            "url": raw_url,
            "apiKey": str(api_key or ""),
            "model": raw_model,
            "enabled": bool(payload.get("enabled", (existing or {}).get("enabled", True))),
            "is_default": bool(payload.get("is_default", (existing or {}).get("is_default", False))),
            "updated_at": now_utc_iso(),
        }
