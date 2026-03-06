# P4 策略信号与回测模块验收记录（2026-03-05）

- 任务：`83b0af56-58db-4654-86bc-10ab90c3167d`
- 目标：基于因子评分生成信号，支持参数化回测与 KPI 报告，并保证同输入可复现
- 验收脚本：`python scripts/check_p4_backtest.py`

## 1. 代码交付

已实现/更新以下文件：

- `services/strategy/base_strategy.py`
- `services/strategy/rules/score_threshold_strategy.py`
- `services/strategy/rules/score_momentum_strategy.py`
- `services/strategy/rules/__init__.py`
- `services/strategy/__init__.py`
- `services/backtest/metrics.py`
- `services/backtest/runner.py`
- `services/backtest/__init__.py`
- `scripts/check_p4_backtest.py`
- `tests/test_backtest_runner.py`
- `docs/research/backtest-methodology.md`
- `README.md`

## 2. 功能验收结果（014943）

### 2.1 双策略回测可运行
- 策略 1：`score_threshold`
- 策略 2：`score_momentum`
- 结果：`two_strategies_backtest=true`

### 2.2 KPI 指标完整
- 输出指标：
  - `total_return_pct`
  - `annualized_return_pct`
  - `max_drawdown_pct`
  - `win_rate`
  - `sharpe`
  - `turnover_ratio`
  - `trade_count`
- 结果：`required_kpi_present=true`

### 2.3 可复现性
- 机制：使用固定历史快照并生成 `snapshot_hash`
- 同参数重复运行结果：一致
- 结果：`reproducible_same_input=true`
- 本次样本：`snapshot_hash=c84fb3ae542ef562`

### 2.4 无未来函数口径
- 信号在 `t` 日收盘后生成，仅使用 `t` 及以前数据
- 仓位在 `t -> t+1` 收益区间生效
- 交易成本在调仓当日扣减：
  - `trade_cost = equity * |Δposition| * (fee_rate + slippage_bps/10000)`

## 3. 测试与验证

- `python -m unittest tests/test_backtest_runner.py`：`OK (2 tests)`
- `python scripts/check_p4_backtest.py`：`PASSED`

## 4. 已知限制

1. 当前 `014943` 历史样本较短（约 20 条），回测自动降档 warmup（`effective_warmup_days=17`）。
2. 场外基金资金语义通过代理 ETF（`159870`）补充，结果附带代理语义风险。 
3. 当前模型未纳入申赎费、冲击成本与容量约束。

## 5. 结论

P4 核心验收项已满足：

1. 至少 2 套策略可运行回测。
2. KPI 指标齐全并可产出策略对比。
3. 相同输入可复现相同结果（快照哈希一致、指标一致）。
4. 回测方法论已文档化，执行口径可追溯。
