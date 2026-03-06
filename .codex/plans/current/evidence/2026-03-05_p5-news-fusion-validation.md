# P5 新闻与国际动态融合链路验收记录（2026-03-05）

- 任务：`4f6bab26-2e03-4bd9-b970-277914f05cda`
- 目标：接入新闻源，完成清洗去重、实体关联、情绪打分，并将情绪特征写入因子输入
- 验收脚本：`python scripts/check_p5_news_pipeline.py`

## 1. 代码交付

已实现/更新以下文件：

- `services/news_pipeline/schema.py`
- `services/news_pipeline/sentiment.py`
- `services/news_pipeline/fetchers/eastmoney_news_fetcher.py`
- `services/news_pipeline/fetchers/tavily_news_fetcher.py`
- `services/news_pipeline/fetchers/__init__.py`
- `services/news_pipeline/processor.py`
- `services/news_pipeline/service.py`
- `services/news_pipeline/__init__.py`
- `services/factor_engine/scoring.py`
- `services/factor_engine/factors/sentiment_factor.py`
- `scripts/check_p5_news_pipeline.py`
- `tests/test_news_pipeline.py`
- `README.md`

## 2. 功能验收结果（014943）

### 2.1 新闻拉取与解析
- 当前环境下 `eastmoney` 直连快讯返回空列表（非异常）
- 验收脚本自动回退到 `SourceManager.fetch_news(symbol=None)`（实际来源为 `akshare`）
- 结果：`news_fetch_and_parse_stable=true`（可稳定拿到并解析新闻）

### 2.2 去重与时效窗
- 默认时效窗：`72h`
- 验收注入重复新闻后，去重生效：`dedup_effective=true`
- 管线结果保留最新重复项并移除重复指纹

### 2.3 实体关联与单基金查询
- 已实现基金/ETF 与板块关键词映射（含 `014943`、`159870` 默认别名）
- 单基金关联查询可用：`symbol_news_query_available=true`
- 单基金情绪摘要可用：`symbol_sentiment_available=true`

### 2.4 情绪特征写入因子输入
- `FactorScorer.score_symbol` 新增 `extra_context`
- `SentimentFactor` 优先消费 `extra_context.news_feature`
- 验证结果：`sentiment_written_to_factor_input=true`
- `sentiment.source_refs=['news_pipeline:feature_summary']`

## 3. 测试与验证

- `python -m unittest tests/test_news_pipeline.py tests/test_factor_engine.py tests/test_backtest_runner.py`：`OK`
- `python scripts/check_p5_news_pipeline.py`：`PASSED`

关键检查项：

1. `news_fetch_and_parse_stable=true`
2. `dedup_effective=true`
3. `symbol_news_query_available=true`
4. `symbol_sentiment_available=true`
5. `sentiment_written_to_factor_input=true`

## 4. 已知限制

1. 直连 `eastmoney` 快讯在当前网络环境下可能为空，需要依赖回退源兜底。
2. Tavily 通道需配置 `TAVILY_API_KEY` 才会启用。
3. 当前情绪模型为规则词典法，后续可替换为更强语义模型。

## 5. 结论

P5 核心验收项已满足：

1. 新闻融合链路可稳定拉取并解析（含回退机制）。
2. 去重、实体关联、情绪打分能力已落地。
3. 单基金（014943）可查询关联新闻与情绪摘要。
4. 情绪特征已成功注入因子输入并体现在评分输出。
