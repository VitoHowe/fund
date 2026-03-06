# 新闻/财经/政策链路验收记录（2026-03-05）

- 验收目标：确认“新闻资讯、财经信息、政策信号”是否可稳定获取并可进入量化分析。
- 验收时间：2026-03-05 13:00 ~ 14:10（Asia/Shanghai）

## 1. 可用链路（已实测）

### 1.1 stock-data-mcp（本地 HTTP 直连）
- 服务：`uvx stock-data-mcp --http --port 8808`，版本 `0.2.4`
- `stock_news_global`：可用，返回 `新浪 + NewsNow` 快讯流。
- `stock_news(symbol='014943'/'159870')`：可用，可返回基金/ETF 关联报道。
- `data_source_status`：可用，展示 `Efinance/Akshare/Baostock/Yfinance` 状态。

### 1.2 AkShare 新闻与宏观接口
- `stock_info_global_cls()`：可用，返回 20 条财联社快讯（盘中事件流）。
- `stock_news_em(symbol='600519')`：可用，返回 10 条东方财富新闻。
- `news_economic_baidu(date='20260305')`：可用，返回 81 条财经日历事件。
- `news_cctv(date='20260304')`：可用，返回 14 条新闻联播文本（政策语义强）。

### 1.3 官方政策/监管来源（网页可达性）
- 中国证监会首页 `http://www.csrc.gov.cn/`：可访问，可抽取“新闻发布会/市场快报”链接。
- 中国政府网最新政策页 `https://www.gov.cn/zhengce/zuixin/`：可访问（静态页）。
- 中国政府网政策库页 `https://www.gov.cn/zhengce/zhengceku/`：本次直连返回 `403`（需要浏览器仿真/备用抓取）。

## 2. 本轮异常与处理

- `stock_realtime`（stock-data-mcp）本轮对 `600519/ETF` 返回 `Not Found`：
  - 处理：盘中价格链路优先改为 `AkShare + Eastmoney raw` 双通道。
- `stock_sector_fund_flow_rank`（stock-data-mcp）本轮失败：
  - 处理：板块资金流改为直接使用 `AkShare stock_sector_fund_flow_rank`（已验证可用）。

## 3. 对 ETF 复盘的落地意义

- 盘后“全市场榜单”已具备三类核心输入：
  1. 全基金/ETF 排名与区间表现（AkShare）
  2. 板块资金流排名（AkShare）
  3. 新闻/政策事件流（stock-data-mcp + AkShare + 官方站点）
- 政策敏感基金的评分可加入“事件冲击分”：
  - 事件权重（监管/部委/媒体）
  - 时效衰减（T+0/T+1~T+5）
  - 跨源一致性（至少 2 源）

## 4. 结论

- 新闻、财经、政策三类数据已确认“可获取、可入模、可追溯”，不是停留在接口可调用层。
- 下一步需要把“事件抓取 + 去重 + 时效 + 证据留档”实现为统一流水线并接入复盘榜单。
