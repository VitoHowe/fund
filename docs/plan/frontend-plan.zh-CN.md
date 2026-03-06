# 前端实施规划

## 1. 规划目标

基于当前仓库已经存在的运行时接口和前端原型页，规划一个可落地的前端方案，覆盖：

- 模型配置中心（Gemini / OpenAI / 自定义 OpenAI 兼容）
- 单基金分析报告页
- 一键生成今日基金量化报告
- 报告页展示全链路数据源状态
- 登录页（密码验证）
- 配置热更新方案（前后端）
- 接口增补清单与里程碑（M1-M4）

当前基线：

- 已有 API 入口：`apps/api/report_api.py`
- 已有前端原型页：`apps/web/src/pages/etf-report.tsx`、`apps/web/src/pages/fund-detail.tsx`
- 已有可复用后端能力：日报生成、单基金详情、监控快照、Prometheus 指标、权重热重载基础实现

## 2. 现状判断

### 2.1 已具备能力

1. `GET /api/report/daily` 可同步生成日报。
2. `GET /api/report/fund-detail` 可返回单基金详情。
3. `GET /api/monitor/data-sources` 可返回全链路数据源状态。
4. `WeightTemplateManager` 已具备基于文件变更时间和 `force_reload` 的热更新模式。

### 2.2 当前缺口

1. 没有登录页，也没有密码验证与会话接口。
2. 没有模型配置中心，不能管理 Gemini/OpenAI/兼容网关。
3. 报表接口仍是同步直出，缺少“生成任务”和“最近一次今日报告”读取接口。
4. `apps/web` 仅有页面原型，没有完整应用壳、路由、鉴权和统一状态管理。
5. OpenAPI 还没有覆盖报表接口和未来配置接口。

## 3. 前端信息架构

建议将前端收敛为一个受登录保护的管理台，路由如下：

| 路由 | 页面 | 目标用户 | 核心能力 |
|---|---|---|---|
| `/login` | 登录页 | 管理员/研究员 | 密码登录、会话校验、错误提示 |
| `/dashboard/today` | 今日基金量化报告 | 研究员 | 一键生成、查看最新日报、导出、监控状态 |
| `/fund/:symbol` | 单基金分析报告页 | 研究员 | 查看单基金评分、新闻、回测、证据链 |
| `/settings/models` | 模型配置中心 | 管理员 | 配置 Gemini/OpenAI/兼容模型、测试连接、切换默认模型 |
| `/settings/runtime` | 运行时配置中心 | 管理员 | 查看配置版本、热更新状态、执行 reload |

## 4. 页面规划

### 4.1 登录页（密码验证）

目标：用最小成本先把匿名访问收口，保护报表、配置和监控接口。

页面组件建议：

- 品牌区：平台名称、当前环境、免责声明
- 登录表单：密码输入框、显示/隐藏密码、提交按钮
- 会话状态：登录失败原因、剩余锁定时间（如有限流）

交互规则：

1. 首屏调用 `GET /api/auth/session` 判断是否已登录。
2. 未登录则展示表单；登录成功后跳转 `/dashboard/today`。
3. 登录失败显示通用错误文案，不泄露密码策略。
4. 会话失效后自动返回登录页。

最小安全方案：

- 后端持有 `FUND_ADMIN_PASSWORD_HASH`
- 使用 HttpOnly + SameSite Cookie 维护会话
- 登录接口增加简单限流和失败次数控制

### 4.2 今日基金量化报告页

目标：让用户一键生成和查看“今日报告”，同时看到生成链路是否可靠。

页面模块建议：

1. 顶部工具栏：日期、市场状态选择、基金代码输入、生成按钮、导出按钮
2. 概览卡片：`symbol_count`、`avg_score`、`bullish_ratio`、`low_confidence_ratio`
3. 排行榜表格：`ranking`
4. 板块资金流榜：`sector_ranking`
5. 风险提示区：`risk_alerts`
6. 审计证据区：`evidence`
7. 数据源状态区：展示 `/api/monitor/data-sources`

“一键生成今日基金量化报告”建议：

- 首版允许直接同步调用并回显
- 当生成时间变长时，再平滑升级为异步任务模式

### 4.3 单基金分析报告页

目标：围绕一个基金代码输出“可解释分析卡”，优先服务于研究和复盘。

