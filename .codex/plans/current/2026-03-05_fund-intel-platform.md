# 中国基金智能分析平台项目规划报告（v1.0）

生成日期：2026-03-05  
规划模式：`$plan`（只读分析 + 计划落地，不改业务代码）  
项目状态：从 0 到 1 的新项目规划阶段  
硬约束：`不使用 TuShare`

---

## 1. 项目目标与边界

### 1.1 目标

建设一个面向中国基金/ETF 的智能分析平台，核心能力包含：

1. 实时行情与资金动态采集（含买卖盘、成交量、资金流向）。
2. 板块级评分与轮动分析（行业/主题/指数维度）。
3. 单基金量化评分、信号生成与可解释输出。
4. 新闻与国际动态融合，增强事件驱动判断。
5. 生成接近 `etf-ark` 风格的收市报告与看板展示。

### 1.2 首期交付（MVP）

1. 覆盖 A 股基金/ETF 主流标的池（首批 300-1000 只）。
2. 输出交互看板（盘中实时 + 历史回溯）。
3. 输出收盘日报（榜单、评分、战术建议、风险提示）。
4. 提供基础回测能力：收益率、最大回撤、胜率、换手率。

### 1.3 非目标（MVP 暂不做）

1. 不直接下单交易，不接券商实盘 API。
2. 不做高频毫秒级交易系统。
3. 不做跨境全市场覆盖（国际先做信息补充，不做全量交易逻辑）。

---

## 2. 需求拆解（按数据与能力）

### 2.1 数据层需求

1. 实时行情：基金净值估算、ETF/指数价格、成交量、买卖盘。
2. 资金数据：主力资金、板块资金流、成交结构。
3. 基金基础信息：类型、跟踪标的、规模、费率、历史净值。
4. 新闻快讯：国内财经新闻、公告、政策动向。
5. 国际动态：美股/港股指数、海外 ETF 与宏观事件摘要。

### 2.2 分析层需求

1. 因子体系：趋势、动量、波动、回撤、量价、资金流、情绪。
2. 评分引擎：板块评分 + 基金评分 + 可解释分项。
3. 信号引擎：买入/卖出/观望分级建议。
4. 回测体系：按策略参数重放，验证稳健性与容量。

### 2.3 展示层需求

1. 实时监控看板：榜单、热力图、分时变化。
2. 收盘报告：Top/Bottom、战术建议、事件解释、风险清单。

---

## 3. 外部调研结论

### 3.1 对标效果站点

参考站点：`https://etf-ark.pages.dev/`  
可借鉴点：

1. 结果导向表达（不只展示数据，而是给“可执行战术提示”）。
2. 结构化报告模板（分层榜单 + 风险提示 + 操作建议）。
3. 读者友好型可解释性（每个结论可回溯到指标）。

### 3.2 GitHub 参考仓库调研（2026-03-05 快照）

| 仓库 | Stars | 主语言 | License | 最新活跃（pushed_at） | 可借鉴方向 | 使用策略 |
|---|---:|---|---|---|---|---|
| Micro-sheep/efinance | 3360 | Python | MIT | 2025-10-10 | A 股/基金数据封装 | 作为主数据适配器之一 |
| stockmcp/stock-data-mcp | 22 | Python | MIT | 2026-02-26 | 多数据源熔断/降级架构 | 架构模式重点参考 |
| ArvinLovegood/go-stock | 4736 | Go | Apache-2.0 | 2026-03-04 | Go 数据服务与接口组织 | 可做 Go sidecar 参考 |
| UlyssesLx/fund-app | 27 | 混合 | MIT | 2026-01-30 | 基金分析应用落地样例 | 交互与接口命名参考 |
| ZhuLinsen/daily_stock_analysis | 15988 | Python | MIT | 2026-03-03 | 日报自动化与分析流程 | 报告流水线参考 |
| oficcejo/tdx-api | 363 | Go | 未声明 | 2025-12-02 | TDX 协议服务化 | 仅协议思路参考 |
| x2rr/funds | 2943 | Vue | GPL-3.0 | 2026-02-27 | 前端展示与基金页面交互 | 只参考思路，不拷贝代码 |
| Austin-Patrician/eastmoney | 517 | Python | 自定义（非商用约束） | 2026-02-24 | Eastmoney 接口调用样例 | 只做接口研究，不直接复用 |
| run-bigpig/jcp | 790 | Go | 未明确 SPDX | 2026-03-03 | 金融数据服务化实践 | 参考架构，不直接复用 |
| akfamily/akshare | 16764 | Python | MIT | 2026-03-04 | 全市场数据接口覆盖广 | 作为补充数据源 |

