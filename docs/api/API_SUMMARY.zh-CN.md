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
| 运行时 | `POST` | `/api/auth/login` | 密码登录并写入会话 Cookie | 已实现 |
| 运行时 | `POST` | `/api/auth/logout` | 注销当前会话 | 已实现 |
| 运行时 | `GET` | `/api/auth/session` | 获取当前登录态与配置版本 | 已实现 |
| 运行时 | `GET` | `/api/monitor/data-sources` | 获取全链路数据源状态与告警 | 已实现 |
| 运行时 | `GET` | `/api/monitor/audit-events` | 获取最近数据源切换与告警审计事件 | 已实现 |
| 运行时 | `GET` | `/metrics` | 导出 Prometheus 文本指标 | 已实现 |
| 运行时 | `GET` | `/api/report/daily` | 生成当日基金/ETF 量化日报 | 已实现 |
| 运行时 | `POST` | `/api/report/daily/generate` | 显式生成今日报告 | 已实现 |
| 运行时 | `GET` | `/api/report/daily/latest` | 读取最近一次已生成的今日报告 | 已实现 |
| 运行时 | `GET` | `/api/report/fund-detail` | 生成单基金分析详情 | 已实现 |
| 运行时 | `GET` | `/api/report/export` | 导出日报 Markdown/HTML/PDF | 已实现 |
| 运行时 | `GET` | `/api/settings/models` | 查询模型配置列表（脱敏） | 已实现 |
| 运行时 | `POST` | `/api/settings/models` | 新增模型配置 | 已实现 |
| 运行时 | `PUT` | `/api/settings/models/{provider_id}` | 更新模型配置 | 已实现 |
| 运行时 | `POST` | `/api/settings/models/{provider_id}/default` | 设置默认模型 | 已实现 |
| 运行时 | `POST` | `/api/settings/models/{provider_id}/enabled` | 启停模型配置 | 已实现 |
| 运行时 | `POST` | `/api/settings/models/{provider_id}/test` | 测试连通性/鉴权/模型可用性 | 已实现 |
| 运行时 | `POST` / `GET` | `/api/settings/models/reload` | 触发或确认模型配置热更新 | 已实现 |
| 运行时 | `GET` | `/api/settings/strategies` | 查询策略配置列表 | 已实现 |
| 运行时 | `POST` | `/api/settings/strategies` | 新增策略配置 | 已实现 |
| 运行时 | `PUT` | `/api/settings/strategies/{strategy_id}` | 更新策略配置 | 已实现 |
| 运行时 | `POST` | `/api/settings/strategies/{strategy_id}/default` | 设置默认策略 | 已实现 |
| 运行时 | `POST` | `/api/settings/strategies/{strategy_id}/enabled` | 启停策略 | 已实现 |
| 运行时 | `POST` | `/api/settings/strategies/{strategy_id}/rollback` | 按历史版本回滚策略 | 已实现 |
| 运行时 | `POST` | `/api/settings/strategies/{strategy_id}/replay-tune` | 离线回放并写回推荐参数 | 已实现 |
| 运行时 | `POST` / `GET` | `/api/settings/strategies/reload` | 触发或确认策略热更新 | 已实现 |
| 运行时 | `GET` | `/api/settings/runtime` | 读取模型/策略配置版本摘要 | 已实现 |

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

