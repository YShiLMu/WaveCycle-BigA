> **打包说明**：本文件由 `01_知识库_knowledge/16_功率评级_power_ratings.md` 转换生成（仅编号与路径口径不同），**禁止直接修改，修改请改源**；维护性章节不打包，完整版见源文件。
>

# 功率评级（Power Ratings）—— Neely 修正浪量化评级

> 来源：《Mastering Elliott Wave: Presenting the Neely Method》ch10「Advanced Logic Rules —— Retracement Based on Power Ratings」。
> 定位：给各种**修正浪（Correction）**一个静态功率评级（`+3 … 0 … -3`），用来预测该修正被下一形态回撤的比例。这是对现有 8 因子概率排序（D12/D25）的**独立量化对照件**——**不并入 8 因子权重**（2:1:1:1:1:1:1:1 原样保留），仅在波浪层内部作参考。

## 1. 概念

- **Power Rating（功率评级）**表示某修正浪形态对趋势延续的**有利 / 不利程度**。
- 正评级（`+1…+3`）= 该形态对趋势延续有利（向上完成时更强）；负评级（`-1…-3`）= 不利（更弱）。
- 排序规则（ch10）：正评级里**离中性越远越强**；负评级里**离中性越远越弱**。

## 2. 完整评级表（ch10）

按「向上完成 / 向下完成」两种方向给出各修正浪的评级。三角形内部分变体例外归 0（表中标注）。

| # | 修正浪（Correction） | 向上完成 | 向下完成 |
|---|---|---|---|
| 1 | Triple Zigzag（三重锯齿） | +3 | -3 |
| 2 | Triple Combination（三重联合） | +3 | -3 |
| 3 | Triple Flat（三重平台） | +3 | -3 |
| 4 | Double Zigzag（双重锯齿） | +2 | -2 |
| 5 | Double Combination（双重联合） | +2 | -2 |
| 6 | Double Flat（双重平台） | +2 | -2 |
| 7 | Elongated Zigzag（延伸锯齿） | +1 | -1 |
| 8 | Elongated Flat（延伸平台） | +1 | -1 |
| 9 | Zigzag（锯齿） | +1 | -1 |
| 10 | B-Failure（B 浪失败） | 0 | 0 |
| 11 | Common（普通） | 0 | 0 |
| 12 | C-Failure（C 浪失败） | 0 | 0 |
| 13 | Irregular（不规则） | -1 | +1 |
| 14 | Irregular Failure（不规则失败） | -1 | +1 |
| 15 | Double Three（双重三浪） | -2 | +2 |
| 16 | Triple Three（三重三浪） | -2 | +2 |
| 17 | Running Correction（奔走修正） | -2 | +2 |
| 18 | Double Three, Running（奔走双重三浪） | -3 | +3 |
| 19 | Triple Three, Running（奔走三重三浪） | -3 | +3 |

> 注：第 7–9 项（Elongated Zigzag / Elongated Flat / Zigzag）书中注明"在三角形内部分变体评级归 0"。表格原始数据由书 ch10 表格整理，个别 Triangle 例外以原文为准。

## 3. 回撤预测规则（ch10，核心）

Power Rating → 该修正被**下一完成形态**回撤的预期比例：

- `(0)`：允许约 **100%** 回撤（可被完全回撤）。
- `(+1,-1)`：下一完成形态回撤 **不超过约 90%**。
- `(+2,-2)`：**不超过约 80%**。
- `(+3,-3)`：回撤最少，约 **60–70%**。

**核心原则**：`+1 到 +3` 的向上完成修正浪**不应**被下一同级形态完全回撤（书："Any formation which concludes upward and has a +1 to +3 rating should not be fully retraced by the next pattern (of the same Degree)"）；绝对值越高，越不可能被完全回撤。

## 4. 应用规则

- 只有在**完整压缩（Compaction）所有下方形态**后，该 Power Rating 才可靠；取**已完成的最大形态**的评级（更小形态不重要）。
- **例外判断**：若一个 `±(1–3)` 形态被**更接近 0 但同级**的形态**完全回撤** → 市场正在酝酿 **Triangle（三角形）或 Terminal（终结形态）**（各变体：Expanding / Contracting，第 1 / 3 / 5 浪延长）。

## 5. 与现有 8 因子的关系

- **独立参考**，**不并入** D12 / D25 的 `2:1:1:1:1:1:1:1` 权重（08 权重仍跨波浪+道氏+江恩+蜡烛图）。
- 用途：给波浪层概率排序一个**硬量化参照**——同一主备方案下，可用 Power Rating 对照"失败距离"/"回撤深度"维度，辅助选主方案。