> 注：Stars/活跃时间来自 GitHub API 当日查询；License 以仓库声明为准，商用前需二次法务核验。

### 3.3 数据源与接口可行性结论（排除 TuShare）

已确认可行的数据获取路线（按推荐优先级）：

1. `AkShare`（MIT）作为首层标准化入口，优先使用稳定的基金类接口。
2. `Eastmoney` 原生接口作为二层直连能力，用于补足时效与字段颗粒度。
3. `stock-data-mcp` 作为多源编排与熔断参考实现，复用其 source manager 设计。
4. `TDX 协议`（tdx-api）用于低延迟行情补充。
5. `yfinance / Alpha Vantage` 用于国际市场补充。
6. `Tavily Search` 用于外部资讯检索增强（不是行情源，是研究源/解释源）。

`AkShare` 在本项目中的定位调整为“主力数据适配器”，不是仅补充：

1. 已实测可用：`fund_name_em`、`fund_info_index_em`、`fund_purchase_em`、`fund_open_fund_rank_em`、`fund_etf_spot_ths`。
2. 已识别不稳定点：`fund_etf_spot_em` 在当前网络路径下因依赖 `https://88.push2.eastmoney.com/...clist...` 出现连接中断。
3. 结论：ETF 实时链路采用 `THS` 与 `Eastmoney ulist` 双通道，`EM clist` 作为条件可用通道。

### 3.4 接口实测验证结论（2026-03-05）

| 接口 | 请求方式 | 关键条件 | 实测结果 |
|---|---|---|---|
| `FundMNFInfo` | GET / POST(简参) | 仅 `FCODE/Fcodes` | 返回 `ErrCode=61136/61136403`（网络繁忙） |
| `FundMNFInfo` | POST(form) | 必带移动端参数：`plat/product/version/deviceid/P` | `200` 且返回 `Datas` |
| `FundMNHisNetList` | POST(form) | 同上移动端参数 | `200` 且返回净值序列 |
| `rankhandler.aspx` | GET | 无 `Referer` | 返回“无访问权限” |
| `rankhandler.aspx` | GET | `User-Agent + Referer` | 正常返回 `rankData` |
| `pingzhongdata/{code}.js` | GET | 常规浏览器头 | 稳定返回历史净值脚本 |
| `np-listapi` 旧路径 | GET | 缺 `req_trace` 或旧参数 | 400/空结果 |
| `np-weblist` 新路径 | GET | 必带 `req_trace` | 正常返回 `fastNewsList` |
| `push2 stock/get` | HTTPS GET | 常规浏览器头 | 正常 |
| `push2 ulist.np/get` | HTTPS GET | 常规浏览器头 | 正常 |
| `push2 clist/get` | HTTPS GET | 即便加浏览器头仍可能被断连 | 在当前网络路径不稳定 |
| `push2 clist/get` | HTTP GET | 参数同上 | 可返回数据（ETF/板块） |

### 3.5 反爬与稳定调用策略（必须落地）

1. 请求头伪装最小集：`User-Agent`、`Referer`、`Accept-Language`，按端点补 `Origin`。
2. `FundMNewApi` 系列统一使用 `POST form`，并固定移动端上下文参数模板。
3. 对 `push2` 建立协议回退：`HTTPS -> HTTP`（仅对已验证的 `clist` 路径启用）。
4. 为资讯接口统一注入 `req_trace`（如 `np-weblist`），避免参数缺失失败。
5. 做速率治理：令牌桶 + 抖动重试 + 指数退避，禁止无间隔扫全量。
6. 做结果降级：主源失败即切备源，仍失败时返回 `stale cache` 并标记新鲜度。

### 3.6 stock-data-mcp 验证摘要

1. 代码层已验证其核心模式：`DataFetcherManager + CircuitBreaker + 动态 TTL + source fallback`。
2. 运行态已验证：`data_source_status` 可输出数据源状态；`stock_news_global` 可返回 `新浪 + NewsNow` 聚合快讯。
3. 风险记录：本地会话中出现过 MCP 连接中断（`Not connected`），生产化需加健康探测和自动重连。

### 3.7 基金 `014943` 多源验收样例（2026-03-05 实测）

