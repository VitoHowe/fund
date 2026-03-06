# 014943 数据源验收记录（2026-03-05）

- 验收对象：`014943`（鹏华中证细分化工产业主题 ETF 联接 C）
- 验收目标：验证“可获取 + 可分析 + 可交叉校验”，而不是仅验证接口通断
- 验收时间：2026-03-05 12:52 ~ 13:03（Asia/Shanghai）

## 1. Eastmoney

### 1.1 `FundMNFInfo`（App 风格）
- 请求方式：`GET + data`（移动端头模板）
- 结果：可返回 1 条记录
- 关键字段：`NAV=1.0300`，`PDATE=2026-03-04`
- 限制：`GSZ/GSZZL/GZTIME` 为空，不可单独作为盘中估算源

### 1.2 `f10/lsjz`
- 请求：`https://api.fund.eastmoney.com/f10/lsjz?fundCode=014943&pageIndex=1&pageSize=10`
- 结果：10 行历史净值，`FSRQ=2026-03-04`，`DWJZ=1.0300`，`JZZZL=-1.44`
- 结论：历史净值主链路可用

### 1.3 `pingzhongdata/014943.js`
- 结果：脚本长度 156512，含 `Data_netWorthTrend`
- 最新样本：`y=1.03`，`equityReturn=-1.44`
- 结论：历史净值序列可用

## 2. AkShare

- 接口：`fund_open_fund_rank_em(symbol='全部')`
- 结果：命中 `014943`
- 关键字段：`日期=2026-03-04`，`单位净值=1.03`
- 结论：可作为净值主源之一

## 3. efinance

### 3.1 `fund.get_realtime_increase_rate('014943')`
- 结果：1 条记录
- 字段：`最新净值=1.03`，`最新净值公开日期=2026-03-04`
- 限制：`估算时间/估算涨跌幅` 为空

### 3.2 `fund.get_quote_history('014943')`
- 结果：969 行
- 最新行：`日期=2026-03-04`，`单位净值=1.03`，`涨跌幅=-1.44`

## 4. 跨源准确性

- Eastmoney vs AkShare：日期一致（2026-03-04），单位净值差值 `0.00`
- Eastmoney vs efinance：日期一致（2026-03-04），单位净值差值 `0.00`
- 结论：当前验收指标一致性通过（`100/100`）

## 5. stock-data-mcp 渠道实测

### 5.1 本地服务直连
- 启动方式：`uvx stock-data-mcp --http --port 8808`
- 服务信息：`stock-data-mcp 0.2.4`
- 调用方式：MCP HTTP（`initialize -> notifications/initialized -> tools/call`）

### 5.2 结果
- `data_source_status`：可用，返回 `Efinance/Akshare/Baostock/Yfinance` 状态
- `stock_news_global`：可用，返回 `新浪 + NewsNow` 快讯
- `search`：可用，可检索 `014943/159870` 相关资讯与基金记录
- `stock_prices`：可用（如 `600519`、`159870`）
- `stock_realtime`：本轮返回 `Not Found`（包含 `600519` 与 ETF 代码）
- `stock_sector_fund_flow_rank`：本轮失败（提示数据源暂不可用）

## 6. 关键约束与后续策略

- `014943` 是场外联接基金（`OF`），不具备盘口成交与买卖盘语义。
- 盘口与成交量类指标必须转到关联 ETF（如 `159870`）和板块资金流链路。
- 后续每个开发步骤必须附带同类证据记录（可获取性 + 准确性 + 新鲜度 + 降级结果）。
