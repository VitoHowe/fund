"""AkShare adapter."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from services.data_hub.adapters.base import IDataSourceAdapter
from services.data_hub.exceptions import DataSourceError, DataUnavailableError
from services.data_hub.types import NormalizedEnvelope

try:
    import akshare as ak
except Exception:  # pragma: no cover
    ak = None


class AkShareAdapter(IDataSourceAdapter):
    """Adapter backed by AkShare."""

    def __init__(self, priority: int = 3, enabled: bool = True) -> None:
        super().__init__(name="akshare", priority=priority, enabled=enabled)
        self._open_rank_cache: tuple[datetime, Any] | None = None

    def fetch_realtime(self, symbol: str, **kwargs: Any) -> NormalizedEnvelope:
        df = self._get_open_fund_rank_df()
        hit = df[df["基金代码"].astype(str) == symbol]
        if hit.empty:
            raise DataUnavailableError(f"akshare realtime has no row for {symbol}")
        row = hit.iloc[0].to_dict()
        record = {
            "symbol": symbol,
            "name": row.get("基金简称"),
            "unit_nav": _to_float(row.get("单位净值")),
            "daily_change_pct": _to_float(row.get("日增长率")),
            "nav_date": _to_str(row.get("日期")),
            "week_change_pct": _to_float(row.get("近1周")),
            "month_change_pct": _to_float(row.get("近1月")),
        }
        return NormalizedEnvelope(
            metric="realtime",
            symbol=symbol,
            source=self.name,
            source_time=record.get("nav_date"),
            records=[record],
            quality_score=0.92,
            metadata={"method": "fund_open_fund_rank_em"},
        )

    def fetch_history(self, symbol: str, **kwargs: Any) -> NormalizedEnvelope:
        limit = int(kwargs.get("limit", 30))
        _ensure_akshare_available()
        try:
            df = ak.fund_info_index_em(symbol=symbol, indicator="单位净值走势")
            if df is None or df.empty:
                raise ValueError("empty result from fund_info_index_em")
            records = []
            # Column names differ by AkShare versions, resolve by position first.
            for _, row in df.head(limit).iterrows():
                item = row.to_dict()
                keys = list(item.keys())
                date_key = keys[0]
                nav_key = keys[1] if len(keys) > 1 else keys[0]
                records.append(
                    {
                        "date": _to_str(item.get(date_key)),
                        "unit_nav": _to_float(item.get(nav_key)),
                        "acc_nav": _to_float(item.get(keys[2])) if len(keys) > 2 else None,
                        "daily_change_pct": _to_float(item.get(keys[3])) if len(keys) > 3 else None,
                    }
                )
            if not records:
                raise ValueError("empty records from fund_info_index_em")
            return NormalizedEnvelope(
                metric="history",
                symbol=symbol,
                source=self.name,
                source_time=records[0].get("date"),
                records=records,
                quality_score=0.9,
                metadata={"method": "fund_info_index_em", "rows": len(records)},
            )
        except Exception:
            # Fallback to snapshot history if detailed history is unavailable.
            df_rank = self._get_open_fund_rank_df()
            hit = df_rank[df_rank["基金代码"].astype(str) == symbol]
            if hit.empty:
                raise DataUnavailableError(f"akshare history unavailable for {symbol}")
            row = hit.iloc[0].to_dict()
            date = _to_str(row.get("日期"))
            records = [
                {
                    "date": date,
                    "unit_nav": _to_float(row.get("单位净值")),
                    "acc_nav": _to_float(row.get("累计净值")),
                    "daily_change_pct": _to_float(row.get("日增长率")),
                }
            ]
            return NormalizedEnvelope(
                metric="history",
                symbol=symbol,
                source=self.name,
                source_time=date,
                records=records,
                quality_score=0.72,
                stale=True,
                metadata={"method": "fund_open_fund_rank_em(snapshot_fallback)"},
            )

    def fetch_news(self, symbol: str | None = None, **kwargs: Any) -> NormalizedEnvelope:
        _ensure_akshare_available()
        limit = int(kwargs.get("limit", 20))
        try:
            df = ak.stock_info_global_cls()
        except Exception as exc:
            raise DataSourceError(f"akshare news failed: {exc}") from exc
        if df is None or df.empty:
            raise DataUnavailableError("akshare global news returned empty")
        records = []
        for _, row in df.head(limit).iterrows():
            item = row.to_dict()
            title = item.get("标题") or ""
            content = item.get("内容") or title
            blob = f"{title} {content}"
            if symbol and symbol not in blob:
                continue
            records.append(
                {
                    "title": title,
                    "content": content,
                    "time": f"{item.get('发布日期')} {item.get('发布时间')}",
                    "source": "cls",
                }
            )
        if symbol and not records:
            raise DataUnavailableError(f"akshare news has no match for symbol={symbol}")
        return NormalizedEnvelope(
            metric="news",
            symbol=symbol or "market",
            source=self.name,
            source_time=records[0].get("time") if records else None,
            records=records,
            quality_score=0.85,
            metadata={"method": "stock_info_global_cls", "rows": len(records)},
        )

    def fetch_flow(self, symbol: str | None = None, **kwargs: Any) -> NormalizedEnvelope:
        _ensure_akshare_available()
        indicator = kwargs.get("indicator", "今日")
        sector_type = kwargs.get("sector_type", "行业资金流")
        limit = int(kwargs.get("limit", 20))
        try:
            df = ak.stock_sector_fund_flow_rank(indicator=indicator, sector_type=sector_type)
        except Exception as exc:
            raise DataSourceError(f"akshare flow failed: {exc}") from exc
        if df is None or df.empty:
            raise DataUnavailableError("akshare flow returned empty")
        records = []
        for _, row in df.head(limit).iterrows():
            item = row.to_dict()
            records.append(
                {
                    "sector": item.get("名称"),
                    "change_pct": _to_float(item.get(f"{indicator}涨跌幅")),
                    "main_net_inflow": _to_float(item.get(f"{indicator}主力净流入-净额")),
                    "main_inflow_ratio": _to_float(item.get(f"{indicator}主力净流入-净占比")),
                    "top_stock": item.get(f"{indicator}主力净流入最大股"),
                }
            )
        return NormalizedEnvelope(
            metric="flow",
            symbol=symbol or "market",
            source=self.name,
            source_time=None,
            records=records,
            quality_score=0.9,
            metadata={"method": "stock_sector_fund_flow_rank", "indicator": indicator, "sector_type": sector_type},
        )

    def _get_open_fund_rank_df(self):
        _ensure_akshare_available()
        now = datetime.now()
        if self._open_rank_cache and now - self._open_rank_cache[0] < timedelta(seconds=120):
            return self._open_rank_cache[1]
        try:
            df = ak.fund_open_fund_rank_em(symbol="全部")
        except Exception as exc:
            raise DataSourceError(f"akshare fund_open_fund_rank_em failed: {exc}") from exc
        self._open_rank_cache = (now, df)
        return df


def _ensure_akshare_available() -> None:
    if ak is None:
        raise DataSourceError("akshare is not installed")


def _to_float(value: Any) -> float | None:
    if value in (None, "", "--"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)