| 数据源 | 接口/方法 | 可获取性 | 关键样本 | 结论 |
|---|---|---|---|---|
| Eastmoney | `FundMNFInfo`（App 风格 `GET+data`） | 可用（部分降级） | `NAV=1.0300`、`PDATE=2026-03-04`，`GSZ/GSZZL/GZTIME=null` | 可作为净值快照源，不可单独承担盘中估算 |
| Eastmoney | `api.fund.eastmoney.com/f10/lsjz` | 可用 | `FSRQ=2026-03-04`、`DWJZ=1.0300`、`JZZZL=-1.44` | 历史净值主链路可用 |
| Eastmoney | `pingzhongdata/014943.js` | 可用 | `Data_netWorthTrend` 最新 `y=1.03` | 历史序列与图表回放可用 |
| AkShare | `fund_open_fund_rank_em(symbol='全部')` | 可用 | `日期=2026-03-04`、`单位净值=1.03` | 可做净值与区间收益主源 |
| efinance | `fund.get_realtime_increase_rate('014943')` | 可用（部分降级） | `最新净值=1.03`、`最新净值公开日期=2026-03-04`、估算字段空 | 适合做冗余校验源 |
| efinance | `fund.get_quote_history('014943')` | 可用 | 最新行 `日期=2026-03-04`、`单位净值=1.03` | 历史净值备份链路可用 |

交叉一致性（`014943`）：

1. `Eastmoney f10` vs `AkShare`：日期一致（`2026-03-04`），单位净值一致（`1.03`，差值 `0.00`）。
2. `Eastmoney f10` vs `efinance`：日期一致（`2026-03-04`），单位净值一致（`1.03`，差值 `0.00`）。
3. 当前验收项（日期 + 单位净值）一致性评分：`100/100`。

重要语义约束：

1. `014943` 为场外联接基金（`OF`），不具备盘口买卖盘与逐笔成交语义。
2. 需要“买入/卖出、成交量、资金流”时，必须切换到其关联 ETF（如 `159870`）和板块数据链路，不允许直接把 `014943` 当股票盘口处理。

### 3.8 每步开发强制验收规范（以 `014943` 为基准样例）

每完成一个开发步骤，必须输出一次“数据源验收记录”，最低包括：

1. 可获取性：主源 + 备源至少各 1 条成功样本（包含时间戳与关键字段）。
2. 准确性：同一指标至少双源对比（如 `日期/单位净值/涨跌幅`），并给出差值阈值判断。
3. 新鲜度：标注 `source_time` 与 `ingest_time`，超过阈值自动标注 `stale`。
4. 可降级性：模拟主源失败，验证自动回退到备源或缓存。
5. 证据留档：保存到 `evidence`（请求参数模板、响应摘要、判定结果）。
6. 首份样例证据：`.codex/plans/current/evidence/2026-03-05_014943-source-validation.md`。
7. P1 验收证据：`.codex/plans/current/evidence/2026-03-05_p1-data-hub-validation.md`。
8. P2 验收证据：`.codex/plans/current/evidence/2026-03-05_p2-storage-validation.md`。
9. P3 验收证据：`.codex/plans/current/evidence/2026-03-05_p3-factor-engine-validation.md`。
10. P4 验收证据：`.codex/plans/current/evidence/2026-03-05_p4-backtest-validation.md`。
11. P5 验收证据：`.codex/plans/current/evidence/2026-03-05_p5-news-fusion-validation.md`。

### 3.9 新闻/财经/政策数据链路验收（2026-03-05 实测）

| 类型 | 数据源 | 实测接口/方法 | 结果 | 备注 |
|---|---|---|---|---|
| 快讯 | `stock-data-mcp` | `stock_news_global` | 可用 | 返回 `新浪 + NewsNow` 聚合快讯 |
| 个股/主题新闻 | `stock-data-mcp` | `stock_news(symbol='014943'/'159870')` | 可用 | 可用于基金-ETF-主题关联证据补充 |
| 财联社快讯 | `AkShare` | `stock_info_global_cls()` | 可用（20 条） | 高频事件流，适合盘中冲击信号 |
| 个股新闻 | `AkShare` | `stock_news_em(symbol='600519')` | 可用（10 条） | 可迁移到 ETF 成分股舆情聚合 |
| 宏观日历 | `AkShare` | `news_economic_baidu(date='20260305')` | 可用（81 条） | 用于宏观事件窗口标注 |
| 政策信号 | `AkShare` | `news_cctv(date='20260304')` | 可用（14 条） | 可提取政策关键词与行业映射 |
| 监管信息 | `CSRC` 官网 | `http://www.csrc.gov.cn/`（新闻发布会/市场快报链接） | 可抓取 | 官方源，适合做高权重政策事件 |

