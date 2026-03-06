# 领域模型与数据字典

## 核心对象

## FundQuote
- `symbol: string` 基金代码
- `name: string | null` 基金名称
- `unit_nav: number | null` 单位净值
- `daily_change_pct: number | null` 日涨跌幅
- `source: string` 数据源标识
- `source_time: string | null` 源数据时间
- `ingest_time: string` 接入时间

## FundNavSeries
- `symbol: string`
- `records: Array<{date, unit_nav, acc_nav, daily_change_pct}>`
- `source: string`
- `source_time: string | null`
- `stale: boolean`

## FundFlow
- `symbol: string`
- `records: Array<{sector, main_net_inflow, main_inflow_ratio, top_stock}>`
- `source: string`
- `ingest_time: string`

## NewsItem
- `title: string`
- `content: string | null`
- `time: string | null`
- `source: string`
- `url: string | null`

## FactorSnapshot
- `symbol: string`
- `factor_name: string`
- `value: number`
- `weight: number`
- `as_of: string`
- `calc_version: string`

## SignalDecision
- `symbol: string`
- `action: "buy" | "sell" | "hold"`
- `confidence: number`
- `evidence: string[]`
- `risk_flags: string[]`
- `generated_at: string`

## 统一返回包装（NormalizedEnvelope）
- `metric: "realtime" | "history" | "news" | "flow"`
- `symbol: string`
- `source: string`
- `source_time: string | null`
- `records: object[]`
- `quality_score: number`
- `stale: boolean`
- `ingest_time: string`
- `metadata: object`

