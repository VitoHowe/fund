# P1 数据接入层验收记录（2026-03-05）

- 任务：`b10a778b-cbaa-4a96-a03e-4193b1508040`
- 目标：实现多源适配、熔断、自动切换、统一 schema 与 source health 查询
- 验收脚本：`python scripts/check_p1_data_hub.py`

## 1. 代码交付

已实现以下文件：

- `services/data_hub/adapters/base.py`
- `services/data_hub/adapters/eastmoney_adapter.py`
- `services/data_hub/adapters/efinance_adapter.py`
- `services/data_hub/adapters/akshare_adapter.py`
- `services/data_hub/adapters/tdx_adapter.py`
- `services/data_hub/adapters/yfinance_adapter.py`
- `services/data_hub/adapters/alpha_vantage_adapter.py`
- `services/data_hub/source_manager.py`
- `services/data_hub/types.py`
- `services/data_hub/exceptions.py`
- `scripts/check_p1_data_hub.py`

## 2. 功能验收结果（014943）

### 2.1 统一 schema
- `fetch_realtime('014943')`：成功，来源 `eastmoney`
- `fetch_history('014943', limit=5)`：成功，来源 `eastmoney`
- `fetch_news(symbol='014943')`：成功（自动降级到市场新闻），来源 `akshare`

所有返回均含：`metric/symbol/source/source_time/records/quality_score/stale/ingest_time/metadata`。

### 2.2 自动切源（故障转移）
- 人工注入故障：强制 `eastmoney.fetch_history` 抛错
- 实际结果：`history` 自动切换到 `efinance`，返回 3 条历史净值
- 审计日志：记录了 `source_switch` 事件（metric、symbol、失败源、选中源、原因）

### 2.3 source_health 与熔断状态
- 可查询每个 source 的 `success_count/failure_count/consecutive_failures/circuit_open_until/avg_latency_ms`
- 熔断粒度已改为 `source + metric`，避免新闻链路故障影响历史链路可用性

## 3. 已知限制

- `tdx` 适配器当前为占位实现（接口定义已完成，等待后续对接）
- `alpha_vantage` 依赖 `ALPHA_VANTAGE_API_KEY`，未配置时仅返回可控失败
- `yfinance` 新闻链路有速率限制（会触发限流），已由 SourceManager 自动降级处理
- `eastmoney` 快讯在个别时段可能空结果，已实现自动回退到其他新闻源

## 4. 结论

P1 的核心验收项已满足：

1. 任一数据源故障可自动切换到次优源。
2. 单次请求返回统一 schema。
3. `source_health` 可查询且包含失败计数、熔断状态、恢复时间。