结论：

1. 新闻与财经信息链路已拿到可用数据，不是纸面设计。
2. 对基金决策影响最大的“政策/监管信号”已确认可从官方站点与高权重媒体双通道获取。
3. 需要把“来源权重 + 时效衰减 + 交叉验证”作为默认机制，避免单条快讯误导。
4. 本轮验收证据：`.codex/plans/current/evidence/2026-03-05_news-policy-validation.md`。

### 3.10 类似开源项目经验（GitHub 核验后可复用）

| 仓库 | 可复用经验 | 对本项目落地点 |
|---|---|---|
| `ZhuLinsen/daily_stock_analysis` | 新闻搜索多源（含 Tavily）+ 新闻时效门槛（如 `NEWS_MAX_AGE_DAYS`）+ 日报/复盘流水线 | 直接用于 `Report Engine` 的“盘后复盘模板 + 新闻时效过滤” |
| `24mlight/A_Share_investment_Agent` | 新闻多源整合、去重、缓存、情绪驱动回测参数 | 直接用于 `Research Engine` 的“增量抓取 + 去重 + 情绪特征” |
| `ethqunzhong/InStock` | 全市场数据抓取、ETF 与行业资金流、定时任务 + 回测联动 | 直接用于“全基金/全板块复盘作业编排” |
| `khscience/OSkhQuant` | 强调回测-模拟-实盘一致接口与本地可追溯数据资产 | 直接用于策略层的统一执行接口与审计链路 |
| `UFund-Me/Qbot` | 多因子/多策略工作流、基金与股票混合研究范式 | 直接用于因子工厂和策略实验框架设计 |
| `DIYgod/RSSHub` | 通用 RSS 化聚合框架（适合把异构资讯源标准化） | 作为资讯接入的可选补充层（注意 AGPL 许可证边界） |

经验提炼（必须落地）：

1. 新闻必须做 `增量抓取 + 去重 + 时效窗口`，不做“全量重复抓”。
2. 复盘报告必须固定模板化输出（榜单、因子解释、风险标记、证据链接）。
3. 事件驱动结论必须保留原文证据与时间戳，支持事后归因复查。
4. 策略上线前必须通过 `IS/OOS + 成本/滑点` 约束，不接受纯样本内漂亮曲线。

### 3.11 部署独立性约束（Docker 运行时）

1. 生产运行时数据获取必须是“源站直连”（HTTP/SDK），不得依赖 MCP 会话。
2. `stock-data-mcp` 仅可作为研发期的数据验证与对照工具，不进入运行时依赖。
3. 运行时依赖白名单：`requests/pandas/akshare/efinance/yfinance`（`AlphaVantage` 仅在配置 key 时启用）。
4. 提供自动检查脚本：`scripts/check_runtime_independence.py`，扫描运行时代码中的 MCP 关键调用痕迹。
5. Docker 基线命令：`docker build -t fund-intel:dev . && docker run --rm fund-intel:dev`，默认执行独立性检查与 P1 数据链路检查。
6. 本轮独立性验收证据：`.codex/plans/current/evidence/2026-03-05_runtime-independence-check.md`。

---

## 4. 技术选型与总体方案

### 4.1 选型对比

| 方案 | 描述 | 优点 | 风险 | 结论 |
|---|---|---|---|---|
| A. Python 主栈 + Go 辅助服务 | 核心分析/回测用 Python，低延迟网关可选 Go sidecar | 数据生态成熟，研发速度快，扩展灵活 | 双语言协作成本 | `推荐` |
| B. 全 Go | 全链路 Go 化 | 性能好、部署统一 | 量化生态与数据处理效率偏弱 | 不作为首选 |
| C. 全 Python | 所有模块 Python | 开发最快 | 极端高并发场景有性能瓶颈 | 可作为早期最简版本 |

推荐：**A（Python 主栈 + Go 可选边车）**。  
理由：量化研发效率和生态优先，同时保留高性能扩展点。

### 4.2 推荐技术栈

