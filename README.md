# fund-intel

中国基金/ETF 智能分析平台（进行中）。

当前已完成：
- P0 文档基线（PRD、领域模型、OpenAPI 契约）
- P1 数据接入层骨架（多源适配、熔断、健康状态、审计日志）
- P2 数据标准化、缓存与时序存储（统一 schema + UTC + SQLite）
- P3 因子引擎与评分框架（6 类因子、权重模板、可解释 ScoreCard）
- P4 策略信号与回测模块（双策略、成本/滑点、KPI 报告、可复现）
- P5 新闻与国际动态融合链路（清洗去重、实体关联、情绪特征注入）
- 运行时独立性约束（不依赖 MCP 进行数据获取）

快速验证：

```bash
python scripts/check_runtime_independence.py
python scripts/check_p1_data_hub.py
python scripts/check_p2_storage.py
python scripts/check_p3_factor_engine.py
python scripts/check_p4_backtest.py
python scripts/check_p5_news_pipeline.py
```

Docker 基线验证：

```bash
docker build -t fund-intel:dev .
docker run --rm fund-intel:dev
```