页面模块建议：

1. 查询区：基金代码、快捷切换、最近查询历史
2. 基金头图：名称、代码、总分、置信度、风险标签
3. 因子分解：`scorecard.factor_scores`
4. 新闻因子摘要：`news_summary`
5. 回测摘要：`backtest_summary`
6. 证据链：`data_source_refs`、`source_time_utc`
7. 关联数据源状态：只高亮本页涉及数据源

### 4.4 模型配置中心

目标：集中管理 LLM 提供商配置，为后续“报告总结增强”“自然语言问答”“策略解释生成”等能力预留入口。

配置对象建议统一为：

| 字段 | 说明 |
|---|---|
| `provider_id` | 唯一标识 |
| `provider_type` | `gemini` / `openai` / `openai_compatible` |
| `name` | 展示名称 |
| `base_url` | API 基地址 |
| `api_key_masked` | 仅回显脱敏值 |
| `model` | 默认模型名 |
| `enabled` | 是否启用 |
| `is_default` | 是否默认模型 |
| `timeout_seconds` | 请求超时 |
| `max_retries` | 重试次数 |
| `extra_headers` | 自定义请求头 |

页面功能建议：

1. 列表展示全部模型配置
2. 新增/编辑/启用/停用/设为默认
3. 测试连通性
4. 查看配置版本与最后更新时间
5. 执行配置热更新

提供商预设：

- Gemini：只展示 Gemini 相关字段与默认 base URL
- OpenAI：只展示 OpenAI 官方字段
- 自定义 OpenAI 兼容：允许填写任意 `base_url`

## 5. 报告页中的全链路数据源状态展示

日报页与单基金页都应接入 `GET /api/monitor/data-sources`，但展示深度不同：

- 日报页：展示整体状态、所有源健康表、当前告警、Prometheus 链接
- 单基金页：展示与当前基金分析相关的源摘要和告警

前端建议映射字段：

| 后端字段 | 前端展示 |
|---|---|
| `overall_status` | 顶部状态灯：`healthy` / `warning` / `critical` |
| `source_count` | 数据源数量 |
| `sources[].enabled` | 启用状态标签 |
| `sources[].failure_count` | 总失败次数 |
| `sources[].consecutive_failures` | 连续失败次数 |
| `sources[].avg_latency_ms` | 平均延迟 |
| `sources[].circuit_open_until` | 熔断恢复时间 |
| `alerts[]` | 告警列表 |
| `sources[].cache_metrics` | 缓存命中/未命中 |

## 6. 配置热更新方案

### 6.1 后端方案

现有 `WeightTemplateManager` 已经证明了“配置文件 + mtime 检查 + force reload”可行，建议复用到模型配置和运行时配置：

1. 新增 `config/model_providers.yaml`
2. 新增 `services/config/runtime_config.py`，提供统一读取、版本哈希、原子写入、强制 reload
3. 配置更新流程：
   - 前端提交变更
   - 后端先校验字段
   - 使用临时文件写入，再原子替换
   - 更新配置版本号/哈希
   - 返回最新版本与生效时间
4. 所有读取方按“懒加载 + 版本缓存”使用配置
5. 对敏感字段仅存储原值，返回前脱敏

建议区分两类配置：

- 热更新立即生效：模型提供商、默认模型、请求超时、开关项
- 需重启生效：服务监听地址、进程级别线程数、底层 SDK 初始化项

### 6.2 前端方案

前端不直接缓存密钥原文，只缓存配置版本与脱敏字段。

建议机制：

1. 应用启动时读取 `/api/config/runtime`
2. 管理台保存配置成功后立即刷新对应 Query
3. 通过轮询或 SSE 感知 `config_version`
4. 当版本变化时提示“配置已更新，可刷新当前页”

优先级建议：

- M1-M2：轮询即可
- M3-M4：如配置改动频繁，再升级到 SSE

## 7. 接口增补清单

### 7.1 鉴权接口

| Method | 路径 | 用途 |
|---|---|---|
| `POST` | `/api/auth/login` | 密码登录，写入会话 Cookie |
| `POST` | `/api/auth/logout` | 注销当前会话 |
| `GET` | `/api/auth/session` | 查询当前登录态 |

### 7.2 报表接口增补

