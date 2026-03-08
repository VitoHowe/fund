"""Runtime HTTP API and admin console delivery for fund intel."""

from __future__ import annotations

import hashlib
import hmac
import json
import mimetypes
import os
import secrets
import sys
import threading
import time
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlparse

# Allow running as `python apps/api/report_api.py` from repo root without extra PYTHONPATH setup.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.backtest import BacktestRunner
from services.config import ModelSettingsManager, StrategySettingsManager, now_utc_iso
from services.data_hub import build_default_source_manager
from services.factor_engine import FactorScorer, WeightTemplateManager, build_default_factor_registry
from services.llm import test_model_connection
from services.news_pipeline import NewsFusionService
from services.observability import SourceMonitor
from services.reporting import DailyReportOptions, DailyReportService
from services.reporting.report_cache import ReportCache

APP_STATIC_ROOT = ROOT / "apps" / "web" / "static"
PUBLIC_PAGE_ROUTES = {"/", "/login"}
PROTECTED_PAGE_PREFIXES = ("/dashboard", "/fund", "/settings")
SESSION_COOKIE_NAME = "fund_session"
DEFAULT_REPORT_SCOPE = ["014943", "159870"]
WATCHLIST_SCOPE = ["014943", "159870", "512660", "515790", "518880", "159516"]
ALL_MARKET_SCOPE = [
    "159326",
    "515220",
    "561360",
    "159611",
    "159201",
    "159870",
    "516150",
    "515790",
    "515210",
    "518880",
    "512400",
    "515880",
    "512660",
    "159206",
    "512800",
    "159865",
    "159755",
    "512880",
    "159516",
    "512170",
    "159852",
    "512690",
    "159851",
    "512200",
    "159766",
    "159869",
]
REPORT_SCOPE_SYMBOLS = {
    "default": DEFAULT_REPORT_SCOPE,
    "watchlist": WATCHLIST_SCOPE,
    "all_market": ALL_MARKET_SCOPE,
}
STRATEGY_TEMPLATE_TO_STATE = {
    "保守": "bear",
    "bear": "bear",
    "defensive": "bear",
    "平衡": "neutral",
    "neutral": "neutral",
    "balanced": "neutral",
    "进取": "bull",
    "bull": "bull",
    "aggressive": "bull",
}


