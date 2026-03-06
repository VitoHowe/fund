import React, { useEffect, useMemo, useState } from "react";

type RankingRow = {
  symbol: string;
  name: string;
  tier: string;
  total_score: number;
  confidence: number;
  tactical_action: string;
  tactical_reason: string;
  risk_tags: string[];
};

type ReportPayload = {
  report_id: string;
  report_date: string;
  generated_at_utc: string;
  market_summary: Record<string, number>;
  tactical_brief: string[];
  ranking: RankingRow[];
};

export default function EtfReportPage() {
  const [payload, setPayload] = useState<ReportPayload | null>(null);
  const [error, setError] = useState<string>("");

  useEffect(() => {
    fetch("/api/report/daily?symbols=014943,159870&market_state=neutral")
      .then((res) => res.json())
      .then((data) => setPayload(data))
      .catch((err) => setError(String(err)));
  }, []);

  const rows = useMemo(() => payload?.ranking || [], [payload]);

  return (
    <main
      style={{
        maxWidth: 1100,
        margin: "32px auto",
        padding: 24,
        background: "#ffffff",
        borderRadius: 16,
        boxShadow: "0 10px 36px rgba(15,23,42,0.08)",
        fontFamily: "Noto Sans SC, PingFang SC, Microsoft YaHei, sans-serif",
      }}
    >
      <h1 style={{ marginTop: 0 }}>ETF 日报工作台</h1>
      {error ? <p>加载失败：{error}</p> : null}
      {!payload ? <p>加载中...</p> : null}
      {payload ? (
        <>
          <p>
            报告 ID: <code>{payload.report_id}</code>
          </p>
          <p>报告日期: {payload.report_date}</p>
          <section>
            <h2>市场摘要</h2>
            <ul>
              <li>覆盖标的: {payload.market_summary.symbol_count}</li>
              <li>平均评分: {payload.market_summary.avg_score}</li>
              <li>多头占比: {payload.market_summary.bullish_ratio}</li>
              <li>低置信占比: {payload.market_summary.low_confidence_ratio}</li>
            </ul>
          </section>
          <section>
            <h2>分级榜单</h2>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Name</th>
                  <th>Tier</th>
                  <th>Score</th>
                  <th>Conf</th>
                  <th>Action</th>
                  <th>Reason</th>
                  <th>Risk</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.symbol}>
                    <td>{row.symbol}</td>
                    <td>{row.name}</td>
                    <td>{row.tier}</td>
                    <td>{row.total_score.toFixed(2)}</td>
                    <td>{row.confidence.toFixed(2)}</td>
                    <td>{row.tactical_action}</td>
                    <td>{row.tactical_reason}</td>
                    <td>{row.risk_tags.join(", ") || "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </>
      ) : null}
    </main>
  );
}

