# fund 外部参考仓库与文档接入建议

更新时间：2026-03-07  
适用范围：`fund` 项目的 `data_hub / news_pipeline / reporting / HKCloud` 部署

## 1. 关键结论

1. `fund` 当前已经具备可运行的数据骨架，但“基金净值 / ETF 盘口与资金流 / 新闻补证 / 外部搜索”仍混在统一 `realtime/history/news/flow` 契约里，下一轮应改成“语义拆分、契约兼容”的重构，而不是继续堆新的适配器。
2. 生产主链路建议固定为：`Eastmoney raw + AkShare`。`Eastmoney` 负责时效与细粒度，`AkShare` 负责广覆盖与基金主数据；两者互为主备，但分工要按资产语义拆开。
3. `efinance` 不适合继续作为默认二号运行时主备。仓库 `LICENSE` 是 MIT，但 README 明确写了“仅供学习交流使用，不得用于商业用途”；如果 `fund` 有 HKCloud 对外部署或商业化风险，应将其降级为“特性开关下的可选备源/验收源”。
4. `stock-data-mcp` 适合继续做研发期架构对照与熔断参考，不应进入生产运行时依赖。它的价值在 `source manager / circuit breaker / status surface`，不在直接替代 `fund` 的运行时数据源。
5. `TDX` 相关参考只值得放在 ETF 盘口和分钟级成交 sidecar，不值得直接拉进开放式基金净值链路。开放式基金 (`OF`) 与场内 ETF 的交易语义必须强制分流。
6. HKCloud 最小可行方案只需要自部署 `fund-api`；只有当你确认需要五档盘口、逐笔成交或更稳的 ETF 分钟级链路时，再加一个 `tdx-api` sidecar。`etf-ark / fund-app / x2rr/funds / go-stock / jcp` 都是参考产品，不是生产依赖。

## 2. 与 fund 当前实现的对齐点

截至本次分析，仓库内已经存在如下基线：

1. `services/data_hub/__init__.py` 当前默认源顺序为 `eastmoney -> efinance -> akshare -> tdx -> yfinance -> alpha_vantage`。
2. `services/data_hub/source_manager.py` 当前全局熔断配置为 `failure_threshold=3`、`cooldown_seconds=90`、`retry_per_source=1`、`timeout_seconds=20`。
3. `services/news_pipeline/service.py` 当前新闻链路为 `EastmoneyNewsFetcher + TavilyNewsFetcher`，并已具备去重、来源统计、情绪摘要。
4. `services/config/strategy_settings.py` 已内置 `DEFAULT_PROXY_SYMBOL_MAP = {"014943": "159870"}`，说明项目已经承认“场外基金必须走代理 ETF 链路”的现实约束。
5. `docs/api/API_SUMMARY.zh-CN.md` 已定义统一数据契约与监控面，包括：
   - `/v1/data/realtime/{symbol}`
   - `/v1/data/history/{symbol}`
   - `/v1/data/news`
   - `/v1/data/flow`
   - `/api/monitor/data-sources`
   - `/api/monitor/audit-events`
   - `/metrics`
6. `scripts/check_p1_data_hub.py` 与 `scripts/check_p5_news_pipeline.py` 已提供现成验收骨架，后续只需要扩展，不需要另起一套检查体系。

结论：本次建议不推翻现有 `SourceManager`，而是在其上补“资产语义路由 + 每指标优先级 + 更明确的主备/降级策略”。

## 3. 外部来源逐项分析

### 3.1 可直接映射到数据链路的来源

