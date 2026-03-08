"""Source health monitoring and alert evaluation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class MonitorAlert:
    level: str
    source: str
    message: str
    metric: str = "all"
    triggered_at_utc: str = field(default_factory=now_utc_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SourceMonitorConfig:
    max_consecutive_failures_warn: int = 2
    max_consecutive_failures_critical: int = 4
    max_avg_latency_warn_ms: float = 1200.0
    max_avg_latency_critical_ms: float = 3000.0


class SourceMonitor:
    """Generate status snapshot and alerts for data sources."""

    def __init__(self, source_manager: Any, config: SourceMonitorConfig | None = None) -> None:
        self.source_manager = source_manager
        self.config = config or SourceMonitorConfig()

    def snapshot(self) -> dict[str, Any]:
        items = self.source_manager.get_source_health()
        alerts = self._evaluate_alerts(items)
        overall = _overall_status(items, alerts)
        state_counts = {
            "ok": sum(1 for item in items if item.get("route_state") == "ok"),
            "degraded": sum(1 for item in items if item.get("route_state") == "degraded"),
            "unavailable": sum(1 for item in items if item.get("route_state") == "unavailable"),
            "idle": sum(1 for item in items if item.get("route_state") == "idle"),
            "disabled": sum(1 for item in items if item.get("route_state") == "disabled"),
        }
        return {
            "captured_at_utc": now_utc_iso(),
            "overall_status": overall,
            "source_count": len(items),
            "state_counts": state_counts,
            "sources": items,
            "alerts": [item.to_dict() for item in alerts],
        }

    def prometheus_text(self) -> str:
        snapshot = self.snapshot()
        lines: list[str] = []
        lines.append("# HELP fund_data_source_enabled Source enabled flag (1 enabled, 0 disabled)")
        lines.append("# TYPE fund_data_source_enabled gauge")
        lines.append("# HELP fund_data_source_failure_count Source failure count")
        lines.append("# TYPE fund_data_source_failure_count gauge")
        lines.append("# HELP fund_data_source_consecutive_failures Source consecutive failures")
        lines.append("# TYPE fund_data_source_consecutive_failures gauge")
        lines.append("# HELP fund_data_source_avg_latency_ms Source average latency in ms")
        lines.append("# TYPE fund_data_source_avg_latency_ms gauge")
        lines.append("# HELP fund_data_source_route_state Source route state marker")
        lines.append("# TYPE fund_data_source_route_state gauge")
        for item in snapshot["sources"]:
            source = item.get("source")
            enabled = 1 if item.get("enabled") else 0
            failure_count = float(item.get("failure_count") or 0)
            consecutive = float(item.get("consecutive_failures") or 0)
            latency = float(item.get("avg_latency_ms") or 0.0)
            route_state = item.get("route_state") or "idle"
            lines.append(f'fund_data_source_enabled{{source="{source}"}} {enabled}')
            lines.append(f'fund_data_source_failure_count{{source="{source}"}} {failure_count}')
            lines.append(f'fund_data_source_consecutive_failures{{source="{source}"}} {consecutive}')
            lines.append(f'fund_data_source_avg_latency_ms{{source="{source}"}} {latency}')
            lines.append(f'fund_data_source_route_state{{source="{source}",state="{route_state}"}} 1')
        lines.append("# HELP fund_data_source_alert_total Active monitor alerts")
        lines.append("# TYPE fund_data_source_alert_total gauge")
        lines.append(f'fund_data_source_alert_total{{level="critical"}} {sum(1 for a in snapshot["alerts"] if a["level"]=="critical")}')
        lines.append(f'fund_data_source_alert_total{{level="warning"}} {sum(1 for a in snapshot["alerts"] if a["level"]=="warning")}')
        return "\n".join(lines) + "\n"

    def _evaluate_alerts(self, items: list[dict[str, Any]]) -> list[MonitorAlert]:
        alerts: list[MonitorAlert] = []
        for item in items:
            source = str(item.get("source"))
            if not item.get("enabled", True):
                alerts.append(MonitorAlert(level="warning", source=source, message="source disabled"))
            route_state = str(item.get("route_state") or "idle")
            if route_state == "unavailable":
                detail = item.get("error_type") or item.get("error_message") or "unknown"
                alerts.append(MonitorAlert(level="critical", source=source, message=f"source unavailable: {detail}"))
            elif route_state == "degraded":
                detail = item.get("fallback_source") or item.get("error_type") or "fallback"
                alerts.append(MonitorAlert(level="warning", source=source, message=f"source degraded: {detail}"))
            consecutive = int(item.get("consecutive_failures") or 0)
            latency = float(item.get("avg_latency_ms") or 0.0)
            if consecutive >= self.config.max_consecutive_failures_critical:
                alerts.append(
                    MonitorAlert(
                        level="critical",
                        source=source,
                        message=f"consecutive failures too high: {consecutive}",
                    )
                )
            elif consecutive >= self.config.max_consecutive_failures_warn:
                alerts.append(
                    MonitorAlert(
                        level="warning",
                        source=source,
                        message=f"consecutive failures warning: {consecutive}",
                    )
                )
            if latency >= self.config.max_avg_latency_critical_ms:
                alerts.append(
                    MonitorAlert(
                        level="critical",
                        source=source,
                        message=f"avg latency too high: {latency:.2f}ms",
                    )
                )
            elif latency >= self.config.max_avg_latency_warn_ms:
                alerts.append(
                    MonitorAlert(
                        level="warning",
                        source=source,
                        message=f"avg latency warning: {latency:.2f}ms",
                    )
                )
            if item.get("circuit_open_until"):
                alerts.append(
                    MonitorAlert(
                        level="warning",
                        source=source,
                        message=f"circuit open until {item.get('circuit_open_until')}",
                    )
                )
        return alerts


def _overall_status(items: list[dict[str, Any]], alerts: list[MonitorAlert]) -> str:
    if not items:
        return "unknown"
    if any(item.level == "critical" for item in alerts):
        return "critical"
    if any(item.level == "warning" for item in alerts):
        return "warning"
    return "healthy"