1. API 层：FastAPI + Pydantic。
2. 调度层：APScheduler（盘中/盘后任务）+ Celery 或 RQ。
3. 数据接入：Adapter 模式（AkShare/efinance/Eastmoney raw/TDX/yfinance/AlphaVantage）。
4. 实时缓存：Redis（秒级 TTL）。
5. 历史层：PostgreSQL + TimescaleDB（时序查询友好）。
6. 对象归档：MinIO（可选，用于快照与报告归档）。
7. 分析引擎：Pandas/Polars + NumPy + vectorbt（回测）。
8. 前端：Next.js + ECharts（对标 `etf-ark` 的报告表现）。
9. 可观测：Prometheus + Grafana + Loki + Sentry。
10. 部署：Docker Compose（开发）-> Kubernetes（生产可选）。
11. 研究检索层：Tavily Search API（`topic=finance/news` + `time_range` + `include_domains`）。

### 4.3 量化策略与模型准确度提升框架

1. 策略研究基线：趋势跟随、横截面动量、波动/回撤约束、行业轮动、事件驱动。
2. 因子上线门槛：必须通过 `IS/OOS` 分离验证，不允许只看样本内收益。
3. 组合构建约束：加入交易成本、滑点、容量约束，杜绝“纸面高收益”。
4. 信号置信机制：每次模型结论至少有 `2` 个独立数据源证据支撑。
5. 数据质量闸门：缺失率、延迟、时间戳漂移超阈值时，模型只输出“观望/低置信”。
6. 结论输出规范：强制返回 `evidence + factor_breakdown + risk_flags + confidence`。
7. 研究增强链路：Tavily 用于外部事件补证，不直接替代行情与净值原始源。

### 4.4 ETF 全市场复盘与榜单能力（新增硬需求）

实测可用的数据基础（2026-03-05）：

1. 全开放式基金榜单：`AkShare fund_open_fund_rank_em(symbol='全部')`，约 `19310` 条。
2. 交易所基金榜单：`AkShare fund_exchange_rank_em()`，约 `1419` 条。
3. ETF 实时净值快照：`AkShare fund_etf_spot_ths()`，约 `1478` 条。
4. 板块资金流榜单：`AkShare stock_sector_fund_flow_rank()`，行业与概念均可用（`497`/`468` 量级）。

复盘榜单设计（盘后）：

1. 基金榜：按近 `1/5/20` 日收益、回撤、波动、资金偏好综合评分。
2. ETF 榜：按成交活跃度、趋势强度、资金净流入、跟踪误差评分。
3. 板块榜：按主力净流入、涨跌幅、持续性（连日强度）评分。
4. 政策敏感榜：按政策关键词命中率与事件后超额收益贡献排序。

---

## 5. 系统架构设计

### 5.1 分层架构

1. Data Hub（多源采集与健康检查）。
2. Normalization（统一实体模型与字段标准化）。
3. Storage（实时缓存 + 历史时序落库）。
4. Factor Engine（因子计算与评分）。
5. Strategy Engine（信号生成与回测）。
6. Research Engine（Tavily + 资讯聚合的外部证据检索与对齐）。
7. Report Engine（日报与收盘报告）。
8. API & Dashboard（服务与展示）。

### 5.2 关键机制：多源熔断与降级

目标：任何单源失败不致命，服务保持可用。

核心策略：

1. SourceAdapter 标准接口：`fetch_quote / fetch_nav / fetch_news / health_check`。
2. 源健康评分：成功率、延迟、错误率、最近可用时间。
3. 熔断：连续失败超过阈值进入 OPEN，冷却后 HALF-OPEN 探测恢复。
4. 降级：主源失败自动切备源，返回结果附带 `source` 与 `quality_score`。
5. 缓存兜底：当全部失败时返回最近可用缓存，并标记 `stale=true`。

伪代码（高层）：

```text
for source in sorted(available_sources by health_score):
  if source.circuit_open:
    continue
  result = source.fetch(request)
  if result.ok:
    cache.write(result)
    return normalized(result, quality=source.health_score)
  source.record_failure()

fallback = cache.read_latest(request.key)
if fallback:
  return mark_stale(fallback)
raise DataUnavailableError
```

### 5.3 自研 `Fund Data Collector`（接口不可行时兜底）

当现有接口不可行或被限制时，直接启用自研采集组件，目标是“拿到可分析数据”而非等待接口恢复。

核心子模块：

