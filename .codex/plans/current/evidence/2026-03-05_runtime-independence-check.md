# 运行时独立性验收（2026-03-05）

## 1. 目标

确认项目运行时数据源获取不依赖 MCP，会在 Docker 中独立运行。

## 2. 检查项与结果

### 2.1 代码扫描
- 扫描范围：`services/`、`scripts/`、`docs/`、`README.md`
- 关键字：`mcp`、`stock-data-mcp`、`mcp__`、`list_tasks`、`execute_task`、`verify_task`
- 结果：`NO_MATCH`

### 2.2 自动化独立性检查脚本
- 脚本：`python scripts/check_runtime_independence.py`
- 输出：
  - `RUNTIME_INDEPENDENCE_CHECK=PASSED`
  - `Runtime data source layer is independent from MCP.`

### 2.3 运行时数据链路验证
- 脚本：`python scripts/check_p1_data_hub.py`
- 关键结果：
  - `realtime(014943)`：成功，来源 `eastmoney`
  - `history(014943)`：成功，来源 `eastmoney`
  - `fallback_history`：注入故障后自动切换到 `efinance`
  - `news(014943)`：成功，来源 `akshare`（通过 SourceManager 降级策略）

## 3. Docker 部署准备

已新增：
- `Dockerfile`
- `.dockerignore`

容器默认命令：
- `python scripts/check_runtime_independence.py && python scripts/check_p1_data_hub.py`

## 4. 环境限制

本机当前无法直接执行 Docker 验证（`docker --version` 不可用，命令未安装）。

## 5. 结论

当前代码层面和依赖层面均满足“运行时独立，不依赖 MCP”要求。
