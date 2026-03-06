# 任务计划：前端配置中心与策略配置交付

## 元信息
- 计划 ID：plan-2026-03-07-frontend-strategy-config-delivery
- 创建时间：2026-03-07T02:55:00+08:00
- 状态：blocked（推送鉴权失败，代码与自测已完成）
- 执行方式：按 `plan -> do-plan` 连续执行
- 复杂度：高
- 计划文件：`.codex/plans/current/2026-03-07_frontend-strategy-config-delivery.md`
- MCP 同步：是
- 用户批准来源：当前会话已明确要求“先计划后执行，并直接提交到 main、推送 origin”

---

## 任务目标

在不破坏现有 `fund-api` 运行链路的前提下，以最小可运行、可部署闭环交付一套受登录保护的管理台和对应最小后端 API，覆盖模型配置、策略配置、今日报告、单基金报告、链路监控、配置热更新、离线回放与参数调优，并补齐验证脚本与文档。

---

## 已确认事实

1. 后端入口当前只有 `apps/api/report_api.py`，运行于 Python 标准库 `BaseHTTPRequestHandler`。
2. 前端当前只有 `apps/web/src/pages/etf-report.tsx` 与 `apps/web/src/pages/fund-detail.tsx` 两个原型文件，仓库内无 `package.json`，不存在现成 Node 前端构建链。
3. 已有能力可复用：
   - `DailyReportService`：日报与单基金详情生成、导出
   - `SourceMonitor` + `SourceManager`：数据源健康、告警、熔断、审计事件
   - `BacktestRunner`：基于历史快照的离线回放
   - `WeightTemplateManager`：文件配置热重载（mtime + hash）
4. 当前仓库无 `.codex/lessons/` 本地经验库，本轮风险控制以现有主计划、前端计划和代码基线为准。

---

## 技术决策

1. **单服务交付**：继续以 `apps/api/report_api.py` 为唯一运行入口，同时提供 API 与管理台页面，不引入新的 Node 运行时。
2. **统一配置存储**：新增统一文件配置层，模型配置与策略配置都采用 JSON 文件存储、临时文件写入 + 原子替换、生效版本 hash、按需热重载。
3. **统一模型字段**：模型配置统一为 `url` / `apiKey` / `model`，返回时始终脱敏 `apiKey`。
4. **策略调优最小闭环**：复用 `BacktestRunner` 做离线回放，支持读取现有策略参数、运行 replay、输出推荐参数，并将推荐结果写为新版本配置。
5. **前端实现方式**：管理台采用服务端输出的静态 HTML/CSS/JS，多页面路由由后端直接分发，前端直接消费现有 JSON API，不再额外设计 DTO 协议层。

---

## 里程碑

| 里程碑 | 状态 | 目标 | 验收标准 |
|---|---|---|---|
| M0 计划落地与任务同步 | done | 生成本计划文件并同步 MCP 任务 | 计划文件存在于 `.codex/plans/current/`，MCP 任务已创建 |
| M1 运行时基础与鉴权 | done | 引入会话认证、统一配置存储、API 路由基座 | `/api/auth/*` 可用；配置文件支持原子写入与热更新 |
| M2 报表与监控页面闭环 | done | 提供登录页、今日报告页、单基金页、监控区和静态页面路由 | 页面可访问；报告/监控接口与页面联动正常 |
| M3 模型配置中心 | done | 提供模型配置 CRUD、默认项、脱敏返回、连接测试 | 模型配置支持列表/新增/更新/设默认/连通性测试 |
| M4 策略配置与离线调优 | done | 提供策略配置 CRUD、启停、默认项、版本回滚、热更新、离线 replay/tune | 策略参数可配置；可运行 replay 并写入新版本 |
| M5 文档、验证、发布 | blocked | 更新验证脚本、README、API 文档、部署说明，并完成自测、提交推送 | 验证脚本通过；文档更新；提交并推送 `origin/main` |

状态字段仅允许：`todo` / `in_progress` / `done` / `blocked`。

---

## 步骤分解

### 步骤 1：运行时基座、认证与配置存储
- 状态：done
- 目标：在不破坏现有接口的前提下，为 `report_api` 增加可扩展路由、Cookie 会话认证、统一 JSON 配置存储与脱敏能力。
- 涉及文件：
  - `apps/api/report_api.py` — 重构为薄入口并接入新路由
  - `services/config/*` — 新建配置存储/脱敏/原子写入模块
  - `config/model_providers.json` — 新建模型配置文件
  - `config/strategy_profiles.json` — 新建策略配置文件