1. `Template Registry`：按源维护请求模板（`method/url/headers/cookies/query/body`）与版本号，支持热更新。
2. `Browser Camouflage`：内置移动端与桌面端请求画像（`UA/Referer/Origin/Accept-Language`），并支持端点级覆盖。
3. `Adaptive Fetcher`：协议与路径回退（`HTTPS->HTTP`、新旧端点轮询）、限速与指数退避。
4. `Response Parser`：`JSON/JSONP/JS script/HTML` 多协议解析，统一映射到标准字段。
5. `Cross-Source Verifier`：同指标双源交叉校验，不达阈值则降级输出低置信结果。
6. `Evidence Logger`：自动记录采集证据与判定过程，供回溯与审计。

高层流程（pseudocode）：

```text
for endpoint in template_registry.by_priority(metric):
  resp = adaptive_fetch(endpoint, with_camouflage=True)
  parsed = parse_and_normalize(resp)
  if parsed.valid:
    evidence.log(endpoint, parsed)
    if verifier.pass_with_backup(parsed, backup_source):
      return parsed
fallback = cache.latest(metric)
return mark_low_confidence(fallback)
```

---

## 6. 统一数据模型（建议）

### 6.1 核心实体

1. `instrument`：基金/ETF 基础信息。
2. `quote_tick`：实时行情快照（price/volume/bid_ask/turnover）。
3. `fund_nav_snapshot`：净值/估值快照。
4. `sector_flow_snapshot`：板块资金流与热度。
5. `news_event`：新闻事件（时间、来源、情绪、标签）。
6. `factor_score`：分因子评分。
7. `signal_event`：买卖/观望信号及置信度。

### 6.2 字段规范

1. 时间统一 `Asia/Shanghai`，数据库落库同时存 UTC。
2. 金额统一 `CNY`，国际补充数据附币种字段。
3. 所有记录保留 `source`、`ingest_time`、`quality_score`。
4. 所有衍生结果保留 `calc_version`（确保可追溯）。

---

## 7. 新闻与国际动态融合方案

### 7.1 数据链路

1. 采集：国内快讯（`np-weblist`/NewsNow/新浪）+ 海外市场资讯 + 指数行情。
2. 清洗：去噪、去重、正文抽取、实体识别（基金/板块/主题）。
3. 情绪：规则 + 轻量 NLP 模型输出 `sentiment_score`。
4. 关联：将新闻映射到基金池与板块池。
5. 产出：事件冲击标签（正向/中性/负向）进入评分引擎。

### 7.2 融合规则建议

1. 时间衰减：新闻影响分随时间衰减。
2. 来源权重：权威媒体权重 > 自媒体聚合源。
3. 冲突处理：多源结论冲突时使用置信度加权。

### 7.3 Tavily 接入规范（新增）

1. 角色定位：`Tavily` 仅用于外部事件补证与解释增强，不作为行情主数据源。
2. 查询策略：默认 `topic=finance`，并启用 `time_range`（day/week）限制时效漂移。
3. 域名白名单：优先主流财经媒体与监管机构域名，抑制低质量站点噪声。
4. 结果治理：每条 Tavily 结果要做来源评分与去重，低置信内容不进入交易信号。
5. 成本治理：按问题类型切换 `search_depth`，盘中默认 `basic/fast`，盘后复盘可 `advanced`。

### 7.4 政策事件融合规则（新增）

1. 事件分级：`监管发布 > 部委政策 > 主流媒体快讯 > 聚合转载`。
2. 行业映射：政策关键词映射到行业/主题词典，再映射到 ETF 与联接基金。
3. 时间窗：默认 `T+0`（盘中）与 `T+1~T+5`（延迟影响）双窗口评估冲击。
4. 证据门槛：政策类结论至少 2 个独立来源（如官方站点 + 主流财经媒体）。
5. 风险控制：来源冲突或证据不足时，只输出“观望/低置信”，禁止强买卖信号。

---

## 8. 合规与许可证治理

### 8.1 许可证策略

1. MIT/Apache 项目：可参考并按条款复用。
2. GPL-3.0：避免代码混入闭源主体；仅做思路参考。
3. 非商用/自定义许可证：不直接集成代码，避免商用风险。
4. 未声明许可证：默认保守处理，仅参考架构思想。

### 8.2 本项目约束

