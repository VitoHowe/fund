"""Connectivity checks for Gemini, OpenAI and compatible APIs."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode, urlparse

import requests


def test_model_connection(url: str, api_key: str, model: str, timeout: int = 10) -> dict[str, Any]:
    if not url:
        raise ValueError("url is required")
    if not model:
        raise ValueError("model is required")
    provider = detect_provider(url)
    if provider == "gemini":
        return _test_gemini(url=url, api_key=api_key, model=model, timeout=timeout)
    return _test_openai_compatible(url=url, api_key=api_key, model=model, timeout=timeout)


def detect_provider(url: str) -> str:
    target = url.lower()
    if "generativelanguage.googleapis.com" in target or "gemini" in target:
        return "gemini"
    return "openai_compatible"


def _test_openai_compatible(url: str, api_key: str, model: str, timeout: int) -> dict[str, Any]:
    list_url = _normalize_openai_models_url(url)
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    result = {
        "provider": "openai_compatible",
        "resolved_url": list_url,
        "connectivity": {"ok": False, "status_code": None, "message": ""},
        "auth": {"ok": False, "status_code": None, "message": ""},
        "model": {"ok": False, "status_code": None, "message": "", "model": model},
    }
    try:
        response = requests.get(list_url, headers=headers, timeout=timeout)
    except requests.RequestException as exc:
        result["connectivity"]["message"] = f"network error: {exc}"
        result["ok"] = False
        return result
    result["connectivity"] = {
        "ok": True,
        "status_code": response.status_code,
        "message": "endpoint reachable",
    }
    if response.status_code in {401, 403}:
        result["auth"] = {
            "ok": False,
            "status_code": response.status_code,
            "message": "authentication rejected",
        }
        result["ok"] = False
        return result
    if response.status_code >= 400:
        result["auth"] = {
            "ok": False,
            "status_code": response.status_code,
            "message": f"unexpected status: {response.status_code}",
        }
        result["ok"] = False
        return result
    result["auth"] = {
        "ok": True,
        "status_code": response.status_code,
        "message": "credentials accepted",
    }
    payload = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
    data = payload.get("data") or []
    names = {str(item.get("id") or "") for item in data if isinstance(item, dict)}
    model_ok = model in names
    result["model"] = {
        "ok": model_ok,
        "status_code": response.status_code,
        "message": "model available" if model_ok else "model not returned by provider",
        "model": model,
        "available_models": sorted(name for name in names if name)[:30],
    }
    result["ok"] = bool(result["connectivity"]["ok"] and result["auth"]["ok"] and result["model"]["ok"])
    return result


def _test_gemini(url: str, api_key: str, model: str, timeout: int) -> dict[str, Any]:
    list_url = _normalize_gemini_models_url(url)
    query = urlencode({"key": api_key})
    resolved = f"{list_url}?{query}" if query else list_url
    result = {
        "provider": "gemini",
        "resolved_url": resolved,
        "connectivity": {"ok": False, "status_code": None, "message": ""},
        "auth": {"ok": False, "status_code": None, "message": ""},
        "model": {"ok": False, "status_code": None, "message": "", "model": model},
    }
    try:
        response = requests.get(resolved, timeout=timeout)
    except requests.RequestException as exc:
        result["connectivity"]["message"] = f"network error: {exc}"
        result["ok"] = False
        return result
    result["connectivity"] = {
        "ok": True,
        "status_code": response.status_code,
        "message": "endpoint reachable",
    }
    if response.status_code in {401, 403}:
        result["auth"] = {
            "ok": False,
            "status_code": response.status_code,
            "message": "authentication rejected",
        }
        result["ok"] = False
        return result
    if response.status_code >= 400:
        result["auth"] = {
            "ok": False,
            "status_code": response.status_code,
            "message": f"unexpected status: {response.status_code}",
        }
        result["ok"] = False
        return result
    result["auth"] = {
        "ok": True,
        "status_code": response.status_code,
        "message": "credentials accepted",
    }
    payload = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
    models = payload.get("models") or []
    names = {
        str(item.get("name") or "").replace("models/", "")
        for item in models
        if isinstance(item, dict) and item.get("name")
    }
    model_ok = model in names
    result["model"] = {
        "ok": model_ok,
        "status_code": response.status_code,
        "message": "model available" if model_ok else "model not returned by provider",
        "model": model,
        "available_models": sorted(name for name in names if name)[:30],
    }
    result["ok"] = bool(result["connectivity"]["ok"] and result["auth"]["ok"] and result["model"]["ok"])
    return result


def _normalize_openai_models_url(url: str) -> str:
    stripped = url.rstrip("/")
    if stripped.endswith("/models"):
        return stripped
    parsed = urlparse(stripped)
    if parsed.path.endswith("/v1"):
        return f"{stripped}/models"
    if "/v1/" in parsed.path:
        root = stripped.split("/v1/", 1)[0]
        return f"{root}/v1/models"
    return f"{stripped}/v1/models"


def _normalize_gemini_models_url(url: str) -> str:
    stripped = url.rstrip("/")
    if stripped.endswith("/models"):
        return stripped
    parsed = urlparse(stripped)
    root = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else stripped
    return f"{root}/v1beta/models"
