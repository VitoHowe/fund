"""Report template models and renderers."""

from __future__ import annotations

import html
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class RankingItem:
    symbol: str
    name: str
    tier: str
    total_score: float
    confidence: float
    tactical_action: str
    tactical_reason: str
    risk_tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SectorRankingItem:
    sector: str
    change_pct: float
    main_net_inflow: float
    main_inflow_ratio: float
    top_stock: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class FundDetail:
    symbol: str
    name: str
    scorecard: dict[str, Any]
    news_summary: dict[str, Any]
    backtest_summary: dict[str, Any]
    data_source_refs: list[str]
    source_time_utc: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class DailyReport:
    report_id: str
    report_date: str
    generated_at_utc: str
    market_summary: dict[str, Any]
    tactical_brief: list[str]
    ranking: list[RankingItem]
    sector_ranking: list[SectorRankingItem]
    fund_details: list[FundDetail]
    risk_alerts: list[str]
    evidence: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "report_date": self.report_date,
            "generated_at_utc": self.generated_at_utc,
            "market_summary": self.market_summary,
            "tactical_brief": self.tactical_brief,
            "ranking": [item.to_dict() for item in self.ranking],
            "sector_ranking": [item.to_dict() for item in self.sector_ranking],
            "fund_details": [item.to_dict() for item in self.fund_details],
            "risk_alerts": self.risk_alerts,
            "evidence": self.evidence,
        }


