"""Eastmoney raw adapter."""

from __future__ import annotations

import time
from typing import Any

import requests

from services.data_hub.adapters.base import IDataSourceAdapter
from services.data_hub.exceptions import DataSourceError, DataUnavailableError
from services.data_hub.types import NormalizedEnvelope


class EastmoneyAdapter(IDataSourceAdapter):
    """Raw eastmoney adapter with browser camouflage headers."""

    def __init__(self, priority: int = 1, enabled: bool = True) -> None:
        super().__init__(name="eastmoney", priority=priority, enabled=enabled)
        self.session = requests.Session()
        self._app_headers = {
            "User-Agent": "EMProjJijin/6.2.8 (iPhone; iOS 13.6; Scale/2.00)",
            "GTOKEN": "98B423068C1F4DEF9842F82ADF08C5db",
            "clientInfo": "ttjj-iPhone10,1-iOS-iOS13.6",
            "Content-Type": "application/x-www-form-urlencoded",
            "Host": "fundmobapi.eastmoney.com",
            "Referer": "https://mpservice.com/516939c37bdb4ba2b1138c50cf69a2e1/release/pages/FundHistoryNetWorth",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        self._web_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            "Accept": "application/json,text/plain,*/*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }

    def fetch_realtime(self, symbol: str, **kwargs: Any) -> NormalizedEnvelope:
        timeout = int(kwargs.get("timeout_seconds", 20))
        url = "https://fundmobapi.eastmoney.com/FundMNewApi/FundMNFInfo"
        data = {
            "pageIndex": "1",
            "pageSize": "300000",
            "Sort": "",
            "Fcodes": symbol,
            "SortColumn": "",
            "IsShowSE": "false",
            "P": "F",
            "deviceid": "3EA024C2-7F22-408B-95E4-383D38160FB3",
            "plat": "Iphone",
            "product": "EFund",
            "version": "6.2.8",
        }
        try:
            resp = self.session.get(url, headers=self._app_headers, data=data, timeout=timeout)
            resp.raise_for_status()
            payload = resp.json()
            rows = payload.get("Datas") or []
        except Exception as exc:
            raise DataSourceError(f"eastmoney realtime request failed: {exc}") from exc
        if not rows:
            raise DataUnavailableError(f"eastmoney realtime returned empty for {symbol}")
        row = rows[0]
        record = {
            "symbol": row.get("FCODE") or symbol,
            "name": row.get("SHORTNAME"),
            "unit_nav": _to_float(row.get("NAV") or row.get("ACCNAV")),
            "daily_change_pct": _to_float(row.get("NAVCHGRT")),
            "estimated_nav": _to_float(row.get("GSZ")),
            "estimated_change_pct": _to_float(row.get("GSZZL")),
            "trade_time": row.get("GZTIME"),
            "nav_date": row.get("PDATE"),
        }
        return NormalizedEnvelope(
            metric="realtime",
            symbol=symbol,
            source=self.name,
            source_time=record.get("trade_time") or record.get("nav_date"),
            records=[record],
            quality_score=0.95 if record.get("estimated_nav") is not None else 0.86,
            metadata={"endpoint": "FundMNFInfo", "err_code": payload.get("ErrCode")},
        )

    def fetch_history(self, symbol: str, **kwargs: Any) -> NormalizedEnvelope:
        timeout = int(kwargs.get("timeout_seconds", 20))
        limit = int(kwargs.get("limit", 30))
        url = "https://api.fund.eastmoney.com/f10/lsjz"
        params = {"fundCode": symbol, "pageIndex": "1", "pageSize": str(limit)}
        headers = {**self._web_headers, "Referer": "https://fundf10.eastmoney.com/"}
        try:
            resp = self.session.get(url, params=params, headers=headers, timeout=timeout)
            resp.raise_for_status()
            payload = resp.json()
            rows = ((payload.get("Data") or {}).get("LSJZList") or [])
        except Exception as exc:
            raise DataSourceError(f"eastmoney history request failed: {exc}") from exc
        if not rows:
            raise DataUnavailableError(f"eastmoney history returned empty for {symbol}")
        records = []
        for item in rows:
            records.append(
                {
                    "date": item.get("FSRQ"),
                    "unit_nav": _to_float(item.get("DWJZ")),
                    "acc_nav": _to_float(item.get("LJJZ")),
                    "daily_change_pct": _to_float(item.get("JZZZL")),
                    "sub_status": item.get("SGZT"),
                    "red_status": item.get("SHZT"),
                }
            )
        return NormalizedEnvelope(
            metric="history",
            symbol=symbol,
            source=self.name,
            source_time=records[0].get("date"),
            records=records,
            quality_score=0.98,
            metadata={"endpoint": "f10/lsjz", "rows": len(records)},
        )

    def fetch_news(self, symbol: str | None = None, **kwargs: Any) -> NormalizedEnvelope:
        timeout = int(kwargs.get("timeout_seconds", 20))
        limit = int(kwargs.get("limit", 20))
        url = "https://np-weblist.eastmoney.com/comm/web/getFastNewsList"
        params = {
            "req_trace": str(int(time.time() * 1000)),
            "client": "web",
            "biz": "web_news_col",
            "order": "1",
            "pn": "1",
            "pz": str(limit),
        }
        headers = {**self._web_headers, "Referer": "https://kuaixun.eastmoney.com/"}
        try:
            resp = self.session.get(url, params=params, headers=headers, timeout=timeout)
            resp.raise_for_status()
            payload = resp.json()
            rows = ((payload.get("data") or {}).get("fastNewsList") or [])
        except Exception as exc:
            raise DataSourceError(f"eastmoney news request failed: {exc}") from exc
        if not rows:
            raise DataUnavailableError("eastmoney news returned empty")
        records = []
        market_records = []
        for item in rows:
            title = item.get("title") or item.get("digest") or item.get("content") or ""
            content = item.get("content") or item.get("digest") or title
            text_blob = f"{title} {content}"
            normalized = {
                "title": title,
                "content": content,
                "time": item.get("showtime") or item.get("time"),
                "source": item.get("media") or "eastmoney_fastnews",
                "url": item.get("url"),
                "relevance": 1.0 if (symbol and symbol in text_blob) else 0.2,
            }
            market_records.append(normalized)
            if symbol and symbol not in text_blob:
                continue
            records.append(normalized)
        fallback_mode = False
        if symbol and not records:
            records = market_records
            fallback_mode = True
        if not records:
            raise DataUnavailableError("eastmoney news returned empty after normalization")
        return NormalizedEnvelope(
            metric="news",
            symbol=symbol or "market",
            source=self.name,
            source_time=records[0].get("time") if records else None,
            records=records,
            quality_score=0.74 if fallback_mode else 0.82,
            metadata={"endpoint": "np-weblist", "rows": len(records), "fallback_mode": fallback_mode},
        )

    def fetch_flow(self, symbol: str | None = None, **kwargs: Any) -> NormalizedEnvelope:
        timeout = int(kwargs.get("timeout_seconds", 20))
        if not symbol:
            raise DataUnavailableError("symbol is required for eastmoney flow")
        secid = _to_secid(symbol)
        url = "https://push2.eastmoney.com/api/qt/stock/get"
        params = {
            "ut": "fa5fd1943c7b386f172d6893dbfba10b",
            "invt": "2",
            "fltt": "2",
            "fields": "f12,f14,f43,f47,f48,f170,f168,f169,f60,f117",
            "secid": secid,
        }
        try:
            resp = self.session.get(url, params=params, headers=self._web_headers, timeout=timeout)
            resp.raise_for_status()
            payload = resp.json()
            row = payload.get("data") or {}
        except Exception as exc:
            raise DataSourceError(f"eastmoney flow request failed: {exc}") from exc
        if not row:
            raise DataUnavailableError(f"eastmoney flow empty for {symbol}")
        records = [
            {
                "symbol": row.get("f12") or symbol,
                "name": row.get("f14"),
                "latest_price": _price_from_em(row.get("f43")),
                "volume": _to_float(row.get("f47")),
                "amount": _to_float(row.get("f48")),
                "change_pct": _to_float(row.get("f170")),
                "turnover_pct": _to_float(row.get("f168")),
                "market_cap": _to_float(row.get("f117")),
            }
        ]
        return NormalizedEnvelope(
            metric="flow",
            symbol=symbol,
            source=self.name,
            source_time=None,
            records=records,
            quality_score=0.88,
            metadata={"endpoint": "push2 stock/get", "secid": secid},
        )


def _to_float(value: Any) -> float | None:
    if value in (None, "", "--"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _price_from_em(raw: Any) -> float | None:
    # Eastmoney often returns integer price with x1000 factor in push2.
    val = _to_float(raw)
    if val is None:
        return None
    if val > 10000:
        return round(val / 1000.0, 4)
    return val


def _to_secid(symbol: str) -> str:
    if symbol.startswith(("5", "6", "9")):
        return f"1.{symbol}"
    return f"0.{symbol}"