- 具体操作：
  1. 抽象请求解析、JSON 响应、静态页面响应、Cookie 会话校验。
  2. 新增认证接口 `/api/auth/login`、`/api/auth/logout`、`/api/auth/session`。
  3. 新增统一配置存储层，支持 version/hash、mtime 检查、force reload、原子写入、历史版本保留。
  4. 明确敏感字段脱敏规则：响应层永远不返回原始 `apiKey`。
- 验证方法：
  - `POST /api/auth/login` 成功写入 Cookie。
  - 未登录访问受保护页面/接口返回 401 或重定向。
  - 配置写入后再次读取返回新版本号且原始文件完整。

### 步骤 2：管理台页面与报表/监控闭环
- 状态：done
- 目标：提供登录页、今日报告页、单基金报告页、全局导航与数据链路状态展示区。
- 涉及文件：
  - `apps/web/static/*` 或等价静态资源目录 — 新建页面与脚本样式
  - `apps/api/report_api.py` — 新增页面路由与静态资源分发
  - `apps/web/src/pages/*.tsx` — 保持原型文件存在，必要时更新说明或兼容内容
- 具体操作：
  1. 实现 `/login`、`/dashboard/today`、`/fund/{symbol}` 页面。
  2. 提供统一布局、导航、错误提示、加载态。
  3. 报告页接入一键生成今日报告、读取最近报告、导出入口。
  4. 页面接入 `/api/monitor/data-sources` 并展示来源健康、告警、熔断状态。
- 验证方法：
  - 浏览器访问页面可正常加载。
  - 日报页可触发生成并展示返回结果。
  - 单基金页可查询并展示评分、新闻、回测与证据。

### 步骤 3：模型配置中心与连接测试
- 状态：done
- 目标：交付统一字段 `url/apiKey/model` 的模型配置页与后端 API，支持列表、新增、更新、设默认、连接测试。
- 涉及文件：
  - `services/config/*` — 模型配置管理
  - `services/llm/*` 或等价模块 — 连接测试与 provider 适配
  - `apps/api/report_api.py` — `/api/settings/model*` 路由
  - `apps/web/static/*` — 模型配置页交互
- 具体操作：
  1. 定义模型配置对象、默认项、启停状态、版本字段。
  2. 返回数据时脱敏 `apiKey`，编辑时支持“保留原值”模式。
  3. 实现连接测试，覆盖连通性、鉴权、模型可用性三项结果。
  4. 支持设置默认模型并立即热更新生效。
- 验证方法：
  - 新增、更新、设默认接口可用。
  - 连接测试接口可区分网络失败、鉴权失败、模型不存在。
  - 页面可展示掩码后的 key、默认状态和测试结果。

### 步骤 4：策略配置、版本回滚、热更新与离线调优
- 状态：done
- 目标：交付策略配置页与后端能力，支持参数/权重/启停/默认项/版本回滚/热更新/离线 replay/tune。
- 涉及文件：
  - `services/strategy/*` — 策略实例工厂、参数化、调优逻辑
  - `services/backtest/runner.py` — 复用或小幅扩展 replay 输出
  - `services/reporting/daily_report_service.py` — 读取配置化策略实例
  - `apps/api/report_api.py` — `/api/settings/strategy*` 路由
  - `apps/web/static/*` — 策略配置页交互
- 具体操作：
  1. 将现有 `ScoreThresholdStrategy`、`ScoreMomentumStrategy` 接入配置工厂。
  2. 策略配置文件支持版本历史、启停、默认策略集、热更新。
  3. 提供离线 replay/tune 接口：读取历史数据回放、比较策略表现、生成推荐参数并可写回新版本。
  4. 提供版本回滚接口，将历史版本恢复为当前生效版本。
- 验证方法：
  - 策略列表/新增/更新/启停/设默认/回滚/热更新接口可用。
  - replay/tune 可返回 ranking、推荐参数与新版本号。
  - 日报与单基金详情使用的策略结果可反映最新配置版本。

### 步骤 5：文档、验证、提交与推送
- 状态：blocked
- 目标：补齐验证脚本、README、API 文档、部署说明，并完成自测、提交与推送。
- 涉及文件：
  - `scripts/check_api_runtime.py`
  - 新增或更新验证脚本（模型配置/策略配置/页面可用性）
  - `README.md`
  - `docs/api/API_SUMMARY.zh-CN.md`
  - `docs/api/openapi.yaml`
  - `docs/plan/` 或 `docs/product/` 下相关说明文档
