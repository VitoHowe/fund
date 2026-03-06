# Fund API 总结

## 1. 文档目的

本文整理当前仓库中已经存在的 API 能力，分为两类：

- 契约接口：定义在 `docs/api/openapi.yaml`，代表数据接入层的统一接口基线。
- 运行时接口：实现于 `apps/api/report_api.py`，当前本地可直接启动和验证。

当前状态需要明确区分：`openapi.yaml` 覆盖了数据接入层接口，但尚未覆盖报表运行时接口；运行时接口已经可用，但未同步回 OpenAPI 文档。

## 2. 接口总览

| 分类 | Method | 路径 | 用途 | 当前状态 |
|---|---|---|---|---|
| 契约 | `GET` | `/v1/data/realtime/{symbol}` | 查询统一实时行情/净值 | OpenAPI 已定义，运行时未在 `report_api.py` 暴露 |
| 契约 | `GET` | `/v1/data/history/{symbol}` | 查询统一历史净值/价格序列 | OpenAPI 已定义，运行时未在 `report_api.py` 暴露 |
| 契约 | `GET` | `/v1/data/news` | 查询统一新闻数据 | OpenAPI 已定义，运行时未在 `report_api.py` 暴露 |
| 契约 | `GET` | `/v1/data/flow` | 查询基金/板块资金流 | OpenAPI 已定义，运行时未在 `report_api.py` 暴露 |
| 契约 | `GET` | `/v1/sources/health` | 查询数据源健康状态 | OpenAPI 已定义，运行时存在近似实现 `/api/monitor/data-sources` |
| 运行时 | `GET` | `/health` | API 存活检查 | 已实现 |
| 运行时 | `GET` | `/api/monitor/data-sources` | 获取全链路数据源状态与告警 | 已实现 |
| 运行时 | `GET` | `/metrics` | 导出 Prometheus 文本指标 | 已实现 |
| 运行时 | `GET` | `/api/report/daily` | 生成当日基金/ETF 量化日报 | 已实现 |
| 运行时 | `GET` | `/api/report/fund-detail` | 生成单基金分析详情 | 已实现 |
| 运行时 | `GET` | `/api/report/export` | 导出日报 Markdown/HTML/PDF | 已实现 |

## 3. 契约接口

### 3.1 `GET /v1/data/realtime/{symbol}`

用途：获取统一实时行情或净值数据，返回 `NormalizedEnvelope`。

参数：

| 参数 | 位置 | 必填 | 说明 |
|---|---|---|---|
| `symbol` | path | 是 | 基金/ETF 代码，例如 `014943`、`159870` |

返回结构示例：

```json
{
  "metric": "realtime",
  "symbol": "014943",
  "source": "eastmoney",
  "source_time": "2026-03-07T09:35:00+08:00",
  "ingest_time": "2026-03-07T01:35:02+00:00",
  "quality_score": 0.98,
  "stale": false,
  "records": [
    {
      "symbol": "014943",
      "name": "示例基金",
      "unit_nav": 1.0231,
      "daily_change_pct": 0.42
    }
  ],
  "metadata": {
    "cache_hit": false,
    "cache_ttl_seconds": 30
  }
}
```

### 3.2 `GET /v1/data/history/{symbol}`

用途：获取统一历史净值/价格序列。

参数：

| 参数 | 位置 | 必填 | 说明 |
|---|---|---|---|
| `symbol` | path | 是 | 基金/ETF 代码 |
| `limit` | query | 否 | 返回条数，默认 `30` |

返回结构示例：

```json
{
  "metric": "history",
  "symbol": "014943",
  "source": "akshare",
  "source_time": "2026-03-07T00:00:00+08:00",
  "ingest_time": "2026-03-07T01:40:00+00:00",
  "quality_score": 0.95,
  "stale": false,
  "records": [
    {
      "date": "2026-03-06",
      "unit_nav": 1.0228,
      "acc_nav": 1.1452,
      "daily_change_pct": 0.31
    }
  ],
  "metadata": {
    "cache_hit": true
  }
}
```

### 3.3 `GET /v1/data/news`

用途：获取统一新闻数据，可按基金/ETF 代码过滤。

参数：

| 参数 | 位置 | 必填 | 说明 |
|---|---|---|---|
| `symbol` | query | 否 | 过滤特定基金/ETF 相关新闻 |
| `limit` | query | 否 | 返回条数，默认 `20` |

返回结构示例：

```json
{
  "metric": "news",
  "symbol": "014943",
  "source": "eastmoney",
  "source_time": "2026-03-07T09:30:00+08:00",
  "ingest_time": "2026-03-07T01:41:22+00:00",
  "quality_score": 0.87,
  "stale": false,
  "records": [
    {
      "title": "示例基金相关新闻",
      "content": "摘要内容",
      "time": "2026-03-07T09:20:00+08:00",
      "source": "eastmoney",
      "url": "https://example.com/news/1"
    }
  ],
  "metadata": {
    "symbol_news_fallback": false
  }
}
```