用途：返回全链路数据源状态、整体健康判断、告警列表和最近审计事件。该接口可直接用于报表页展示“数据源状态”模块。

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
  ],
  "recent_audit_events": [
    {
      "time": "2026-03-07T01:44:08.000000+00:00",
      "metric": "news",
      "symbol": null,
      "selected_source": "akshare",
      "failed_sources": [
        "eastmoney",
        "efinance"
      ],
      "reason": "fallback activated"
    }
  ],
  "audit_event_count": 1
}
```

### 4.2.1 `GET /api/monitor/audit-events`

用途：返回最近数据源切换与告警事件，便于管理台审计与问题追踪。

返回结构示例：

```json
{
  "events": [
    {
      "time": "2026-03-07T01:44:08.000000+00:00",
      "metric": "news",
      "symbol": null,
      "selected_source": "akshare",
      "failed_sources": [
        "eastmoney",
        "efinance"
      ],
      "reason": "fallback activated"
    }
  ],
  "captured_at_utc": "2026-03-07T01:44:10.000000+00:00"
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

### 4.4.1 `POST /api/report/daily/generate`

用途：显式触发今日报告生成。当前仍为同步实现，但语义上已与“读取最近报告”分离。

请求体示例：

```json
{
  "symbols": "014943,159870",
  "market_state": "neutral"
}
```

返回结构：与 `GET /api/report/daily` 一致。

### 4.4.2 `GET /api/report/daily/latest`

用途：返回最近一次成功生成并缓存到文件的日报对象。

说明：

1. 如果当前没有缓存文件，接口会按默认参数生成一次并返回。
2. 缓存文件位于 `data/reports/`。

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

### 4.7 `POST /api/auth/login`

用途：密码登录并写入会话 Cookie。

请求体示例：

```json
{
  "password": "fund-admin"
}
```

返回结构示例：

```json
{
  "ok": true,
  "authenticated": true,
  "session": {
    "username": "admin",
    "created_at": "2026-03-07T01:50:00+00:00",
    "expires_at": "2026-03-07T13:50:00Z"
  }
}
```

### 4.8 `POST /api/auth/logout`

用途：清除当前会话。

### 4.9 `GET /api/auth/session`

用途：返回当前登录态以及模型/策略配置版本摘要。

### 4.10 `GET /api/settings/models`

用途：返回模型配置列表。核心统一字段为 `url` / `apiKey` / `model`，其中 `apiKey` 返回时已脱敏。

### 4.11 `POST /api/settings/models`

用途：新增模型配置。

请求体示例：

```json
{
  "id": "mock-openai",
  "name": "Mock OpenAI",
  "url": "http://127.0.0.1:8021/v1",
  "apiKey": "test-key",
  "model": "mock-model",
  "enabled": true,
  "is_default": true
}
```

### 4.12 `PUT /api/settings/models/{provider_id}`

用途：更新模型配置。更新时 `apiKey` 可留空以保留旧值。

### 4.13 `POST /api/settings/models/{provider_id}/default`

用途：设定默认模型配置。

### 4.14 `POST /api/settings/models/{provider_id}/enabled`

用途：切换启停状态。

### 4.15 `POST /api/settings/models/{provider_id}/test`

用途：执行模型连接测试，返回三段结果：

1. `connectivity`
2. `auth`
3. `model`

该接口同时适配 Gemini、OpenAI 与 OpenAI compatible 网关。

### 4.16 `GET/POST /api/settings/models/reload`

用途：重新载入模型配置文件并返回当前版本摘要。

### 4.17 `GET /api/settings/strategies`

用途：返回策略配置列表，包括：

- `strategy_type`
- `params`
- `weight`
- `enabled`
- `is_default`
- `profile_version`
- `history`

### 4.18 `POST /api/settings/strategies`

用途：新增策略配置。

### 4.19 `PUT /api/settings/strategies/{strategy_id}`

用途：更新策略参数或权重。

### 4.20 `POST /api/settings/strategies/{strategy_id}/default`

用途：设置默认策略。

### 4.21 `POST /api/settings/strategies/{strategy_id}/enabled`

用途：切换策略启停状态。

### 4.22 `POST /api/settings/strategies/{strategy_id}/rollback`

用途：按历史 `profile_version` 回滚到旧版本，并生成新的当前版本。

### 4.23 `POST /api/settings/strategies/{strategy_id}/replay-tune`

用途：基于现有历史量化数据做离线回放和参数调优，并可把推荐参数直接写回新版本。

请求体示例：

```json
{
  "symbols": "014943",
  "market_state": "neutral",
  "limit": 60,
  "persist": true
}
```

### 4.24 `GET/POST /api/settings/strategies/reload`

用途：强制重载策略配置文件。

### 4.25 `GET /api/settings/runtime`

用途：读取模型与策略配置的版本摘要，供管理台显示当前运行时生效状态。

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

### 5.3 管理台页面

当前服务直接分发管理台页面：

- `http://127.0.0.1:8010/login`
- `http://127.0.0.1:8010/dashboard/today`
- `http://127.0.0.1:8010/fund/014943`
- `http://127.0.0.1:8010/settings/models`
- `http://127.0.0.1:8010/settings/strategy`

## 6. 验证方式

推荐最小验证顺序：

1. 安装依赖：`python -m pip install -e .`
2. 启动运行时 API：`python apps/api/report_api.py`
3. 执行运行时 smoke test：`python scripts/check_api_runtime.py`
4. 执行报表模块校验：`python scripts/check_p6_reporting.py`
5. 如需验证权重热更新基础能力：`python scripts/check_p3_factor_engine.py`

## 7. 当前限制

1. `docs/api/openapi.yaml` 与 `apps/api/report_api.py` 尚未统一，报表类接口没有进入 OpenAPI 契约。
2. 当前认证为最小可用方案，默认开发密码是 `fund-admin`；生产环境必须覆盖。
3. 运行时接口仍以同步计算为主；离线调优也是同步接口，重负载场景后续应演进为异步任务。
4. `/api/report/daily` 与 `/api/report/fund-detail` 仍使用内置默认值，并且保留了 `014943 -> 159870` 的代理映射。
5. 模型连接测试当前通过 provider endpoint 适配实现，适合 MVP 与网关联调，不是完整 SLA 探针系统。
6. 管理台为服务端直出静态资源方案，优点是部署简单，缺点是前端工程化能力有限。
7. PDF 导出为轻量文本实现，适合作为占位能力，不适合复杂版式或高保真报告。