| Method | 路径 | 用途 |
|---|---|---|
| `POST` | `/api/report/daily/generate` | 显式触发生成今日报告 |
| `GET` | `/api/report/daily/latest` | 获取最近一次今日报告 |
| `GET` | `/api/report/{report_id}` | 按报告 ID 查询结果 |
| `GET` | `/api/report/{report_id}/export` | 基于报告 ID 导出文件 |

说明：

- M1 可继续复用现有 `GET /api/report/daily`
- 进入 M2 后建议拆成“生成”和“读取”两个语义更清晰的接口

### 7.3 模型配置接口

| Method | 路径 | 用途 |
|---|---|---|
| `GET` | `/api/settings/model-providers` | 查询模型配置列表（脱敏） |
| `POST` | `/api/settings/model-providers` | 新增模型配置 |
| `PUT` | `/api/settings/model-providers/{provider_id}` | 更新模型配置 |
| `POST` | `/api/settings/model-providers/{provider_id}/validate` | 测试连通性 |
| `POST` | `/api/settings/model-providers/{provider_id}/set-default` | 设为默认模型 |
| `POST` | `/api/settings/reload` | 触发热更新 |
| `GET` | `/api/config/runtime` | 查询运行时配置版本与状态 |

### 7.4 监控与审计接口增补

| Method | 路径 | 用途 |
|---|---|---|
| `GET` | `/api/monitor/data-sources` | 已有，直接复用 |
| `GET` | `/api/monitor/audit-events` | 展示最近源切换与告警事件 |
| `GET` | `/api/monitor/metrics-link` | 返回 Prometheus/Grafana 跳转信息 |

## 8. 里程碑

### M1：前端基线与登录

目标：

- 补齐 `apps/web` 应用壳、路由与基础布局
- 完成登录页和登录态守卫
- 接入现有日报/单基金查询接口

交付物：

- `/login`
- `/dashboard/today`
- `/fund/:symbol`
- `POST /api/auth/login`
- `GET /api/auth/session`
- `POST /api/auth/logout`

### M2：日报产品化

目标：

- 支持一键生成今日报告
- 支持查看最近一次报告与导出
- 报告页完整展示数据源状态

交付物：

- `POST /api/report/daily/generate`
- `GET /api/report/daily/latest`
- `GET /api/report/{report_id}`
- `GET /api/report/{report_id}/export`
- 报告页状态灯、告警区、审计证据区

### M3：模型配置中心与热更新

目标：

- 完成 Gemini/OpenAI/自定义兼容模型配置中心
- 完成配置校验和热更新闭环

交付物：

- `/settings/models`
- `/settings/runtime`
- 模型配置 CRUD
- 配置版本展示
- 热更新按钮与生效提示

### M4：可观测性与体验完善

目标：

- 增加监控审计页面和事件追踪
- 优化大报告加载体验、错误边界、空状态和导出链路

交付物：

- `/monitor` 或在 `/dashboard/today` 内扩展高级监控区
- `/api/monitor/audit-events`
- 更完整的导出状态管理、失败重试与回退提示

## 9. 实施建议

1. 先不引入过重的权限体系，密码登录 + 会话 Cookie 足够支撑 MVP。
2. 报表生成初期保留同步接口，等耗时明显增长后再演进为异步任务。
3. 模型配置中心必须从第一天就做“脱敏返回”和“原子写入”，否则后续补救成本更高。
4. OpenAPI 需要同步补齐到报表接口与新增配置接口，否则前后端联调成本会持续偏高。
5. 页面实现应直接复用当前返回结构，不要在前端再造一层字段映射协议。

## 10. 与当前仓库的对应关系

| 当前文件 | 可复用点 |
|---|---|
| `apps/api/report_api.py` | 现有报表与监控接口基础 |
| `services/reporting/daily_report_service.py` | 日报/单基金详情聚合逻辑 |
| `services/reporting/template_engine.py` | 导出结构、报告字段定义 |
| `services/observability/source_monitor.py` | 数据源状态与告警结构 |
| `services/factor_engine/scoring.py` | 配置热更新基础模式 |
| `apps/web/src/pages/etf-report.tsx` | 日报页原型 |
| `apps/web/src/pages/fund-detail.tsx` | 单基金页原型 |