### 3.4 `GET /v1/data/flow`

用途：获取基金资金流或板块资金流。

参数：

| 参数 | 位置 | 必填 | 说明 |
|---|---|---|---|
| `symbol` | query | 否 | 不传时一般表示板块/市场视角 |

返回结构示例：

```json
{
  "metric": "flow",
  "symbol": "159870",
  "source": "eastmoney",
  "source_time": "2026-03-07T09:30:00+08:00",
  "ingest_time": "2026-03-07T01:42:00+00:00",
  "quality_score": 0.93,
  "stale": false,
  "records": [
    {
      "sector": "人工智能",
      "main_net_inflow": 18200000.0,
      "main_inflow_ratio": 0.81,
      "top_stock": "159870"
    }
  ],
  "metadata": {}
}
```

### 3.5 `GET /v1/sources/health`

用途：获取统一数据源健康状态。

参数：无。

返回结构示例：

```json
[
  {
    "source": "eastmoney",
    "priority": 1,
    "enabled": true,
    "success_count": 12,
    "failure_count": 1,
    "consecutive_failures": 0,
    "last_error": null,
    "last_success_time": "2026-03-07T01:43:00+00:00",
    "last_failure_time": null,
    "circuit_open_until": null,
    "avg_latency_ms": 238.7
  }
]
```

## 4. 运行时接口

### 4.1 `GET /health`

用途：服务存活检查。

参数：无。

返回结构示例：

```json
{
  "status": "ok",
  "service": "report_api"
}
```

### 4.2 `GET /api/monitor/data-sources`

用途：返回全链路数据源状态、整体健康判断和告警列表。该接口可直接用于报表页展示“数据源状态”模块。

参数：无。

返回结构示例：

```json
{
  "captured_at_utc": "2026-03-07T01:44:10.000000+00:00",
  "overall_status": "warning",
  "source_count": 2,
  "sources": [
    {
      "source": "eastmoney",
      "priority": 1,
      "enabled": true,
      "success_count": 12,
      "failure_count": 3,
      "consecutive_failures": 2,
      "last_error": "timeout",
      "last_success_time": "2026-03-07T01:40:00+00:00",
      "last_failure_time": "2026-03-07T01:42:00+00:00",
      "circuit_open_until": "2026-03-07T01:45:00+00:00",
      "avg_latency_ms": 3200.0,
      "cache_metrics": {
        "hit_count": 10,
        "miss_count": 4
      }
    }
  ],
  "alerts": [
    {
      "level": "warning",
      "source": "eastmoney",
      "message": "consecutive failures warning: 2",
      "metric": "all",
      "triggered_at_utc": "2026-03-07T01:44:10.000000+00:00"
    }
  ]
}
```

### 4.3 `GET /metrics`

用途：输出 Prometheus 采集文本。

参数：无。

返回结构示例：

```text
# HELP fund_data_source_enabled Source enabled flag (1 enabled, 0 disabled)
# TYPE fund_data_source_enabled gauge
fund_data_source_enabled{source="eastmoney"} 1
fund_data_source_failure_count{source="eastmoney"} 3
fund_data_source_consecutive_failures{source="eastmoney"} 2
fund_data_source_avg_latency_ms{source="eastmoney"} 3200.0
fund_data_source_alert_total{level="critical"} 0
fund_data_source_alert_total{level="warning"} 1
```

### 4.4 `GET /api/report/daily`

用途：同步生成日报对象，返回市场摘要、榜单、板块排行、基金详情、证据链和风险提示。

参数：

| 参数 | 位置 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `symbols` | query | 否 | `014943,159870` | 逗号分隔的基金/ETF 代码 |
| `market_state` | query | 否 | `neutral` | 权重模板，当前支持 `neutral`、`bull`、`bear` |

返回结构示例：

