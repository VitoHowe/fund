# License Matrix

更新时间：2026-03-06  
范围：运行时依赖、核心参考仓库、可复用边界

## 1. 运行时依赖

| Component | License | Use Mode | Decision | Notes |
|---|---|---|---|---|
| requests | Apache-2.0 | Runtime dependency | ALLOW | 网络请求基础组件 |
| pandas | BSD-3-Clause | Runtime dependency | ALLOW | 数据处理 |
| akshare | MIT | Runtime dependency | ALLOW | 主力数据源适配器 |
| efinance | MIT | Runtime dependency | ALLOW | 备源数据适配器 |
| yfinance | Apache-2.0 | Runtime dependency | ALLOW | 国际市场补充源 |

## 2. 参考仓库与复用边界

| Component | License | Use Mode | Decision | Notes |
|---|---|---|---|---|
| Micro-sheep/efinance | MIT | API/思路参考 + 依赖调用 | ALLOW | 可商用，保留 notices |
| stockmcp/stock-data-mcp | MIT | 架构思路参考 | ALLOW_WITH_BOUNDARY | 仅参考熔断/降级设计，不作为运行时依赖 |
| akfamily/akshare | MIT | API 调用 | ALLOW | 主力接口来源 |
| ArvinLovegood/go-stock | Apache-2.0 | 架构参考 | ALLOW | 可复用架构思路 |
| ZhuLinsen/daily_stock_analysis | MIT | 流程思路参考 | ALLOW | 报告流程参考 |
| x2rr/funds | GPL-3.0 | 前端思路参考 | REFERENCE_ONLY | 禁止代码复制到本仓库 |
| Austin-Patrician/eastmoney | Custom/Non-commercial constraints | 接口行为研究 | REFERENCE_ONLY | 不直接复用代码 |
| oficcejo/tdx-api | Unknown | 协议思路参考 | REFERENCE_ONLY | 许可证未明确，禁止代码复制 |
| run-bigpig/jcp | Unknown | 架构思路参考 | REFERENCE_ONLY | 许可证未明确，禁止代码复制 |

## 3. 强制规则

1. `GPL-3.0` 与 `非商用` 许可项目仅可做思路参考，禁止代码复制或二次分发混入本仓库。
2. 许可证未明确（Unknown）项目按高风险处理，仅做概念参考。
3. 新增依赖必须更新本矩阵并经过 `scripts/check_p7_governance.py` 检查。
4. 若未来引入前端包管理依赖（`package.json`），必须补齐对应 license matrix 条目。