class ReportTemplateEngine:
    """Render report objects to markdown/html/pdf bytes."""

    def render_markdown(self, report: DailyReport) -> str:
        lines: list[str] = []
        lines.append(f"# ETF 日报 {report.report_date}")
        lines.append("")
        lines.append(f"- 报告 ID：`{report.report_id}`")
        lines.append(f"- 生成时间（UTC）：`{report.generated_at_utc}`")
        lines.append("")
        lines.append("## 市场摘要")
        lines.append("")
        lines.append(f"- 覆盖标的数：{report.market_summary.get('symbol_count', 0)}")
        lines.append(f"- 平均评分：{report.market_summary.get('avg_score', 0.0)}")
        lines.append(f"- 多头占比：{report.market_summary.get('bullish_ratio', 0.0)}")
        lines.append(f"- 低置信占比：{report.market_summary.get('low_confidence_ratio', 0.0)}")
        lines.append("")
        lines.append("## 战术指令")
        lines.append("")
        for item in report.tactical_brief:
            lines.append(f"- {item}")
        lines.append("")
        lines.append("## 分级榜单")
        lines.append("")
        lines.append("| Symbol | Name | Tier | Score | Conf | Action | Reason | Risks |")
        lines.append("|---|---|---:|---:|---:|---|---|---|")
        for row in report.ranking:
            lines.append(
                f"| {row.symbol} | {row.name} | {row.tier} | {row.total_score:.2f} | "
                f"{row.confidence:.2f} | {row.tactical_action} | {row.tactical_reason} | "
                f"{','.join(row.risk_tags) or '-'} |"
            )
        lines.append("")
        lines.append("## 板块榜单")
        lines.append("")
        lines.append("| Sector | Change% | Main Inflow | Inflow Ratio% | Top Stock |")
        lines.append("|---|---:|---:|---:|---|")
        for row in report.sector_ranking:
            lines.append(
                f"| {row.sector} | {row.change_pct:.2f} | {row.main_net_inflow:.2f} | "
                f"{row.main_inflow_ratio:.2f} | {row.top_stock or '-'} |"
            )
        lines.append("")
        lines.append("## 个基详情")
        lines.append("")
        for detail in report.fund_details:
            lines.append(f"### {detail.symbol} {detail.name}")
            lines.append("")
            lines.append(
                f"- 总分：{detail.scorecard.get('total_score', 0.0)} "
                f"(conf={detail.scorecard.get('confidence', 0.0)})"
            )
            lines.append(f"- 新闻摘要：{detail.news_summary}")
            lines.append(f"- 回测摘要：{detail.backtest_summary}")
            lines.append(f"- 证据来源：{', '.join(detail.data_source_refs) or '-'}")
            lines.append(f"- 源时间（UTC）：{detail.source_time_utc or '-'}")
            lines.append("")
        lines.append("## 风险提示")
        lines.append("")
        for item in report.risk_alerts:
            lines.append(f"- {item}")
        lines.append("")
        lines.append("## 审计信息")
        lines.append("")
        lines.append(f"```json\n{_to_pretty_json(report.evidence)}\n```")
        lines.append("")
        return "\n".join(lines)

    def render_html(self, report: DailyReport) -> str:
        md = self.render_markdown(report)
        # Lightweight markdown-to-html conversion for this project.
        html_body = self._simple_markdown_to_html(md)
        return (
            "<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'/>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'/>"
            "<title>ETF 日报</title>"
            "<style>"
            "body{font-family:'Noto Sans SC','PingFang SC','Microsoft YaHei',sans-serif;"
            "line-height:1.6;margin:24px;background:#f6f8fb;color:#0f172a;}"
            "main{max-width:1080px;margin:0 auto;background:#fff;border-radius:16px;padding:28px;"
            "box-shadow:0 12px 40px rgba(15,23,42,.08);}"
            "h1,h2,h3{margin-top:1.2em;color:#0b3a6f;}table{width:100%;border-collapse:collapse;"
            "margin:12px 0;}th,td{border:1px solid #dbe3ef;padding:8px 10px;font-size:14px;}"
            "th{background:#eef4ff;}code,pre{background:#0b1220;color:#d6e4ff;border-radius:8px;}"
            "code{padding:2px 6px;}pre{padding:12px;overflow:auto;}ul{padding-left:22px;}"
            "</style></head><body><main>"
            f"{html_body}</main></body></html>"
        )

    def render_pdf_bytes(self, report: DailyReport) -> bytes:
        # Simple single-page text PDF builder to avoid external dependencies.
        plain = self.render_markdown(report)
        plain = re.sub(r"[^\x20-\x7E\n]", " ", plain)
        lines = plain.splitlines()
        max_lines = 48
        lines = lines[:max_lines]
        escaped_lines = []
        for line in lines:
            line = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            escaped_lines.append(line[:105])
        content_lines = ["BT", "/F1 10 Tf", "50 790 Td", "12 TL"]
        if escaped_lines:
            content_lines.append(f"({escaped_lines[0]}) Tj")
            for line in escaped_lines[1:]:
                content_lines.append(f"T* ({line}) Tj")
        content_lines.append("ET")
        stream_data = "\n".join(content_lines).encode("latin-1", errors="ignore")

        objects: list[bytes] = []
        objects.append(b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n")
        objects.append(b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n")
        objects.append(
            b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj\n"
        )
        objects.append(b"4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n")
        objects.append(
            b"5 0 obj << /Length "
            + str(len(stream_data)).encode("ascii")
            + b" >> stream\n"
            + stream_data
            + b"\nendstream endobj\n"
        )

        output = bytearray(b"%PDF-1.4\n")
        offsets = [0]
        for obj in objects:
            offsets.append(len(output))
            output.extend(obj)
        xref_pos = len(output)
        output.extend(f"xref\n0 {len(offsets)}\n".encode("ascii"))
        output.extend(b"0000000000 65535 f \n")
        for offset in offsets[1:]:
            output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
        output.extend(
            (
                f"trailer << /Size {len(offsets)} /Root 1 0 R >>\n"
                f"startxref\n{xref_pos}\n%%EOF\n"
            ).encode("ascii")
        )
        return bytes(output)

    def _simple_markdown_to_html(self, text: str) -> str:
        lines = text.splitlines()
        out: list[str] = []
        in_ul = False
        in_pre = False
        in_table = False
        for raw in lines:
            line = raw.rstrip()
            if line.startswith("```"):
                if in_pre:
                    out.append("</pre>")
                    in_pre = False
                else:
                    out.append("<pre>")
                    in_pre = True
                continue
            if in_pre:
                out.append(html.escape(line))
                continue
            if line.startswith("### "):
                if in_ul:
                    out.append("</ul>")
                    in_ul = False
                if in_table:
                    out.append("</tbody></table>")
                    in_table = False
                out.append(f"<h3>{html.escape(line[4:])}</h3>")
                continue
            if line.startswith("## "):
                if in_ul:
                    out.append("</ul>")
                    in_ul = False
                if in_table:
                    out.append("</tbody></table>")
                    in_table = False
                out.append(f"<h2>{html.escape(line[3:])}</h2>")
                continue
            if line.startswith("# "):
                if in_ul:
                    out.append("</ul>")
                    in_ul = False
                if in_table:
                    out.append("</tbody></table>")
                    in_table = False
                out.append(f"<h1>{html.escape(line[2:])}</h1>")
                continue
            if line.startswith("|") and line.endswith("|"):
                cells = [html.escape(item.strip()) for item in line.strip("|").split("|")]
                if all(re.fullmatch(r"-+", cell) for cell in cells):
                    continue
                if not in_table:
                    out.append("<table><tbody>")
                    in_table = True
                tag = "th" if "Symbol" in line or "Sector" in line else "td"
                out.append("<tr>" + "".join(f"<{tag}>{cell}</{tag}>" for cell in cells) + "</tr>")
                continue
            if line.startswith("- "):
                if not in_ul:
                    out.append("<ul>")
                    in_ul = True
                out.append(f"<li>{html.escape(line[2:])}</li>")
                continue
            if line.strip() == "":
                if in_ul:
                    out.append("</ul>")
                    in_ul = False
                if in_table:
                    out.append("</tbody></table>")
                    in_table = False
                continue
            out.append(f"<p>{html.escape(line)}</p>")
        if in_ul:
            out.append("</ul>")
        if in_table:
            out.append("</tbody></table>")
        if in_pre:
            out.append("</pre>")
        return "".join(out)


def _to_pretty_json(value: dict[str, Any]) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, indent=2, default=str)

