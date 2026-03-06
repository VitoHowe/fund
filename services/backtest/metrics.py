"""Backtest KPI utilities."""

from __future__ import annotations

import math
from statistics import pstdev


def compute_max_drawdown_pct(equity_values: list[float]) -> float:
    if not equity_values:
        return 0.0
    peak = equity_values[0]
    max_dd = 0.0
    for value in equity_values:
        if value > peak:
            peak = value
        if peak <= 0:
            continue
        drawdown = (value - peak) / peak
        if drawdown < max_dd:
            max_dd = drawdown
    return max_dd * 100.0


def compute_sharpe_ratio(daily_returns: list[float], risk_free_daily: float = 0.0) -> float:
    if not daily_returns:
        return 0.0
    excess = [item - risk_free_daily for item in daily_returns]
    mean_excess = sum(excess) / len(excess)
    std = pstdev(excess) if len(excess) > 1 else abs(excess[0])
    if std <= 1e-12:
        return 0.0
    return (mean_excess / std) * math.sqrt(252.0)


def compute_kpis(
    equity_curve: list[dict[str, float | str]],
    initial_capital: float,
    trade_count: int,
    turnover: float,
) -> dict[str, float]:
    if not equity_curve:
        return {
            "total_return_pct": 0.0,
            "annualized_return_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "win_rate": 0.0,
            "sharpe": 0.0,
            "turnover_ratio": 0.0,
            "trade_count": float(trade_count),
        }
    equity_values = [float(item["equity"]) for item in equity_curve]
    returns: list[float] = []
    for idx in range(1, len(equity_values)):
        prev = equity_values[idx - 1]
        curr = equity_values[idx]
        if prev <= 0:
            continue
        returns.append((curr - prev) / prev)
    final_equity = equity_values[-1]
    total_return = (final_equity / initial_capital - 1.0) * 100.0 if initial_capital > 0 else 0.0
    periods = max(len(returns), 1)
    annualized = ((final_equity / initial_capital) ** (252.0 / periods) - 1.0) * 100.0 if initial_capital > 0 else 0.0
    win_days = sum(1 for item in returns if item > 0)
    win_rate = win_days / len(returns) if returns else 0.0
    sharpe = compute_sharpe_ratio(returns)
    return {
        "total_return_pct": round(total_return, 4),
        "annualized_return_pct": round(annualized, 4),
        "max_drawdown_pct": round(compute_max_drawdown_pct(equity_values), 4),
        "win_rate": round(win_rate, 4),
        "sharpe": round(sharpe, 4),
        "turnover_ratio": round(turnover / max(len(returns), 1), 6),
        "trade_count": float(trade_count),
    }

