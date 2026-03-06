# fund-intel

中国基金/ETF 智能分析平台（进行中）。

当前已完成：
- P0 文档基线（PRD、领域模型、OpenAPI 契约）
- P1 数据接入层骨架（多源适配、熔断、健康状态、审计日志）
- P2 数据标准化、缓存与时序存储（统一 schema + UTC + SQLite）
- P3 因子引擎与评分框架（6 类因子、权重模板、可解释 ScoreCard）
- P4 策略信号与回测模块（双策略、成本/滑点、KPI 报告、可复现）
- P5 新闻与国际动态融合链路（清洗去重、实体关联、情绪特征注入）
- P6 报告系统与可视化工作台（日/收盘报告、榜单、API、导出、页面）
- P7 稳定性与治理（数据源监控、Prometheus 指标、故障转移集成测试、回归基线、License 矩阵）
- 运行时独立性约束（不依赖 MCP 进行数据获取）

API 总结与前端规划：
- [API 总结](docs/api/API_SUMMARY.zh-CN.md)
- [前端规划](docs/plan/frontend-plan.zh-CN.md)
- [管理台说明](docs/product/admin-console.zh-CN.md)

管理台页面：

- `/login`：密码登录页
- `/dashboard/today`：今日量化报告、一键生成、数据链路状态
- `/fund/:symbol`：单基金量化报告页
- `/settings/models`：模型配置中心（统一字段 `url / apiKey / model`）
- `/settings/strategy`：策略配置中心（参数、权重、启停、版本、回滚、热更新、离线调优）

安装依赖：

```bash
python -m pip install -e .
```

快速验证：

```bash
python scripts/check_runtime_independence.py
python scripts/check_p1_data_hub.py
python scripts/check_p2_storage.py
python scripts/check_p3_factor_engine.py
python scripts/check_p4_backtest.py
python scripts/check_p5_news_pipeline.py
python scripts/check_p6_reporting.py
python scripts/check_p7_governance.py
python scripts/check_api_runtime.py
```

管理台默认开发密码与部署环境：

- 默认开发密码：`fund-admin`
- 生产环境应通过 `FUND_ADMIN_PASSWORD` 或 `FUND_ADMIN_PASSWORD_HASH` 覆盖默认值
- `FUND_ADMIN_PASSWORD_HASH` 采用 `sha256` 十六进制字符串

配置文件：

- `config/model_providers.json`：模型配置、默认模型、热更新版本
- `config/strategy_profiles.json`：策略配置、版本历史、默认策略、离线调优写回结果

Docker 基线验证：

```bash
docker build -t fund-intel:dev .
docker run --rm fund-intel:dev
```

本机启动 API：

```bash
python apps/api/report_api.py
```

本机访问：

- API：`http://127.0.0.1:8010`
- 管理台：`http://127.0.0.1:8010/login`
