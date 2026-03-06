# P7 稳定性与治理验收记录（2026-03-06）

- 任务：`d760e8c6-2544-46ec-b08e-daca131eaf8c`
- 目标：补齐可观测性、测试与合规治理，确保系统可持续运行并具备商用边界说明
- 验收脚本：`python scripts/check_p7_governance.py`

## 1. 代码交付

已实现/更新以下文件：

- `services/observability/source_monitor.py`
- `services/observability/__init__.py`
- `apps/api/report_api.py`
- `ops/monitoring/data_source_dashboard.json`
- `tests/test_observability.py`
- `tests/integration/test_failover.py`
- `tests/regression/test_factor_scores.py`
- `tests/fixtures/factor_regression_014943.json`
- `scripts/check_p7_governance.py`
- `docs/compliance/license-matrix.md`
- `THIRD_PARTY_NOTICES.md`
- `README.md`

## 2. 功能验收结果

### 2.1 可观测性与告警

- 新增 `SourceMonitor`，可输出数据源实时健康快照、告警列表和总体状态。
- API 已暴露：
  - `GET /api/monitor/data-sources`（JSON 状态）
  - `GET /metrics`（Prometheus 文本指标）
- 看板模板已落地：`ops/monitoring/data_source_dashboard.json`。
- 验收结果：`monitor_snapshot_available=true`、`monitor_alert_schema_ok=true`、`prometheus_metrics_available=true`。

### 2.2 测试体系补齐

- 新增单元测试：`tests/test_observability.py`
- 新增集成测试：`tests/integration/test_failover.py`
  - 基于 `014943` 验证主源失败后自动切换到备源，且审计事件可追踪。
- 新增回归测试：`tests/regression/test_factor_scores.py`
  - 使用固定夹具 `factor_regression_014943.json` 与稳定 hash（`4f57efdf2663866d`）约束评分回归漂移。
- 验收结果：`critical_test_suites_passed=true`。

### 2.3 License 与复用边界治理

- 新增 `docs/compliance/license-matrix.md`，覆盖运行时依赖与参考仓库复用边界。
- 新增 `THIRD_PARTY_NOTICES.md`，沉淀第三方组件声明。
- 新增治理脚本 `scripts/check_p7_governance.py`：
  - 自动解析 `pyproject.toml` 运行时依赖
  - 校验 license matrix 覆盖完整性
- 验收结果：`license_matrix_covers_runtime_dependencies=true`，`license_missing_components=[]`。

## 3. 测试与验证

执行命令：

```bash
python -m py_compile services/observability/source_monitor.py apps/api/report_api.py scripts/check_p7_governance.py tests/integration/test_failover.py tests/regression/test_factor_scores.py tests/test_observability.py
python -m unittest tests.test_observability tests.integration.test_failover tests.regression.test_factor_scores
python scripts/check_p7_governance.py
python scripts/check_runtime_independence.py
```

结果：

1. 编译检查通过。
2. 核心测试集通过（`Ran 5 tests ... OK`）。
3. 治理检查输出全部 `true`。
4. 运行时独立性检查通过（`RUNTIME_INDEPENDENCE_CHECK=PASSED`）。

## 4. 已知限制

1. 当前监控为进程内采集，生产环境仍需接入 Alertmanager/告警通道（企业微信/钉钉/短信）。
2. 当前回归基线覆盖 `014943` 主路径，后续应扩展至多市场状态与更多代表性基金/ETF。
3. 当前 license matrix 仅覆盖 Python 运行时依赖；若新增前端依赖需同步扩展校验规则。

## 5. 结论

P7 核心验收项已满足：

1. 数据源状态可实时监控并暴露 Prometheus 指标。
2. 单元/集成/回归关键测试链路已建立并通过。
3. 许可证矩阵覆盖运行时依赖，并明确 GPL/非商用/未知许可的复用边界。
4. 运行时独立性保持不变，满足 Docker 独立部署约束。

## 6. 发布前补充修复（2026-03-06）

在后续“全链路发布验收”中发现并修复两项运行性问题：

1. `python apps/api/report_api.py` 启动时存在 `ModuleNotFoundError: services`。
   - 处理：在 `apps/api/report_api.py` 增加根目录 `sys.path` 注入，确保入口脚本可直接运行。
2. 报告接口在板块资金流全源失败时返回 `500`。
   - 处理：在 `services/reporting/daily_report_service.py` 中将 `fetch_flow` 异常降级为空榜单，并写入 `MARKET: SECTOR_FLOW_UNAVAILABLE` 风险标记和 `evidence.sector_flow_error`。
   - 补充测试：`tests/test_reporting.py::test_sector_flow_failure_is_degraded`。
3. 新增 API 运行时烟囱脚本：`scripts/check_api_runtime.py`，检查 `/health`、`/api/monitor/data-sources`、`/metrics`、`/api/report/daily`。

补充验证命令：

```bash
python -m unittest tests.test_reporting
python scripts/check_api_runtime.py
```

补充验证结果：

1. `report_api` 可直接启动，无需手动设置 `PYTHONPATH`。
2. `daily report` 在 `flow` 失败场景不再 `500`，接口保持 `200`。
3. 运行时 API 烟囱检查全部通过。