1. 建立 `THIRD_PARTY_NOTICES.md`（后续执行阶段创建）。
2. 引入依赖前做 SPDX 扫描（CI 自动化）。
3. 数据源使用条款单独登记（接口频率、用途、展示限制）。

---

## 9. 实施计划与里程碑（对齐 MCP 任务）

### 9.1 阶段划分

| 阶段 | 时间（建议） | 目标 | 对应任务 ID |
|---|---|---|---|
| P0 立项与范围冻结 | 第 1 周 | 明确 MVP、指标、验收口径 | `5b444d70-1bbe-4a64-8bfc-9909c73e6080` |
| P1 数据接入层 | 第 2-3 周 | 多源 Adapter + 熔断 + 健康检查 | `b10a778b-cbaa-4a96-a03e-4193b1508040` |
| P2 存储与标准化 | 第 4-5 周 | 标准模型 + Redis + Timescale | `ca1788c2-b7ac-471b-812d-01162f65edbb` |
| P3 因子与评分 | 第 6-7 周 | 因子框架与可解释评分 | `dc9d5e8d-a635-440c-8958-138fc98422bd` |
| P4 策略与回测 | 第 8 周 | 信号生成、回测评估 | `83b0af56-58db-4654-86bc-10ab90c3167d` |
| P5 新闻与国际动态 | 第 8-9 周 | 新闻融合与事件驱动打分 | `4f6bab26-2e03-4bd9-b970-277914f05cda` |
| P6 报告与看板 | 第 10-11 周 | 收盘报告 + 可视化工作台 | `6ef99d01-d788-432f-82fd-52de50071e32` |
| P7 稳定性与治理 | 第 12 周 | 监控、测试、合规、发布 | `d760e8c6-2544-46ec-b08e-daca131eaf8c` |

### 9.2 并行策略

1. P3（因子）与 P5（新闻）可在 P2 后并行推进。
2. P6（报告）依赖 P3/P4/P5，需在核心数据链路稳定后开发。
3. P7 贯穿全程，但在发布前集中验收。

### 9.3 每步交付闸门（强制）

1. 每个阶段任务关闭前，必须附带“本阶段数据源验收记录”。
2. 验收记录至少覆盖：`014943`（场外净值链路）+ 1 个关联 ETF（盘中交易链路，如 `159870`）。
3. 任一关键字段出现跨源不一致（超阈值）时，任务不得标记完成。
4. 所有策略结论必须附双源证据；证据不足时只能输出“观望/低置信”。

---

## 10. 验收标准（MVP）

### 10.1 功能验收

1. 支持主流基金/ETF 实时监控与历史回溯。
2. 支持板块评分、单基金评分与可解释分项。
3. 支持收盘报告自动生成（含建议与风险提示）。
4. 支持新闻与国际动态对评分的联动影响。

### 10.2 性能与稳定性验收

1. 盘中核心标的数据刷新延迟：目标 `<= 5s`（P95）。
2. 主数据源故障切换：目标 `<= 30s` 完成恢复。
3. 报告产出时效：交易日 `15:10` 前完成第一版。
4. 服务可用性：MVP 阶段目标 `>= 99.0%`。

### 10.3 质量与可追溯验收

1. 任一评分可追溯到原始数据与计算版本。
2. 回测可重复（固定参数 + 固定数据快照）。
3. 单元测试 + 集成测试覆盖关键链路。

### 10.4 数据源验收硬标准

1. `014943` 的日期与单位净值在 `Eastmoney/AkShare/efinance` 至少两源一致。
2. 关联 ETF 的行情字段（价格、成交量）可持续获取，且有备源。
3. 新闻链路至少双源可用（如 Eastmoney + NewsNow/新浪/Tavily 检索补证）。
4. 任一主源失效时，系统在 `30s` 内完成降级并给出新鲜度标签。

---

## 11. 风险清单与缓解