class ApiError(Exception):
    """Structured API error."""

    def __init__(
        self,
        status: HTTPStatus,
        message: str,
        *,
        payload: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.payload = payload or {}


class SessionStore:
    """Small in-memory session storage for admin pages and protected APIs."""

    def __init__(self, ttl_seconds: int = 60 * 60 * 12) -> None:
        self.ttl_seconds = ttl_seconds
        self._lock = threading.RLock()
        self._sessions: dict[str, dict[str, Any]] = {}

    def create(self, *, username: str) -> dict[str, Any]:
        token = secrets.token_urlsafe(32)
        now = time.time()
        session = {
            "token": token,
            "username": username,
            "created_at": now_utc_iso(),
            "expires_at_epoch": now + self.ttl_seconds,
            "expires_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now + self.ttl_seconds)),
        }
        with self._lock:
            self._cleanup_locked()
            self._sessions[token] = session
        return session

    def get(self, token: str | None) -> dict[str, Any] | None:
        if not token:
            return None
        with self._lock:
            self._cleanup_locked()
            session = self._sessions.get(token)
            if not session:
                return None
            return dict(session)

    def revoke(self, token: str | None) -> None:
        if not token:
            return
        with self._lock:
            self._sessions.pop(token, None)

    def _cleanup_locked(self) -> None:
        now = time.time()
        expired = [token for token, session in self._sessions.items() if session.get("expires_at_epoch", 0) <= now]
        for token in expired:
            self._sessions.pop(token, None)


class LoginAttemptTracker:
    """Very small lockout tracker to slow down repeated password guessing."""

    def __init__(self, max_failures: int = 5, lock_seconds: int = 60) -> None:
        self.max_failures = max_failures
        self.lock_seconds = lock_seconds
        self._lock = threading.RLock()
        self._state: dict[str, dict[str, Any]] = {}

    def check(self, key: str) -> dict[str, Any]:
        with self._lock:
            record = self._state.get(key) or {"failures": 0, "locked_until": 0.0}
            remaining = max(0.0, float(record.get("locked_until") or 0.0) - time.time())
            return {
                "allowed": remaining <= 0,
                "remaining_seconds": int(remaining),
                "failures": int(record.get("failures") or 0),
            }

    def record_failure(self, key: str) -> dict[str, Any]:
        with self._lock:
            record = self._state.get(key) or {"failures": 0, "locked_until": 0.0}
            record["failures"] = int(record.get("failures") or 0) + 1
            if record["failures"] >= self.max_failures:
                record["locked_until"] = time.time() + self.lock_seconds
                record["failures"] = 0
            self._state[key] = record
        return self.check(key)

    def record_success(self, key: str) -> None:
        with self._lock:
            self._state.pop(key, None)


def build_runtime() -> dict[str, Any]:
    source_manager = build_default_source_manager()
    factor_scorer = FactorScorer(
        source_manager=source_manager,
        registry=build_default_factor_registry(),
        weight_manager=WeightTemplateManager(config_path="config/factor_weights.yaml"),
    )
    news_service = NewsFusionService(source_manager=source_manager)
    backtest_runner = BacktestRunner(source_manager=source_manager, factor_scorer=factor_scorer)
    model_settings = ModelSettingsManager(config_path="config/model_providers.json")
    strategy_settings = StrategySettingsManager(config_path="config/strategy_profiles.json")
    service = DailyReportService(
        source_manager=source_manager,
        factor_scorer=factor_scorer,
        news_service=news_service,
        backtest_runner=backtest_runner,
        strategy_provider=lambda: strategy_settings.build_enabled_strategies(force_reload=False),
        strategy_snapshot_provider=lambda: strategy_settings.get_runtime_snapshot(force_reload=False),
        model_runtime_provider=lambda: model_settings.get_runtime_model(force_reload=False),
    )
    return {
        "source_manager": source_manager,
        "service": service,
        "monitor": SourceMonitor(source_manager=source_manager),
        "backtest_runner": backtest_runner,
        "model_settings": model_settings,
        "strategy_settings": strategy_settings,
        "report_cache": ReportCache(root_path="data/reports"),
        "sessions": SessionStore(),
        "login_attempts": LoginAttemptTracker(),
    }


class ReportApiHandler(BaseHTTPRequestHandler):
    """HTTP handler with JSON APIs and static admin console."""

    runtime = build_runtime()

    def do_GET(self) -> None:  # noqa: N802
        self._dispatch("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch("POST")

    def do_PUT(self) -> None:  # noqa: N802
        self._dispatch("PUT")

    def _dispatch(self, method: str) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        qs = parse_qs(parsed.query)
        try:
            if method == "GET":
                self._handle_get(path, qs, parsed.query)
                return
            if method == "POST":
                body = self._read_json_body()
                self._handle_post(path, qs, body)
                return
            if method == "PUT":
                body = self._read_json_body()
                self._handle_put(path, body)
                return
            raise ApiError(HTTPStatus.METHOD_NOT_ALLOWED, f"method not allowed: {method}")
        except ApiError as exc:
            payload = {"error": exc.message, **exc.payload}
            self._send_json(payload, status=exc.status)
        except Exception as exc:  # pragma: no cover
            self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def _handle_get(self, path: str, qs: dict[str, list[str]], raw_query: str) -> None:
        if path == "/health":
            self._send_json({"status": "ok", "service": "report_api"})
            return
        if path == "/metrics":
            data = self.runtime["monitor"].prometheus_text().encode("utf-8")
            self._send_bytes(data=data, content_type="text/plain; version=0.0.4; charset=utf-8")
            return
        if path == "/api/auth/session":
            session = self._get_session()
            self._send_json(
                {
                    "authenticated": bool(session),
                    "session": {
                        "username": session.get("username"),
                        "created_at": session.get("created_at"),
                        "expires_at": session.get("expires_at"),
                    }
                    if session
                    else None,
                    "config_versions": self._runtime_versions(),
                }
            )
            return
        if path == "/api/monitor/data-sources":
            snapshot = self.runtime["monitor"].snapshot()
            snapshot["recent_audit_events"] = self.runtime["source_manager"].get_recent_audit_events(limit=10)
            snapshot["audit_event_count"] = len(snapshot["recent_audit_events"])
            self._send_json(snapshot)
            return
        if path == "/api/monitor/audit-events":
            self._send_json(
                {
                    "events": self.runtime["source_manager"].get_recent_audit_events(limit=_int_query(qs, "limit", 50)),
                    "captured_at_utc": now_utc_iso(),
                }
            )
            return
        if path == "/api/report/daily":
            self._send_json(self._generate_report(qs))
            return
        if path == "/api/report/daily/latest":
            latest = self.runtime["report_cache"].get_latest_daily_report()
            if latest is None or "strategy_profile" not in latest or "data_pipeline" not in latest:
                latest = self._generate_report({})
            self._send_json(latest)
            return
        if path == "/api/report/fund-detail":
            symbol = (qs.get("symbol") or ["014943"])[0]
            report = self._generate_report({"symbols": [symbol]})
            detail = (report.get("fund_details") or [None])[0]
            self._send_json(
                {
                    "symbol": symbol,
                    "detail": detail,
                    "report_id": report.get("report_id"),
                    "strategy_profile": report.get("strategy_profile"),
                    "model_usage": report.get("model_usage"),
                    "data_pipeline": report.get("data_pipeline"),
                    "quality_score": report.get("quality_score"),
                }
            )
            return
        if path == "/api/report/export":
            fmt = ((qs.get("format") or ["md"])[0]).lower()
            report_obj = self.runtime["service"].generate_daily_report(
                symbols=self._parse_symbols(qs),
                proxy_symbol_map={"014943": "159870"},
                options=DailyReportOptions(
                    market_state=_resolve_market_state(qs),
                    stable_only=_bool_lookup(qs, "stable_only", False),
                ),
            )
            self.runtime["report_cache"].save_daily_report(report_obj.to_dict())
            data = self.runtime["service"].export_report(report_obj, fmt=fmt)
            content_type = {
                "md": "text/markdown; charset=utf-8",
                "html": "text/html; charset=utf-8",
                "pdf": "application/pdf",
            }.get(fmt, "application/octet-stream")
            filename = f"{report_obj.report_id}.{fmt}"
            self._send_bytes(data=data, content_type=content_type, filename=filename)
            return
        if path == "/api/settings/models":
            self._require_session()
            self._send_json(self.runtime["model_settings"].list_models())
            return
        if path == "/api/settings/models/reload":
            self._require_session()
            self._send_json(self.runtime["model_settings"].reload())
            return
        if path == "/api/settings/strategies":
            self._require_session()
            self._send_json(self.runtime["strategy_settings"].list_profiles())
            return
        if path == "/api/settings/strategies/reload":
            self._require_session()
            self._send_json(self.runtime["strategy_settings"].reload())
            return
        if path == "/api/settings/runtime":
            self._require_session()
            self._send_json({"versions": self._runtime_versions(), "captured_at_utc": now_utc_iso()})
            return
        if path.startswith("/assets/"):
            self._serve_static_asset(path)
            return
        if self._is_page_route(path):
            if self._page_requires_session(path) and not self._get_session():
                self._send_redirect(f"/login?next={quote(path)}")
                return
            self._serve_app_shell(path, raw_query)
            return
        raise ApiError(HTTPStatus.NOT_FOUND, "endpoint not found")

    def _handle_post(self, path: str, qs: dict[str, list[str]], body: dict[str, Any]) -> None:
        if path == "/api/auth/login":
            self._handle_login(body)
            return
        if path == "/api/auth/logout":
            token = self._session_token()
            self.runtime["sessions"].revoke(token)
            self._send_json({"ok": True}, headers={"Set-Cookie": self._expired_cookie()})
            return
        if path == "/api/report/daily/generate":
            payload = self._generate_report(body or qs)
            self._send_json(payload)
            return
        if path == "/api/settings/models":
            self._require_session()
            self._send_json(self.runtime["model_settings"].create_model(body), status=HTTPStatus.CREATED)
            return
        if path == "/api/settings/models/reload":
            self._require_session()
            self._send_json(self.runtime["model_settings"].reload())
            return
        if path == "/api/settings/strategies":
            self._require_session()
            self._send_json(self.runtime["strategy_settings"].create_profile(body), status=HTTPStatus.CREATED)
            return
        if path == "/api/settings/strategies/reload":
            self._require_session()
            self._send_json(self.runtime["strategy_settings"].reload())
            return
        if path.startswith("/api/settings/models/"):
            self._require_session()
            provider_id, action = self._extract_item_action(path, "/api/settings/models/")
            manager = self.runtime["model_settings"]
            if action == "default":
                self._send_json(manager.set_default(provider_id))
                return
            if action == "enabled":
                self._send_json(manager.set_enabled(provider_id, bool(body.get("enabled", True))))
                return
            if action == "test":
                config = manager.get_model(provider_id)
                config.update({key: body[key] for key in ("url", "apiKey", "model") if key in body})
                self._send_json(
                    test_model_connection(
                        url=str(config.get("url") or ""),
                        api_key=str(config.get("apiKey") or ""),
                        model=str(config.get("model") or ""),
                        timeout=int(body.get("timeout") or 10),
                    )
                )
                return
            raise ApiError(HTTPStatus.NOT_FOUND, "model action not found")
        if path.startswith("/api/settings/strategies/"):
            self._require_session()
            strategy_id, action = self._extract_item_action(path, "/api/settings/strategies/")
            manager = self.runtime["strategy_settings"]
            if action == "default":
                self._send_json(manager.set_default(strategy_id))
                return
            if action == "enabled":
                self._send_json(manager.set_enabled(strategy_id, bool(body.get("enabled", True))))
                return
            if action == "rollback":
                self._send_json(manager.rollback_profile(strategy_id, str(body.get("version") or "")))
                return
            if action == "replay-tune":
                symbols = self._parse_symbols(body or qs)
                self._send_json(
                    manager.replay_and_tune(
                        strategy_id,
                        backtest_runner=self.runtime["backtest_runner"],
                        symbols=symbols,
                        market_state=_resolve_market_state(body or qs),
                        limit=int(body.get("limit") or 120),
                        persist=bool(body.get("persist", False)),
                    )
                )
                return
            raise ApiError(HTTPStatus.NOT_FOUND, "strategy action not found")
        raise ApiError(HTTPStatus.NOT_FOUND, "endpoint not found")

    def _handle_put(self, path: str, body: dict[str, Any]) -> None:
        if path.startswith("/api/settings/models/"):
            self._require_session()
            provider_id = unquote(path.rsplit("/", 1)[-1])
            self._send_json(self.runtime["model_settings"].update_model(provider_id, body))
            return
        if path.startswith("/api/settings/strategies/"):
            self._require_session()
            strategy_id = unquote(path.rsplit("/", 1)[-1])
            self._send_json(self.runtime["strategy_settings"].update_profile(strategy_id, body))
            return
        raise ApiError(HTTPStatus.NOT_FOUND, "endpoint not found")

    def _handle_login(self, body: dict[str, Any]) -> None:
        client_key = self.client_address[0] if self.client_address else "unknown"
        tracker = self.runtime["login_attempts"]
        attempt = tracker.check(client_key)
        if not attempt["allowed"]:
            raise ApiError(
                HTTPStatus.TOO_MANY_REQUESTS,
                "too many failed attempts",
                payload={"retry_after_seconds": attempt["remaining_seconds"]},
            )
        password = str(body.get("password") or "")
        if not self._verify_password(password):
            after_failure = tracker.record_failure(client_key)
            raise ApiError(
                HTTPStatus.UNAUTHORIZED,
                "invalid password",
                payload={"retry_after_seconds": after_failure["remaining_seconds"]},
            )
        tracker.record_success(client_key)
        session = self.runtime["sessions"].create(username="admin")
        self._send_json(
            {
                "ok": True,
                "authenticated": True,
                "session": {
                    "username": session["username"],
                    "created_at": session["created_at"],
                    "expires_at": session["expires_at"],
                },
            },
            headers={"Set-Cookie": self._build_session_cookie(session["token"])},
        )

    def _generate_report(self, source: dict[str, Any]) -> dict[str, Any]:
        symbols = self._parse_symbols(source)
        market_state = _resolve_market_state(source)
        report = self.runtime["service"].generate_daily_report(
            symbols=symbols,
            proxy_symbol_map={"014943": "159870"},
            options=DailyReportOptions(
                market_state=market_state,
                stable_only=_bool_lookup(source, "stable_only", False),
            ),
        )
        payload = report.to_dict()
        self.runtime["report_cache"].save_daily_report(payload)
        return payload

    @staticmethod
    def _parse_symbols(source: dict[str, Any]) -> list[str]:
        scope = str(_lookup(source, "report_scope", "default") or "default").strip().lower()
        default_symbols = REPORT_SCOPE_SYMBOLS.get(scope, DEFAULT_REPORT_SCOPE)
        raw_value = _lookup(source, "symbols", ",".join(default_symbols))
        if isinstance(raw_value, list):
            values = [str(item).strip() for item in raw_value if str(item).strip()]
        else:
            values = [item.strip() for item in str(raw_value).split(",") if item.strip()]
        return values or list(default_symbols or DEFAULT_REPORT_SCOPE)

    def _require_session(self) -> dict[str, Any]:
        session = self._get_session()
        if not session:
            raise ApiError(HTTPStatus.UNAUTHORIZED, "authentication required")
        return session

    def _get_session(self) -> dict[str, Any] | None:
        return self.runtime["sessions"].get(self._session_token())

    def _session_token(self) -> str | None:
        raw_cookie = self.headers.get("Cookie") or ""
        cookie = SimpleCookie()
        cookie.load(raw_cookie)
        morsel = cookie.get(SESSION_COOKIE_NAME)
        return morsel.value if morsel else None

    def _verify_password(self, password: str) -> bool:
        candidate = hashlib.sha256(password.encode("utf-8")).hexdigest()
        expected = _password_hash()
        return hmac.compare_digest(candidate, expected)

    def _serve_app_shell(self, path: str, raw_query: str) -> None:
        index_path = APP_STATIC_ROOT / "index.html"
        if not index_path.exists():
            raise ApiError(HTTPStatus.NOT_FOUND, "frontend shell not found")
        content = index_path.read_text(encoding="utf-8")
        content = content.replace("__PAGE_PATH__", path).replace("__PAGE_QUERY__", raw_query)
        self._send_bytes(content.encode("utf-8"), content_type="text/html; charset=utf-8")

    def _serve_static_asset(self, path: str) -> None:
        relative = path.removeprefix("/assets/")
        file_path = (APP_STATIC_ROOT / relative).resolve()
        if not file_path.is_file() or not str(file_path).startswith(str(APP_STATIC_ROOT.resolve())):
            raise ApiError(HTTPStatus.NOT_FOUND, "asset not found")
        content_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
        self._send_bytes(file_path.read_bytes(), content_type=content_type)

    def _runtime_versions(self) -> dict[str, Any]:
        model_state = self.runtime["model_settings"].list_models(force_reload=False)
        strategy_state = self.runtime["strategy_settings"].list_profiles(force_reload=False)
        return {
            "models": {
                "version": model_state.get("version"),
                "updated_at": model_state.get("updated_at"),
                "default_id": model_state.get("default_id"),
            },
            "strategies": {
                "version": strategy_state.get("version"),
                "updated_at": strategy_state.get("updated_at"),
                "default_id": strategy_state.get("default_id"),
            },
        }

    def _read_json_body(self) -> dict[str, Any]:
        raw_length = self.headers.get("Content-Length") or "0"
        length = int(raw_length) if raw_length.isdigit() else 0
        if length <= 0:
            return {}
        body = self.rfile.read(length).decode("utf-8")
        if not body.strip():
            return {}
        return json.loads(body)

    @staticmethod
    def _extract_item_action(path: str, prefix: str) -> tuple[str, str]:
        tail = path.removeprefix(prefix)
        parts = [unquote(part) for part in tail.split("/") if part]
        if len(parts) < 2:
            raise ApiError(HTTPStatus.BAD_REQUEST, "invalid action path")
        return parts[0], parts[1]

    @staticmethod
    def _is_page_route(path: str) -> bool:
        return path in PUBLIC_PAGE_ROUTES or path.startswith(PROTECTED_PAGE_PREFIXES)

    @staticmethod
    def _page_requires_session(path: str) -> bool:
        return path.startswith(PROTECTED_PAGE_PREFIXES)

    def _send_json(
        self,
        payload: dict[str, Any],
        *,
        status: HTTPStatus = HTTPStatus.OK,
        headers: dict[str, str] | None = None,
    ) -> None:
        data = json.dumps(payload, ensure_ascii=False, indent=2, default=str).encode("utf-8")
        self.send_response(int(status))
        self.send_header("Content-Type", "application/json; charset=utf-8")
        if headers:
            for key, value in headers.items():
                self.send_header(key, value)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_bytes(
        self,
        data: bytes,
        *,
        content_type: str,
        filename: str | None = None,
        status: HTTPStatus = HTTPStatus.OK,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.send_response(int(status))
        self.send_header("Content-Type", content_type)
        if headers:
            for key, value in headers.items():
                self.send_header(key, value)
        if filename:
            self.send_header("Content-Disposition", f"attachment; filename={filename}")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_redirect(self, location: str) -> None:
        self.send_response(HTTPStatus.FOUND)
        self.send_header("Location", location)
        self.end_headers()

    @staticmethod
    def _build_session_cookie(token: str) -> str:
        return (
            f"{SESSION_COOKIE_NAME}={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=43200"
        )

    @staticmethod
    def _expired_cookie() -> str:
        return f"{SESSION_COOKIE_NAME}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"


def _password_hash() -> str:
    if os.getenv("FUND_ADMIN_PASSWORD_HASH"):
        return str(os.getenv("FUND_ADMIN_PASSWORD_HASH")).strip().lower()
    plain = os.getenv("FUND_ADMIN_PASSWORD", "fund-admin")
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()


def _lookup(source: dict[str, Any], key: str, default: Any) -> Any:
    value = source.get(key, default)
    if isinstance(value, list) and value:
        return value[0]
    return value


def _resolve_market_state(source: dict[str, Any]) -> str:
    raw_value = _lookup(source, "strategy_profile", None)
    if raw_value in (None, "", "--"):
        raw_value = _lookup(source, "market_state", "neutral")
    key = str(raw_value or "neutral").strip().lower()
    return STRATEGY_TEMPLATE_TO_STATE.get(key, "neutral")


def _int_query(qs: dict[str, list[str]], key: str, default: int) -> int:
    raw = _lookup(qs, key, default)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _bool_lookup(source: dict[str, Any], key: str, default: bool) -> bool:
    raw = _lookup(source, key, default)
    if isinstance(raw, bool):
        return raw
    if raw in (None, "", "--"):
        return default
    text = str(raw).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def run_server(host: str = "0.0.0.0", port: int = 8010) -> None:
    server = ThreadingHTTPServer((host, port), ReportApiHandler)
    print(f"Report API listening on http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run_server()
