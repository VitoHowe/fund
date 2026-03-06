# P3 因子引擎与评分框架验收记录（2026-03-05）

- 任务：`dc9d5e8d-a635-440c-8958-138fc98422bd`
- 目标：实现趋势、动量、波动、回撤、量价/资金、情绪等因子，并输出可解释 ScoreCard
- 验收脚本：`python scripts/check_p3_factor_engine.py`

## 1. 代码交付

已实现/更新以下文件：

- `services/factor_engine/base_factor.py`
- `services/factor_engine/factors/common.py`
- `services/factor_engine/factors/trend_factor.py`
- `services/factor_engine/factors/momentum_factor.py`
- `services/factor_engine/factors/volatility_factor.py`
- `services/factor_engine/factors/drawdown_factor.py`
- `services/factor_engine/factors/flow_factor.py`
- `services/factor_engine/factors/sentiment_factor.py`
- `services/factor_engine/factors/__init__.py`
- `services/factor_engine/scoring.py`
- `services/factor_engine/__init__.py`
- `config/factor_weights.yaml`
- `scripts/check_p3_factor_engine.py`
- `tests/test_factor_engine.py`
- `README.md`

## 2. 功能验收结果（014943）

### 2.1 因子覆盖与可解释输出
- 结果：`factor_count_ge_6=true`
- 实际因子：`trend/momentum/volatility/drawdown/flow/sentiment`
- 每个因子均输出：`score + confidence + explanation + risk_tags + raw + source_refs`
- 结论：满足“至少 6 类因子、可单项解释”要求

### 2.2 模板化权重切换
- 场景：同一标的使用 `neutral` 与 `bull` 模板打分
- 结果：`weight_template_switch_effective=true`
- 样本：
  - `neutral.total_score=55.5427`
  - `bull.total_score=52.7025`
- 结论：市场状态模板可切换且对结果有真实影响

### 2.3 权重热更新与版本追溯
- 场景：临时修改权重文件后强制 reload
- 结果：`weight_hot_reload_traceable=true`
- 机制：`weight_version = version + 配置内容 hash`
- 结论：权重变更可追溯到版本标识，满足审计要求

### 2.4 014943 资金语义处理
- 约束：`014943` 为场外基金，不直接具备盘口资金流语义
- 处理：`flow` 因子支持 `proxy_symbol`，本次采用 `159870`
- 风险标签：`FLOW_PROXY_SYMBOL`
- 结论：符合“OF 走净值、交易语义走关联 ETF”规则

## 3. 测试与验证

- `python -m unittest tests/test_factor_engine.py`：`OK (2 tests)`
- `python scripts/check_p3_factor_engine.py`：`PASSED`

关键检查项：

1. `factor_count_ge_6=true`
2. `all_factor_explainable=true`
3. `weight_template_switch_effective=true`
4. `weight_hot_reload_traceable=true`

## 4. 已知限制

- 情绪因子当前为关键词法，尚未接入更强语义模型
- 资金因子在 OF 场景依赖代理 ETF，后续需补“基金-ETF 映射字典服务”
- 评分结果依赖上游数据质量，若新闻或资金链路降级会触发风险标签

## 5. 结论

P3 任务核心验收项已满足：

1. 至少 6 类因子已落地，支持独立测试。
2. 单基金输出包含分项解释、风险标签和证据来源。
3. 权重配置外置，支持按市场状态切换模板。
4. 权重热更新后的评分版本可追溯。