| 风险 | 影响 | 触发条件 | 缓解措施 |
|---|---|---|---|
| 数据源接口变更或限流 | 实时数据中断 | 接口字段变化、频率受限 | 多源冗余 + 版本化解析 + 限流治理 |
| 接口协议差异（HTTP/HTTPS/参数约束） | 部分链路间歇性不可用 | 同一接口不同协议或参数策略变化 | 端点级请求模板 + 协议回退 + 持续探测 |
| 第三方许可证冲突 | 商用受阻 | 引入 GPL/非商用代码 | 白名单依赖策略 + CI 扫描 + 法务审查 |
| 因子过拟合 | 实盘失真 | 历史表现好、未来失效 | Walk-forward 验证 + OOS 检验 |
| 模型结论幻觉或过度自信 | 错误交易建议 | 数据证据不足仍强行输出结论 | 双源证据门槛 + 置信度阈值 + 人工复核 |
| 联接基金与 ETF 语义错配 | 指标解释错误 | 把 `OF` 基金当盘口资产分析 | 建立资产类型守卫：`OF` 仅净值分析，盘口类指标强制走关联 ETF |
| MCP 连接不稳定 | 工具调用中断 | `Not connected` 或会话丢失 | 本地 HTTP 直连兜底 + 健康探测 + 自动重连 |
| 新闻情绪噪声 | 误导信号 | 垃圾资讯占比高 | 来源权重 + 去重 + 人工抽检 |
| 资源瓶颈 | 延迟升高 | 盘中高并发请求 | 缓存前置 + 批量拉取 + 异步队列 |

---

## 12. 开发结构建议（目录草案）

```text
fund-intel/
  apps/
    api/                 # FastAPI 服务
    worker/              # 定时任务与异步任务
    web/                 # Next.js 看板与报告页
  services/
    data_hub/            # 多源适配与熔断
    factor_engine/       # 因子与评分
    strategy_engine/     # 信号与回测
    report_engine/       # 报告生成
  libs/
    schemas/             # Pydantic 模型
    connectors/          # 数据连接器
    observability/       # 日志/指标封装
  infra/
    docker/
    k8s/
  docs/
    ADR/
    data-source-policy/
```

---

## 13. 结论与下一步

### 13.1 结论

1. 项目方向明确可行，且有充足开源参考与接口生态支撑。
2. 在排除 TuShare 前提下，仍可通过 Eastmoney 生态 + efinance/AkShare + 国际补充源实现目标。
3. 推荐采用 Python 主栈快速落地，关键瓶颈再用 Go 侧车增强性能。

### 13.2 下一步执行建议

1. 用户确认该规划文档后，进入 `/do-plan` 执行阶段。
2. 先落地 P0/P1（范围冻结 + 数据接入骨架），1 周内给出首个可跑通样机。
3. 建立测试和合规门禁，从第一天开始约束，而不是收尾补锅。

---

## 14. 参考链接

1. https://etf-ark.pages.dev/
2. https://github.com/Micro-sheep/efinance
3. https://github.com/stockmcp/stock-data-mcp
4. https://github.com/ArvinLovegood/go-stock
5. https://github.com/UlyssesLx/fund-app
6. https://github.com/ZhuLinsen/daily_stock_analysis
7. https://github.com/oficcejo/tdx-api
8. https://github.com/x2rr/funds
9. https://github.com/Austin-Patrician/eastmoney
10. https://github.com/run-bigpig/jcp
11. https://github.com/akfamily/akshare
12. https://akshare.akfamily.xyz/
13. https://akshare.akfamily.xyz/data/fund/fund_public.html
14. https://docs.tavily.com/documentation/api-reference/endpoint/search
15. https://kuaixun.eastmoney.com/jj.html
16. https://kuaixun.eastmoney.com/emresource/main/js/kuaixun.js?v=2026.03.05.12
17. https://np-weblist.eastmoney.com/comm/web/getFastNewsList
18. https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html
19. https://www.sciencedirect.com/science/article/abs/pii/0304405X93900235
20. https://www.sciencedirect.com/science/article/abs/pii/0304405X9390079S
21. https://www.aqr.com/Insights/Research/Journal-Article/A-Century-of-Evidence-on-Trend-Following-Investing
22. https://api.fund.eastmoney.com/f10/lsjz?fundCode=014943&pageIndex=1&pageSize=10
23. https://fund.eastmoney.com/pingzhongdata/014943.js
24. https://raw.githubusercontent.com/stockmcp/stock-data-mcp/main/README.md
25. https://github.com/ZhuLinsen/daily_stock_analysis
26. https://github.com/24mlight/A_Share_investment_Agent
27. https://github.com/ethqunzhong/InStock
28. https://github.com/khscience/OSkhQuant
29. https://github.com/UFund-Me/Qbot
30. https://github.com/DIYgod/RSSHub
31. http://www.csrc.gov.cn/
32. https://www.gov.cn/zhengce/zuixin/
33. https://www.pbc.gov.cn/goutongjiaoliu/113456/113469/index.html
