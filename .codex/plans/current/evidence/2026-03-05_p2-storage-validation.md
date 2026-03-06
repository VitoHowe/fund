# P2 存储与标准化验收记录（2026-03-05）

- 任务：`ca1788c2-b7ac-471b-812d-01162f65edbb`
- 目标：实现数据标准化（统一 schema + UTC）、实时缓存策略与历史时序存储
- 验收脚本：`python scripts/check_p2_storage.py`

## 1. 代码交付

已实现/更新以下文件：

- `infra/db/schema.sql`
- `services/data_hub/cache_policy.py`
- `services/data_hub/normalizer.py`
- `services/data_hub/repository.py`
- `services/data_hub/source_manager.py`
- `scripts/check_p2_storage.py`
- `scripts/check_p1_data_hub.py`
- `README.md`

## 2. 功能验收结果（014943）

### 2.1 缓存命中与 TTL 策略
- 场景：连续调用 `fetch_realtime('014943')`
- 结果：首次 `cache_hit=false`，二次 `cache_hit=true`
- 结果样本：`hits=1, misses=1, sets=1`
- 结论：实时缓存生效，符合盘中秒级缓存预期

### 2.2 跨源标准化一致性（history）
- 场景：主源 `eastmoney` 与备源 `efinance` 的历史净值结果做 schema 对齐校验
- 结果：两源 `records` 首行字段集合一致
- 关键字段：`date/unit_nav/acc_nav/daily_change_pct/sub_status/red_status/event_time_utc`
- 结论：已解决跨源字段形状不一致问题，可支持统一下游因子处理

### 2.3 时序落库与查询性能
- 场景：查询近 30 天 `history`（symbol=`014943`）
- 结果：`rows=31`，`elapsed_ms=0.4958`，`target_met_lt_500ms=true`
- 结论：时序落库与索引可用，查询性能达成阶段目标

### 2.4 新闻链路回归验证
- 场景：`fetch_news(symbol='014943', limit=10)`
- 结果：成功，来源 `akshare`，返回 `10` 条
- 结论：P2 集成后未破坏 P1 的新闻降级链路

## 3. 回归与独立性检查

- `python scripts/check_runtime_independence.py`：`PASSED`
- `python scripts/check_p1_data_hub.py`：`PASSED`
- `python scripts/check_p2_storage.py`：`PASSED`

说明：运行时数据获取仍为源站直连，不依赖 MCP。

## 4. 已知限制

- 当前缓存为进程内内存缓存，尚未引入容量上限与主动淘汰策略
- 时序存储当前使用 SQLite，后续生产环境建议迁移至 PostgreSQL + TimescaleDB
- `yfinance` 新闻存在限流风险，`alpha_vantage` 需配置 API Key

## 5. 结论

P2 的核心验收项已满足：

1. 数据标准化管线已落地（`validate -> map -> enrich`）。
2. 存储层形成“实时缓存 + 历史时序”双层能力。
3. 基于 `014943` 的可获取性、一致性与性能检查通过。
4. 与 P1 链路兼容，且保持 Docker 运行时独立性约束。
