"""Shared helpers for factor calculations."""

from __future__ import annotations

from datetime import datetime
from statistics import pstdev
from typing import Any


def parse_date(value: Any) -> datetime | None:
    if value in (None, "", "--"):
        return None
    text = str(value).strip().replace("/", "-")
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def linear_score(value: float, low: float, high: float) -> float:
    if high <= low:
        return 50.0
    ratio = (value - low) / (high - low)
    return max(0.0, min(100.0, ratio * 100.0))


def extract_nav_series(payload: dict[str, Any]) -> list[tuple[datetime, float]]:
    records = payload.get("records") or []
    points: list[tuple[datetime, float]] = []
    for row in records:
        nav_raw = row.get("unit_nav")
        if nav_raw in (None, "", "--"):
            continue
        try:
            nav = float(nav_raw)
        except (TypeError, ValueError):
            continue
        dt = parse_date(row.get("date") or row.get("nav_date") or row.get("trade_time"))
        if dt is None:
            continue
        points.append((dt, nav))
    points.sort(key=lambda item: item[0])
    return points


def extract_return_series(payload: dict[str, Any], nav_series: list[tuple[datetime, float]]) -> list[float]:
    records = payload.get("records") or []
    out: list[float] = []
    for row in records:
        raw = row.get("daily_change_pct")
        if raw in (None, "", "--"):
            continue
        try:
            out.append(float(raw) / 100.0)
        except (TypeError, ValueError):
            continue
    if out:
        return out
    derived: list[float] = []
    for idx in range(1, len(nav_series)):
        prev = nav_series[idx - 1][1]
        curr = nav_series[idx][1]
        if prev <= 0:
            continue
        derived.append((curr - prev) / prev)
    return derived


def pct_change(start: float, end: float) -> float:
    if start <= 0:
        return 0.0
    return (end - start) / start * 100.0


def std_pct(values: list[float]) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return abs(values[0]) * 100.0
    return pstdev(values) * 100.0


def max_drawdown_pct(nav_values: list[float]) -> float:
    if not nav_values:
        return 0.0
    peak = nav_values[0]
    max_dd = 0.0
    for value in nav_values:
        if value > peak:
            peak = value
        if peak <= 0:
            continue
        dd = (value - peak) / peak
        if dd < max_dd:
            max_dd = dd
    return max_dd * 100.0

