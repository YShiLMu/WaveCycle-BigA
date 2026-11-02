> **打包说明**：本文件由 `01_知识库_knowledge/11_规则冲突裁决_rule_conflict_adjudication.md` 转换生成（仅编号与路径口径不同），**禁止直接修改，修改请改源**；维护性章节（转换规则、验收清单）不打包，完整版见 `01_知识库_knowledge/11_规则冲突裁决_rule_conflict_adjudication.md`。
>

# 规则冲突裁决（Rule Conflict Adjudication）——跨步骤知识

> **定位**：本文件是"规则冲突与形态边界归属"的**唯一权威裁决流程**。数浪（`references/workflow.md（第 2 步）`）、验证（`references/workflow.md（第 3 步）`）、更新（`references/workflow.md（第 5 步）`）遇到 Rule 与 Rule、Rule 与 Guideline、Guideline 与 Guideline 的冲突，或形态边界归属不清时，按本文裁决。它不属于任何一个工作流步骤（工作流 01–05 各承载本步骤执行细则），故属跨步骤知识。
>
> **只裁决、不重复条文**：本文只写"冲突怎么裁决、按什么顺序裁决"，不重复展开规则条文。条文唯一权威在 `references/rules.md`（R1–R35）与 `references/guidelines.md`（G1–G29）；形态结构细节见 `references/patterns.md（推动浪）`、`references/patterns.md（楔形）`、`references/patterns.md（调整浪）`、`references/patterns.md（三角形）`；数据问题按 `references/data.md` 处理，不进入本裁决流程。
>

## 1. 裁决总原则

- **优先级铁律：波浪 Rule > 道氏 > 江恩 ≈ 蜡烛图**。波浪规则是唯一有"硬性失效"逻辑的体系；道氏（references/dow.md）提供概率性方向先验；江恩（references/gann.md）灵活度最高、最易事后解释，只作验证层证据；蜡烛图（references/candlestick.md）提供 K 线转折/持续信号确认，与江恩同档、只作信号层证据。道氏、江恩与蜡烛图信号一律为 Guideline 级，永不否决数法、永不覆盖失效价位。
- **执行层信号不进入裁决**：蜡烛图执行规则（references/candlestick.md第 7 节：买点/卖点/形态止损/假突破/极性转换/背离佐证）只作用于交易执行时机与止损位，不参与本裁决流程、不改变任何数法与失效价位；其方向闸门与主要趋势一致性由 `references/checklists.md（蜡烛图）`（CS-10–CS-15）校验。
- **Rule 优先于 Guideline**：任一 Rule 违反即数法无效（references/rules.md R19）；Guideline 违反只降低概率，并在输出中说明理由（references/guidelines.md 前言）。Guideline 不得豁免 Rule——references/guidelines.md G20 只说明级别错标的概率影响，不豁免 references/rules.md R4 的嵌套自洽判定。
- **例外条款先验证条件、后适用例外**：例外条款必须先验证其适用条件，满足才可豁免基础规则。典型如重叠例外 references/rules.md R8–R11：先查楔形位置（references/rules.md R9/R10）与子浪结构，并按极端价位（references/rules.md R20）判定，全部满足才豁免 references/rules.md R7；条件不满足仍按 references/rules.md R7 判违反（references/rules.md R11）。
- **本文只写裁决方式**：条文与判定标准以 references/rules.md、references/guidelines.md 为唯一权威；本文不新增、不改写任何 Rule/Guideline，也不重复展开条文内容。

## 2. 冲突类型与处理

| 冲突类型 | 例子 | 裁决方式 |
| --- | --- | --- |
| Rule vs Rule 表面冲突 | references/rules.md R7 重叠 vs references/rules.md R8–R11 楔形例外 | 先验证例外条件：位置（references/rules.md R9/R10）、子浪结构、极端价位（references/rules.md R20）；条件不满足则按 references/rules.md R7 判违反（references/rules.md R11） |
| Rule vs Guideline | references/rules.md R4 嵌套自洽 vs references/guidelines.md G20 级别错标只降概率 | references/guidelines.md G20 不豁免 references/rules.md R4：嵌套自洽按 references/rules.md R4 判定；级别错标是否影响概率按 references/guidelines.md G20 单独说明 |
| Guideline vs Guideline | references/guidelines.md G1 交替 vs references/guidelines.md G23 位置偏好指向不同方案 | 不裁决合法性；按 references/guidelines.md G21 八因子计分排序（Guideline 命中数、结构完整度、斐波那契共振、道氏一致性、江恩价格共振、江恩时间共振、蜡烛图信号、失效价位距离） |
| 形态边界归属 | 双锯齿形 references/rules.md R13 vs 联合形 references/rules.md R16；三角形 references/rules.md R15/R27 vs 楔形 references/rules.md R9/R10 vs 平台形 references/rules.md R14/R28 | 按第 3 节裁决顺序执行 |
| 波浪 vs 道氏 | 数出末端浪（第 5 浪/C 浪）但道氏无 DO5 反转确认；道氏趋势状态与主方案方向矛盾 | 见第 2.1 节：降概率/强制主备互换评估，道氏永不否决数法 |
| 波浪 vs 江恩 | 江恩角度线支撑与失效价位矛盾；江恩时间窗与斐波那契时间目标不一致 | 见第 2.2 节：失效价位最高权威；双窗口披露、重叠才计分 |