```json
{
  "report_id": "rpt-20260307-094500",
  "report_date": "2026-03-07",
  "generated_at_utc": "2026-03-07T01:45:00+00:00",
  "market_summary": {
    "symbol_count": 2,
    "avg_score": 62.0,
    "bullish_ratio": 1.0,
    "low_confidence_ratio": 0.0
  },
  "tactical_brief": [
    "014943 -> 持有: 结构中性偏多，继续跟踪"
  ],
  "ranking": [
    {
      "symbol": "014943",
      "name": "name-014943",
      "tier": "A",
      "total_score": 66.0,
      "confidence": 0.77,
      "tactical_action": "持有",
      "tactical_reason": "结构中性偏多，继续跟踪",
      "risk_tags": [
        "FLOW_PROXY_SYMBOL"
      ]
    }
  ],
  "sector_ranking": [
    {
      "sector": "化工",
      "change_pct": 1.2,
      "main_net_inflow": 10000.0,
      "main_inflow_ratio": 0.8,
      "top_stock": "159870"
    }
  ],
  "fund_details": [
    {
      "symbol": "014943",
      "name": "name-014943",
      "scorecard": {
        "total_score": 66.0,
        "confidence": 0.77,
        "factor_scores": {}
      },
      "news_summary": {
        "symbol": "014943",
        "rows": 1,
        "avg_sentiment": 0.6
      },
      "backtest_summary": {
        "snapshot_hash": "hash-014943",
        "ranking": [
          {
            "strategy": "score_threshold",
            "total_return_pct": 1.2,
            "max_drawdown_pct": -1.1,
            "sharpe": 0.8
          }
        ]
      },
      "data_source_refs": [
        "news_pipeline:feature_summary"
      ],
      "source_time_utc": "2026-03-06T00:00:00+00:00"
    }
  ],
  "risk_alerts": [
    "014943: FLOW_PROXY_SYMBOL"
  ],
  "evidence": {
    "generated_by": "DailyReportService",
    "symbols": [
      "014943",
      "159870"
    ],
    "market_state": "neutral"
  }
}
```

### 4.5 `GET /api/report/fund-detail`

用途：返回单基金详情，底层复用日报生成逻辑，只抽取目标基金的 `detail`。

参数：

| 参数 | 位置 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `symbol` | query | 否 | `014943` | 基金代码 |

返回结构示例：

```json
{
  "symbol": "014943",
  "report_id": "rpt-20260307-094500",
  "detail": {
    "symbol": "014943",
    "name": "name-014943",
    "scorecard": {
      "total_score": 66.0,
      "confidence": 0.77
    },
    "news_summary": {
      "symbol": "014943",
      "rows": 1
    },
    "backtest_summary": {
      "snapshot_hash": "hash-014943"
    },
    "data_source_refs": [
      "news_pipeline:feature_summary"
    ],
    "source_time_utc": "2026-03-06T00:00:00+00:00"
  }
}
```

### 4.6 `GET /api/report/export`

用途：导出当前生成日报，支持 `md`、`html`、`pdf`。

参数：

| 参数 | 位置 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `symbols` | query | 否 | `014943,159870` | 逗号分隔代码 |
| `market_state` | query | 否 | `neutral` | 报告权重模板 |
| `format` | query | 否 | `md` | 导出格式：`md` / `html` / `pdf` |

返回结构示例：

```text
HTTP/1.1 200 OK
Content-Type: text/markdown; charset=utf-8
Content-Disposition: attachment; filename=rpt-20260307-094500.md
```

## 5. 运行方式

### 5.1 本机启动

```bash
python apps/api/report_api.py
```

默认监听地址：

- `http://0.0.0.0:8010`
- 本机访问一般使用 `http://127.0.0.1:8010`

### 5.2 手工验证示例

```bash
curl "http://127.0.0.1:8010/health"
curl "http://127.0.0.1:8010/api/monitor/data-sources"
curl "http://127.0.0.1:8010/api/report/daily?symbols=014943,159870&market_state=neutral"
curl -OJ "http://127.0.0.1:8010/api/report/export?symbols=014943,159870&format=md"
```

PowerShell 示例：

```powershell
Invoke-WebRequest "http://127.0.0.1:8010/health"
Invoke-WebRequest "http://127.0.0.1:8010/api/report/daily?symbols=014943,159870&market_state=neutral"
```

## 6. 验证方式

推荐最小验证顺序：

1. 启动运行时 API：`python apps/api/report_api.py`
2. 执行运行时 smoke test：`python scripts/check_api_runtime.py`
3. 执行报表模块校验：`python scripts/check_p6_reporting.py`
4. 如需验证权重热更新基础能力：`python scripts/check_p3_factor_engine.py`

## 7. 当前限制

1. `docs/api/openapi.yaml` 与 `apps/api/report_api.py` 尚未统一，报表类接口没有进入 OpenAPI 契约。
2. 当前没有登录、权限、会话控制，`/metrics`、`/api/report/*`、`/api/monitor/*` 都是匿名可访问。
3. 运行时接口为同步计算；日报生成、导出与监控接口都没有任务队列、缓存键管理或异步轮询机制。
4. `/api/report/daily` 与 `/api/report/fund-detail` 使用了内置默认值，并且写死了 `014943 -> 159870` 的代理映射。
5. 当前没有“模型配置中心”相关接口，也没有 Gemini/OpenAI/自定义兼容模型的配置存储与校验能力。
6. 前端原型页仅覆盖日报与单基金页面，尚未接入登录、配置中心、报表导出状态、错误边界与全局导航。
7. PDF 导出为轻量文本实现，适合作为占位能力，不适合复杂版式或高保真报告。
