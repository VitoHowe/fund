# 管理台运行说明

## 1. 页面总览

当前运行时管理台由 `apps/api/report_api.py` 直接分发静态 HTML/CSS/JS，不依赖额外的 Node 前端服务。

页面路由：

| 路由 | 说明 | 核心能力 |
|---|---|---|
| `/login` | 登录页 | 密码验证、会话建立 |
| `/dashboard/today` | 今日量化报告页 | 一键生成、读取最近报告、导出、数据链路状态 |
| `/fund/{symbol}` | 单基金报告页 | 评分、新闻、回测、证据链 |
| `/settings/models` | 模型配置页 | 统一字段 `url/apiKey/model`、新增/更新/设默认/启停/连接测试 |
| `/settings/strategy` | 策略配置页 | 参数、权重、启停、版本回滚、热更新、离线 replay/tune |

## 2. 认证说明

认证为最小可用方案：

1. 登录接口：`POST /api/auth/login`
2. 会话接口：`GET /api/auth/session`
3. 注销接口：`POST /api/auth/logout`
4. 会话介质：HttpOnly + SameSite Cookie

默认开发密码为 `fund-admin`。生产环境必须通过以下环境变量覆盖：

- `FUND_ADMIN_PASSWORD`
- `FUND_ADMIN_PASSWORD_HASH`

如果提供 `FUND_ADMIN_PASSWORD_HASH`，应为 `sha256` 十六进制字符串。

## 3. 配置文件

### 3.1 模型配置

文件：`config/model_providers.json`

核心字段：

- `url`
- `apiKey`
- `model`
- `enabled`
- `is_default`

返回到前端时，`apiKey` 会被脱敏；原始值只保存在文件内部。

### 3.2 策略配置

文件：`config/strategy_profiles.json`

核心字段：

- `strategy_type`
- `params`
- `weight`
- `enabled`
- `is_default`
- `profile_version`
- `history`

策略更新会生成新版本，支持版本回滚；离线 replay/tune 支持把推荐参数直接写回新版本。

## 4. 热更新机制

模型配置和策略配置统一采用：

1. 文件存储
2. 版本号 + 哈希
3. 临时文件写入
4. 原子替换
5. 运行时按需 reload

显式热更新接口：

- `POST /api/settings/models/reload`
- `POST /api/settings/strategies/reload`

## 5. 部署步骤

```bash
python -m pip install -e .
python apps/api/report_api.py
```

启动后访问：

- `http://127.0.0.1:8010/login`

## 6. 最小验证

```bash
python scripts/check_api_runtime.py
python scripts/check_p6_reporting.py
```

`check_api_runtime.py` 会覆盖：

1. 公共运行时接口
2. 登录/会话
3. 管理台静态页面与资源
4. 模型配置 CRUD 与连接测试
5. 策略配置读取与 replay/tune
6. 最新日报读取与注销