### 2.1 波浪 vs 道氏的冲突场景

1. **末端浪 vs 道氏未确认**：波浪数出末端浪（第 5 浪、C 浪）但道氏未出现 DO5 反转确认（references/dow.md第 5 节）→ 主方案保留、概率降档，报告必须写明"结构看顶/底 vs 趋势未确认"的张力；禁止因道氏未确认而废弃数法，也禁止忽略张力直接给高置信结论；
2. **方向矛盾（最高级别冲突）**：道氏趋势状态与主方案数浪方向矛盾 → 强制触发主备方案互换评估，并要求大一级別数浪复核（references/dow.md第 7 节）；复核后仍矛盾的，两个方向各自成方案、独立失效价位、披露矛盾，禁止硬选唯一解（references/rules.md R24）。

### 2.2 波浪 vs 江恩的冲突场景

1. **价位矛盾**：江恩角度线/1/8 分割支撑位与波浪失效价位矛盾 → **失效价位是全场最高权威**（references/rules.md 第 6 节（规则失效价位）），江恩价位只作辅助确认，禁止因"江恩这里有支撑"而否定任何已违反的 Rule（references/gann.md第 1 节）；
2. **时间不一致**：江恩时间窗与斐波那契时间目标指向不同时点 → 两个窗口都在报告披露，只有重叠时才计时间共振分（references/guidelines.md G21）；禁止择一报喜、禁止事后挑选窗口（references/gann.md第 4 节预登记制度）。

### 2.3 道氏 vs 江恩的冲突场景与三理论矛盾的披露

1. **时间窗内猜转势 vs 道氏未确认**：江恩时间窗到了、价格也到共振区，但道氏无 DO5 结构确认 → 不认定转势，标注时间/价位已就位、趋势确认待定；禁止在时间窗里猜顶猜底（references/gann.md第 5 节）；
2. **江恩转弱信号 vs 道氏趋势延续**：价格跌破江恩 1×1 主轴（GN1 转弱信号）但道氏趋势状态未翻转 → 只降 G21 评分，不报道氏状态变更（状态翻转唯一触发是 DO5，references/defaults.md D22）；
3. **三理论两两矛盾的披露义务**：任意两个理论结论矛盾时，报告【4. 概率排序与理由】必须写明矛盾双方与采纳的裁决路径（本节第 2.1–2.3 节）。**只有"道氏方向与数浪矛盾"才标注 references/guidelines.md G26「背离」并触发 references/guidelines.md G27 强制观望**；江恩与波浪/道氏的矛盾按本节 2.2–2.3 的具体裁决处理（失效价位最高权威、双窗口披露、只降分），不触发仓位闸门。

## 3. 形态边界裁决顺序（固定流程）

1. **结构证据优先**：先按子浪计数判定形态身份——锯齿形 5-3-5（references/rules.md R12）、平台形 3-3-5（references/rules.md R14/R28）、三角形 3-3-3-3-3（references/rules.md R15/R27）、楔形（references/rules.md R9/R10）。子浪结构与数量是最高优先级证据；形态细节见 `references/patterns.md（推动浪）`、`references/patterns.md（楔形）`、`references/patterns.md（调整浪）`、`references/patterns.md（三角形）`。
2. **位置约束次之**：三角形不作第 2 浪独立形态（references/rules.md R15）、楔形位置限制（references/rules.md R9/R10）；位置偏好（references/guidelines.md G23）只作参考，不构成合法性判定。
3. **身份约束**：B/X/W/Y/Z 不得标为推动浪（references/rules.md R30）；X 浪必须是调整浪（references/rules.md R3）；方向身份须自洽（references/rules.md R25）。
4. **Guideline 计分**：前三步仍有多解时，按 references/guidelines.md G21 计分排序；排序不裁决合法性，只影响概率与仓位。
5. **仍无法裁决**：输出多重数浪——主备方案 + 各自独立失效价位 + 区分信号（references/rules.md R24）；禁止硬猜唯一解。

### 3.1 调整家族的证据分流

- 单一锯齿与双锯齿共用粗略起止点时，先查 A/C 的驱动组成还是 W/Y 的完整调整组成；不是只更换标签。
- 平台与三角形前段共用三段外观时，检查第三段的内部身份和是否结束；缺证不代表多个方案“均已合法”，有反例则立即排除对应划分。
- 两个锯齿按 R13/R16 归类；其他同型调整不能仅因 G16“通常不同”而触发硬性淘汰。
- D8 的项目量化变体边界与 R14 的结构组成分别记录；边界组合暂未归类时说明限制，不能强行指定另一个家族。
- 局部组成完成与父级整个调整完成分开判断；后续突破或多出两段都不能替代内部复核。几何观察线、规则边界和特定结构前提分别列明。

## 4. 引用点

- `references/workflow.md（第 2 步）`：枚举候选数法（第 3 节）遇到形态边界时，注明"按 `references/rule_conflicts.md` 第 3 节裁决"。
- `references/workflow.md（第 3 步）`：Rule 复核（第 3 节）发现冲突时，引用本文第 2、3 节。
- `references/workflow.md（第 5 步）`：形态切换决策（5.2 节）引用本文第 3 节。
- `assets/分析报告_report.md`【7. 风险提示】：需要说明歧义裁决依据时引用本文。
