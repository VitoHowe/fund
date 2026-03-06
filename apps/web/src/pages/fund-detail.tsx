import React, { useEffect, useState } from "react";

type DetailPayload = {
  symbol: string;
  report_id: string;
  detail: {
    symbol: string;
    name: string;
    scorecard: Record<string, any>;
    news_summary: Record<string, any>;
    backtest_summary: Record<string, any>;
    data_source_refs: string[];
    source_time_utc?: string;
  };
};

export default function FundDetailPage() {
  const [symbol, setSymbol] = useState("014943");
  const [payload, setPayload] = useState<DetailPayload | null>(null);
  const [error, setError] = useState("");

  const load = (target: string) => {
    fetch(`/api/report/fund-detail?symbol=${encodeURIComponent(target)}`)
      .then((res) => res.json())
      .then((data) => setPayload(data))
      .catch((err) => setError(String(err)));
  };

  useEffect(() => {
    load(symbol);
  }, []);

  return (
    <main
      style={{
        maxWidth: 1000,
        margin: "32px auto",
        padding: 24,
        background: "#ffffff",
        borderRadius: 16,
        boxShadow: "0 10px 36px rgba(15,23,42,0.08)",
        fontFamily: "Noto Sans SC, PingFang SC, Microsoft YaHei, sans-serif",
      }}
    >
      <h1 style={{ marginTop: 0 }}>基金量化详情</h1>
      <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
        <input value={symbol} onChange={(e) => setSymbol(e.target.value)} />
        <button onClick={() => load(symbol)}>查询</button>
      </div>
      {error ? <p>加载失败：{error}</p> : null}
      {!payload ? <p>加载中...</p> : null}
      {payload ? (
        <>
          <p>
            报告 ID: <code>{payload.report_id}</code>
          </p>
          <h2>
            {payload.detail.symbol} {payload.detail.name}
          </h2>
          <h3>评分快照</h3>
          <pre>{JSON.stringify(payload.detail.scorecard, null, 2)}</pre>
          <h3>新闻特征</h3>
          <pre>{JSON.stringify(payload.detail.news_summary, null, 2)}</pre>
          <h3>回测摘要</h3>
          <pre>{JSON.stringify(payload.detail.backtest_summary, null, 2)}</pre>
          <h3>证据来源</h3>
          <ul>
            {(payload.detail.data_source_refs || []).map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </>
      ) : null}
    </main>
  );
}