| 来源 | `news` 能力 | `flow` 能力 | `fund` 能力 | 主要限制 | 主要风险 | 接入建议 |
|---|---|---|---|---|---|---|
| [`Micro-sheep/efinance`](https://github.com/Micro-sheep/efinance) | 弱；README 未体现稳定新闻能力 | 弱；当前项目里也未启用稳定 flow 接口 | 强；支持基金/ETF 历史、净值、估算相关能力 | 更偏“便捷 SDK”，不是强治理数据服务 | `LICENSE` 为 MIT，但 README 声明“不得用于商业用途”，许可证信号冲突 | 仅保留为 `fund_nav` 验收/备份链路；默认不做 HKCloud 运行时主备 |
| [`stockmcp/stock-data-mcp`](https://github.com/stockmcp/stock-data-mcp) | 强；有 `stock_news / stock_news_global` | 强；有 `stock_fund_flow / stock_sector_fund_flow_rank` | 中；更偏股票，不是基金净值专用源 | 运行形态是 MCP Server，且默认生态包含 `Tushare` | 生产运行时会引入 MCP 会话依赖；与本项目“运行时不依赖 MCP”约束冲突 | 仅用于研发期对照、架构参考和回归测试，不进生产 |
| [`oficcejo/tdx-api`](https://github.com/oficcejo/tdx-api) | 无 | 强；五档盘口、分时、逐笔成交、ETF 列表 | 弱；不适合开放式基金净值 | 只覆盖 TDX 语义的数据；更偏场内交易品种 | GitHub 元数据未识别 license，README 写 MIT，但缺少标准元数据；公共 TDX 服务器存在延迟与可用性波动 | 仅作为 ETF 盘口/分钟级 sidecar，可选部署到 HKCloud 内网 |
| [`akfamily/akshare`](https://github.com/akfamily/akshare) | 中到强；可接财经快讯、个股/宏观新闻 | 强；板块资金流、ETF/LOF/基金行情覆盖广 | 强；基金主数据、指数基金、ETF/LOF、申赎状态齐全 | 列名会随版本/上游站点变动；部分接口抓取较慢 | 上游站点反爬、字段变更、接口移除；官方声明仅供研究参考 | 继续作为 `fund` 的主力基金主数据与板块 flow 主源 |
| [`AKShare 在线文档`](https://akshare.akfamily.xyz/) | 文档层，非直接数据源 | 文档层 | 文档层 | 只提供接口说明 | 不能替代运行时可用性验证 | 作为接口名、参数、返回列权威文档，供适配器开发与回归基线使用 |
| [`AKShare 公募基金文档`](https://akshare.akfamily.xyz/data/fund/fund_public.html) | 无直接新闻能力 | 强；明确列出 ETF/LOF/分时/主力净流入字段 | 强；明确列出 `fund_name_em / fund_info_index_em / fund_purchase_em / fund_etf_spot_em / fund_etf_spot_ths` | 文档不保证实际运行时稳定 | 文档与真实返回可能存在版本差 | 作为 `fund` 字段映射与能力矩阵的直接依据 |
| [`Tavily Search API`](https://docs.tavily.com/documentation/api-reference/endpoint/search) | 强；`topic=finance/news`、`time_range`、`include_domains`、`search_depth` 明确 | 无原生 flow | 无原生 fund 行情/净值 | 本质是搜索/检索，不是行情接口 | 成本、时延、结果噪声、引用站点质量不一 | 只做“外部证据补证”与政策/宏观检索，不进入报价/净值链路 |

### 3.2 产品、工作流与交互参考来源

| 来源 | `news` 能力 | `flow` 能力 | `fund` 能力 | 主要限制 | 主要风险 | 接入建议 |
|---|---|---|---|---|---|---|
| [`etf-ark.pages.dev`](https://etf-ark.pages.dev/) | 展示层有“战术指令/解释语句”，不是新闻源 | 展示层出现“机构动量/量价特征”，不是原始 flow API | 强；输出 ETF 收市报告、分级榜单、战术建议 | 静态页面，无可复用数据 API | 只能学报告结构，不能当源 | 仅复用收市报告结构、榜单层级和解释风格 |
| [`ArvinLovegood/go-stock`](https://github.com/ArvinLovegood/go-stock) | 强；支持市场资讯、AI 总结、情感分析 | 强；支持盘口、资金趋势、行业排行 | 中；README 写明“未来计划加入基金，ETF 目前可看净值和估值” | 桌面端产品，不是轻量服务 | 股票优先、基金不是主场景 | 仅参考桌面监控、盘口/资讯融合、AI 分析交互 |
| [`UlyssesLx/fund-app`](https://github.com/UlyssesLx/fund-app) | 弱/无 | 弱/无 | 强；实时估值、自选、持仓、回测、基金经理、收益分析 | 数据源未抽象成可复用后端 | 移动端/Capacitor 架构不适合直接搬入 `fund` | 只参考基金产品 UX、持仓与收益页结构 |
| [`ZhuLinsen/daily_stock_analysis`](https://github.com/ZhuLinsen/daily_stock_analysis) | 很强；多搜索源、新闻时效、仪表盘与推送体系完备 | 中；多行情源 + 市场复盘 | 弱到中；主要是股票，不是基金主数据 | 强依赖外部 LLM、搜索与消息推送 | 容易把“新闻检索链”做得过重 | 重点复用“新闻 age gate、去重、多源 fallback、日报编排”思想 |
| [`x2rr/funds`](https://github.com/x2rr/funds) | 无 | 中；有行情中心、两市/行业/南北向资金展示 | 强；基金估值、持仓、收益、走势图、持仓明细 | Chrome 扩展形态，后端抽象弱 | GPL-3.0，不能把代码混入本仓库 | 只参考基金监控交互和字段组织，不复用代码 |
| [`Austin-Patrician/eastmoney`](https://github.com/Austin-Patrician/eastmoney) | 强；新闻聚合、情绪分析、Tavily 集成 | 中；通过 AkShare/TuShare 做数据混合 | 强；基金池、盘前/盘后报告、组合分析 | 更像完整产品，不是干净的源适配层 | 自定义“非商业许可”；且显式依赖 `TuShare`，与本项目硬约束冲突 | 仅参考“产品层如何消费数据”，不做代码或依赖接入 |
| [`run-bigpig/jcp`](https://github.com/run-bigpig/jcp) | 强；热点舆情、研报服务、MCP 扩展 | 强；实时行情、盘口深度、K 线 | 弱；核心仍是股票 | Wails 桌面形态，不是服务端数据层 | GitHub license 元数据为 `NOASSERTION`，README 说 MIT，且 `LICENSE` 文本版权头异常，需人工复核 | 仅参考多 Agent 讨论、热点舆情入口，不作数据源 |

## 4. fund 的数据链路重构方案

### 4.1 重构原则

1. **契约兼容，语义拆分**：外部 API 仍保留 `/v1/data/realtime|history|news|flow`，但内部必须拆成不同资产语义链路。
2. **先判资产类型，再选数据源**：先得到 `asset_type`，再决定走 `fund_nav`、`etf_quote` 还是 `sector_flow`。
3. **`OF` 不允许直接走盘口/资金流**：开放式基金只能走净值链路；若需要 `flow` 或盘口，必须通过 `proxy_symbol` 切到场内 ETF。
4. **主源与备源按指标，而不是按库**：同一个源库不能同时承担所有指标的主源。
5. **搜索型来源不进入原始行情链路**：`Tavily` 只能补证、补解释，不能补净值、盘口或资金流。

### 4.2 建议的能力矩阵

| 内部链路 | 适用品类 | 主源 | 备源 | 降级策略 | 备注 |
|---|---|---|---|---|---|
| `instrument_master` | `OF / ETF / LOF` | `AkShare: fund_name_em + fund_purchase_em + fund_info_index_em` | Eastmoney 原始页面/接口补字段 | 使用本地快照表 | 这里解决“基金代码是什么、跟踪标的是什么、是否可交易” |
| `fund_nav_snapshot` | `OF / LOF / 联接基金` | `Eastmoney: FundMNFInfo` | `AkShare: fund_open_fund_rank_em` | `efinance` 或本地 stale cache | 输出 `unit_nav / estimated_nav / nav_date / trade_time` |
| `fund_nav_history` | `OF / LOF` | `Eastmoney: f10/lsjz + pingzhongdata` | `efinance: fund.get_quote_history` | `AkShare: fund_info_index_em` 或最新快照 | 历史净值要优先保证连续性与日期完整 |
| `etf_quote_depth` | `ETF / 场内基金` | `Eastmoney: push2 stock/get` | `tdx-api` sidecar | `AkShare: fund_etf_spot_em / fund_etf_spot_ths` 或 cache | 盘口与逐笔成交只在这条链路出现 |
| `sector_flow` | 市场/板块/代理 ETF | `AkShare: stock_sector_fund_flow_rank` | `Eastmoney` ETF 代理报价/板块补充 | 上一交易日快照 + `stale=true` | `flow` 对 `014943` 这类场外基金一律经 `proxy_symbol` 路由 |
| `market_news` | 市场/板块/基金代理标的 | `Eastmoney: np-weblist` | `AkShare: stock_info_global_cls + stock_news_em` | 过去 6 小时缓存 | 市场新闻是默认链路 |
| `external_evidence` | 政策/宏观/海外补证 | `Tavily: /search` | 官方站点域名直抓 | 不影响主流程，只降低解释能力 | 只给 `news_feature` 和报告引用，不给交易原始值 |

### 4.3 建议的优先级调整

当前默认顺序：`eastmoney -> efinance -> akshare -> tdx -> yfinance -> alpha_vantage`

建议改成“按指标配置”的优先级，而不是一个全局列表：

1. `realtime` 且 `asset_type in (OF, LOF)`  
   `eastmoney_fund_nav -> akshare_fund_rank -> efinance_fund_nav(flagged)`
2. `history` 且 `asset_type in (OF, LOF)`  
   `eastmoney_f10 -> efinance_history(flagged) -> akshare_index`
3. `realtime/flow` 且 `asset_type == ETF`  
   `eastmoney_push2 -> tdx_sidecar(optional) -> akshare_etf_spot`
4. `flow` 且 `symbol is None` 或 `sector_mode=true`  
   `akshare_sector_flow -> stale_cache`
5. `news`  
   `eastmoney_fastnews -> akshare_cls -> tavily_finance`

### 4.4 明确的主源 + 备源 + 降级策略

#### A. 基金净值链路

1. 主源：Eastmoney 原始基金接口。
2. 备源：AkShare 基金榜单/基金信息接口。
3. 条件备源：`efinance`，默认关闭，仅在法务放行或内部环境启用。
4. 降级：返回最近成功样本，并在 `metadata` 中带上：
   - `stale=true`
   - `stale_reason`
   - `fallback_source`
   - `source_time`

#### B. ETF 行情与盘口链路

1. 主源：Eastmoney `push2 stock/get`。
2. 备源：`tdx-api` sidecar。
3. 三级备源：AkShare `fund_etf_spot_em` 或 `fund_etf_spot_ths`。
4. 降级：使用 60 秒内缓存；若超时则只返回最新已知价并禁止输出“盘中强信号”。

#### C. 板块资金流链路

1. 主源：AkShare `stock_sector_fund_flow_rank`。
2. 备源：无真正同等质量的公开板块 flow 源，实际备源应是“代理 ETF 行情 + 上一交易日 sector flow 快照”。
3. 降级：当天板块 flow 失败时，保留 ETF 代理链路，报告层显式标记 `SECTOR_FLOW_UNAVAILABLE`。

#### D. 新闻与外部证据链路

1. 主源：Eastmoney `np-weblist`。
2. 备源：AkShare 财联社/个股新闻。
3. 补证源：Tavily，固定 `topic=finance`，默认 `time_range=day|week`，开启 `include_domains` 白名单。
4. 降级：市场新闻为空时可回退到最近 6 小时缓存；Tavily 失败不应让主新闻链路失败。

## 5. 哪些需要自部署到 HKCloud

### 5.1 必须自部署

1. `fund-api`
   - 现有 `Dockerfile` 与 `docker-compose.yml` 已足够起步。
   - 最小资源建议：`2 vCPU / 4 GB RAM / 40 GB SSD / 固定出网 IP`。
   - 必挂载目录：`/app/data`、`/app/logs`、`/app/config`。

### 5.2 按需自部署

1. `tdx-api` sidecar
   - 仅当你需要 `ETF 五档盘口 / 分钟成交 / 更稳的分钟级链路` 时部署。
   - 建议与 `fund-api` 同机或同 VPC，仅暴露内网端口。
2. `Redis`
   - 当前项目还可以用现有内存 TTL + SQLite 跑起来。
   - 只有在多实例、跨进程共享缓存或高并发时再引入。

### 5.3 只建议部署到“研发/验收环境”，不要进生产

1. `stock-data-mcp`
   - 用途：架构对照、结果抽检、回归验收。
   - 不要成为 `fund-api` 的运行时依赖。

### 5.4 不建议部署

1. `etf-ark`：静态报告展示，不是服务依赖。
2. `fund-app`：移动端产品参考。
3. `x2rr/funds`：浏览器扩展参考，且 GPL-3.0。
4. `go-stock` / `jcp`：桌面产品参考，不适合 `fund` 的服务化部署。
5. `Austin-Patrician/eastmoney`：非商业许可，不进入任何生产或半生产环境。

### 5.5 HKCloud 最小可行拓扑

1. 一台 HKCloud Linux VM。
2. Docker Compose 启动 `fund-api`。
3. 使用云负载均衡或 `Caddy/Nginx` 做 HTTPS 终止。
4. 定时执行 3 组可达性探针：
   - Eastmoney 基金接口
   - AkShare 关键基金接口
   - Tavily `/search`
5. 如果 HK 出网对大陆财经站点命中反爬过高，再加 `tdx-api` sidecar，而不是先引入更多前台产品仓库。

## 6. 可执行对接清单

### 6.1 接口与字段映射

| 本地接口/链路 | 上游接口 | 原始字段 | 归一化字段 | 必做补充 |
|---|---|---|---|---|
| `GET /v1/data/realtime/{symbol}` for `OF/LOF` | Eastmoney `FundMNFInfo` | `FCODE, SHORTNAME, NAV, NAVCHGRT, GSZ, GSZZL, GZTIME, PDATE` | `symbol, name, unit_nav, daily_change_pct, estimated_nav, estimated_change_pct, trade_time, nav_date` | 增加 `asset_type, proxy_symbol, source_semantics=fund_nav` |
| `GET /v1/data/history/{symbol}` for `OF/LOF` | Eastmoney `f10/lsjz` | `FSRQ, DWJZ, LJJZ, JZZZL, SGZT, SHZT` | `date, unit_nav, acc_nav, daily_change_pct, sub_status, red_status` | 增加 `row_source_time, history_type=nav` |
| `GET /v1/data/realtime/{symbol}` for `ETF` | Eastmoney `push2 stock/get` / `tdx-api /api/quote` | `latest_price, volume, amount, turnover, bid/ask` | `latest_price, volume, amount, turnover_pct, bid1, ask1` | 增加 `source_semantics=etf_quote` |
| `GET /v1/data/flow` for `ETF/market` | `AkShare stock_sector_fund_flow_rank` / ETF 代理链路 | `名称, 主力净流入, 主力净占比, 最大股` | `sector, main_net_inflow, main_inflow_ratio, top_stock` | 对 `OF` 增加 `proxy_applied=true, effective_symbol=159870` |
| `GET /v1/data/news` | Eastmoney `np-weblist` | `title, content, showtime/time, media, url` | `title, content, time, source, url, source_channel=eastmoney` | 统一补 `published_at_utc, relevance, entity_refs` |
| `external_evidence` | Tavily `/search` | `title, content, published_date, source, url, score, request_id` | `title, content, published_at_utc, source, url, raw.score` | 严格限制为 `source_channel=tavily`，不进入原始行情对象 |

### 6.2 建议补充的配置项

1. `config/source_routing.yaml`
   - 为每个 `metric + asset_type` 定义主备顺序。
2. `config/proxy_symbol_map.json`
   - 将 `014943 -> 159870` 这类代理关系从代码挪到配置。
3. `config/source_flags.json`
   - 放 `efinance_enabled_for_runtime` 这类法务/环境开关。

### 6.3 健康检查

| 数据源 | 检查点 | 成功条件 | 失败后动作 |
|---|---|---|---|
| Eastmoney `FundMNFInfo` | 返回 `Datas[0]` | `FCODE` 与 `NAV/ACCNAV` 非空 | 打开 `fund_nav_snapshot` breaker，切 `AkShare` |
| Eastmoney `f10/lsjz` | 返回 `LSJZList[0]` | `FSRQ` 与 `DWJZ` 非空 | 切 `efinance/AkShare`，并标记 `history_stale` |
| Eastmoney `np-weblist` | 返回 `fastNewsList` | 至少 1 条，且时间可解析 | 切 `AkShare CLS` |
| AkShare `fund_name_em` | DataFrame 非空 | 至少包含 `基金代码/基金简称/基金类型` | 读取本地快照表 |
| AkShare `stock_sector_fund_flow_rank` | DataFrame 非空 | `名称` 与 `主力净流入` 非空 | 返回上一交易日 sector flow |
| `tdx-api /api/health` | HTTP 200 | 响应体包含健康标记 | 对 ETF 盘口链路降级为 Eastmoney/AkShare |
| Tavily `/search` | HTTP 200 | `results` 非空，返回 `request_id` | 只关闭补证，不影响主新闻链路 |

### 6.4 熔断阈值与超时建议

当前代码是全局 `3/90/1/20`，建议改成按链路配置：

| 链路 | timeout | retry | failure threshold | cooldown | stale 阈值 |
|---|---:|---:|---:|---:|---|
| `fund_nav_snapshot` | 8s | 1 | 3 | 90s | 1 个交易日 |
| `fund_nav_history` | 12s | 1 | 3 | 180s | 最新日期落后 1 个交易日 |
| `etf_quote_depth` | 3s | 1 | 2 | 30s | 60s |
| `sector_flow` | 10s | 1 | 2 | 120s | 1 个交易日 |
| `market_news` | 5s | 1 | 2 | 120s | 6h |
| `external_evidence` | 10s | 0 | 2 | 300s | 不做 stale 回放，只做缺省 |

### 6.5 验收标准

1. **基金净值链路**
   - 以 `014943` 为样本，`Eastmoney` 与 `AkShare/efinance` 至少两源一致。
   - 验收字段：`date`、`unit_nav`。
   - 建议阈值：`abs(diff) <= 0.001`。
2. **ETF 代理链路**
   - 以 `159870` 为样本，`Eastmoney` 与 `tdx-api/AkShare` 至少两源可取。
   - 验收字段：`latest_price`、`volume`、`amount`。
   - 价格差异应控制在“1 个最小价位或 0.3% 以内”的较大者。
3. **板块 flow 链路**
   - `stock_sector_fund_flow_rank` 返回 top20 不为空。
   - 主力净流入字段必须是数值型。
4. **新闻链路**
   - 同一轮采集至少 2 个来源通道。
   - 去重后 `processed_count < raw_count`。
   - 超过 `72h` 的新闻默认不进入因子摘要。
5. **监控链路**
   - `/api/monitor/data-sources` 能看到 `avg_latency_ms / consecutive_failures / circuit_open_until / fallback_source`。
   - `/metrics` 能导出 Prometheus 指标。
6. **降级链路**
   - 模拟 Eastmoney 主源失败时，`P1` 与 `P5` 校验脚本仍能完成且返回 `fallback_source` 或 `stale=true`。

## 7. 实施顺序建议

1. 先做“路由层”，不要先加源：
   - 新增 `asset_type` 判定与 `proxy_symbol_map` 配置化。
2. 再做“主备调整”：
   - 将 `efinance` 从默认高优先级移到可选备源。
3. 再做“监控与熔断细化”：
   - 把全局 breaker 改为按链路配置。
4. 最后做“可选 sidecar”：
   - 只有当 ETF 盘口和分钟级需求真实存在时，才接 `tdx-api`。

## 8. 最终建议

1. `fund` 的下一步不是“继续找更多仓库”，而是把现有 `Eastmoney + AkShare + Tavily` 变成明确分层的数据链路。
2. 最值得立刻落地的不是新 UI，而是：
   - `asset_type/proxy_symbol` 配置化
   - `metric-specific routing`
   - `efinance` 降级
   - `Tavily` 域名白名单与时效治理
3. HKCloud 上最小可行就是一个 `fund-api` 容器；`tdx-api` 是可选性能增强件，`stock-data-mcp` 是研发件，不要混成生产依赖。