- 具体操作：
  1. 扩展 API smoke test，覆盖 auth、settings-model、settings-strategy、monitor 增量字段。
  2. 如需本地 mock，增加最小测试辅助逻辑，保证连接测试可自动验证。
  3. 更新 README 与 docs，说明页面、API、部署、配置文件与环境变量。
  4. 运行自测，整理变更文件列表、commit hash、验证摘要，并提交推送 `origin/main`。
- 验证方法：
  - 文档与实现一致。
  - 自测命令全部通过。
  - Git push 成功。

---

## 风险评估与回滚

| 风险 | 触发条件 | 影响 | 缓解措施 | 回滚方案 |
|---|---|---|---|---|
| API 入口复杂度显著上升 | `report_api.py` 同时承载 API 与页面 | 增加回归概率 | 将新增能力拆为内部模块，入口仅做路由编排 | 回退到上一个 `report_api.py` 版本，保留新模块但不挂路由 |
| 配置写入损坏 | 写入过程中异常或中断 | 模型/策略配置不可读 | 使用临时文件 + `replace` 原子替换，保存历史快照 | 恢复最近一个历史版本文件 |
| 模型连接测试依赖外网 | 网络不稳定或第三方限流 | 测试结果不稳定 | 测试接口区分网络/鉴权/模型结果，自测使用本地 mock server | 保留 CRUD，不阻断整体系统；连接测试作为独立接口降级 |
| 策略热更新影响日报链路 | 策略配置非法或不兼容 | 日报生成失败 | 写入前做结构校验，读取失败时退回最近可用版本 | 将当前策略版本回滚到上一个可用快照 |
| 新页面影响现有验证 | 原型页路径或文件结构变化 | `check_p6_reporting.py`/现有文档失败 | 保持原型文件存在，更新验证脚本兼容新页面 | 保留老页面文件并恢复静态分发变更 |
| 会话控制误伤现有接口 | 健康检查和公开导出被错误拦截 | 运行时 smoke test 失败 | 明确公开接口白名单：`/health`、登录页、必要静态资源 | 关闭鉴权钩子或仅保护管理台与配置接口 |

---

## 总体验收标准

- [x] 登录页可完成密码验证，`/api/auth/login`、`/api/auth/logout`、`/api/auth/session` 可用。
- [x] 今日量化报告页、单基金报告页、模型配置页、策略配置页、链路状态展示区可在当前运行时访问并使用。
- [x] 模型配置统一字段为 `url/apiKey/model`，支持列表/新增/更新/设默认/连接测试，且 `apiKey` 返回时脱敏。
- [x] 策略配置支持参数/权重/启停/默认/版本回滚/热更新，且至少提供一次离线 replay 与参数更新机制。
- [x] 配置存储采用文件 + 原子写入 + 热更新，错误时可以恢复历史版本。
- [x] `monitor` 返回来源健康、告警、熔断与审计相关字段。
- [x] README、API 文档、部署说明、验证脚本均已更新。
- [x] 自测通过，且不破坏现有 `fund-api` 基本运行链路。
- [ ] 变更已提交到 `main` 并推送 `origin/main`。

---

## 执行记录

| 时间 | 操作 | 结果 |
|---|---|---|
| 2026-03-07T02:55:00+08:00 | 创建计划文档 | done |
| 2026-03-07T02:55:00+08:00 | 同步 MCP 任务 | done |
| 2026-03-07T03:20:00+08:00 | 完成运行时基座、认证、配置存储与管理台页面 | done |
| 2026-03-07T03:58:00+08:00 | 完成模型配置中心、策略配置中心、离线 replay/tune | done |
| 2026-03-07T04:00:00+08:00 | 完成 README / docs / OpenAPI / 验证脚本更新与发布收尾 | done |
| 2026-03-07T04:05:00+08:00 | 推送 `origin/main` 失败（SSH publickey） | blocked |

---

## 回退检查点

1. 若 M1 失败，保留现有 `/health`、`/api/report/*`、`/api/monitor/data-sources` 路由原行为并停止挂载新接口。
2. 若 M3 失败，模型配置中心可以暂时不可用，但不能影响日报、单基金和监控链路。
3. 若 M4 失败，默认退回现有两条内置策略参数，不阻断日报生成与基金详情查询。
4. 若 M5 中推送失败，保留本地 commit 与验证结果，单独说明远端阻塞原因。
