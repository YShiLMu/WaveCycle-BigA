# 🌊 观复（WaveCycle）· 技术分析融合版

> 万物并作，吾以观复。——《道德经》

一个面向 **A 股** 的 Codex / ZCode Skill：**以 Elliott Wave（艾略特波浪理论）数浪为主框架**，叠加道氏理论（趋势前提）、江恩理论（时间/价位验证）与蜡烛图（K 线信号确认）交叉验证。

**一句话概括它能做什么：**

- 🧭 **定级别**：任何分析先声明波浪级别（Degree），不谈级别的数浪无效
- 🔀 **数浪**：主方案 + 替代方案，48 条硬规则 + 42 条准则双层裁决
- 🎯 **标失效**：每个方案独立失效价位，失效价位是最高权威
- 📊 **出报告**：八因子概率排序 + 共振状态标注，输出 Markdown + 自包含网页报告

**目录：** [🚀 快速开始](#-快速开始) · [📄 输出物](#-输出物) · [📖 Skill 内容介绍](#-skill-内容介绍) · [📁 项目结构](#-项目结构) · [🙏 致谢](#-致谢) · [⚖️ 免责声明](#-免责声明)

---

## 🚀 快速开始

> [!IMPORTANT]
> **硬性要求，缺一不可，装错了技能直接跑不起来。**
>
> 1. **必须安装 Python 3.10 或 3.11**。其他版本（3.9 及更早、3.12 及以上）未经验证，可能因第三方依赖装不上而跑不起来。
> 2. **必须安装三个库：`pandas`、`matplotlib` 与 `requests`**。分析脚本（锚点检测、绘图、校验）依赖前两者；A 股内置取数协议（腾讯行情接口 + 新浪复权因子）依赖 requests。缺任何一个都会直接报错。
> 3. **A 股取数已内置，无需 mootdx／通达信**（通达信第三方网关已实测作废并禁用）：日/周/月 K 线走腾讯 `fqkline`（自动前复权）+ 新浪复权因子，分钟线走腾讯 `mkline`，板块指数走同花顺 `d.10jqka`。仅在需要研报／资金面／期权／公告等**非常用端点**时才选装 [`a-stock-data`](https://github.com/simonlin1212/a-stock-data) skill。**不想联网也可以**——在同花顺日线页面按 **F1** 导出数据（或直接截图）交给技能即可。分析非 A 股市场（美股、港股、期货、加密货币等）由用户直接提供数据或图表。

### 第 1 步 · 装必装环境

[![Python](https://img.shields.io/badge/Python-3.10%20%7C%203.11-blue?style=flat-square&logo=python&logoColor=white)](https://www.python.org/downloads/) [![pandas](https://img.shields.io/badge/pandas-必装-blue?style=flat-square&logo=pandas&logoColor=white)](https://pypi.org/project/pandas/) [![matplotlib](https://img.shields.io/badge/matplotlib-必装-blue?style=flat-square&logo=matplotlib&logoColor=white)](https://pypi.org/project/matplotlib/) ![Market](https://img.shields.io/badge/Market-A股-red?style=flat-square) ![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)

```bash
pip install pandas matplotlib requests
```

<details>
<summary>💡 没装过 Python？点这里</summary>

- 未装 Python 时从官网下载：https://www.python.org/downloads/ （Windows 安装时务必勾选 "Add Python to PATH"）
- 装完可自检：`python --version` 与 `python -c "import pandas, matplotlib"`

</details>

### 第 2 步 · 安装技能

**方式一：把一句话发给 AI（推荐 ✅）**——不需要碰命令行。打开 ZCode / Codex / DSH 任一客户端，新建对话，把下面这句话原样发给它：

```text
帮我安装这个技能：https://github.com/YShiLMu/WaveCycle-BigA
```

AI 会克隆仓库并放到本地技能目录（`~/.agents/skills/wavecycle`）。装完**重启客户端**，再发一句确认是否生效：

```text
列出你当前可用的技能，看看有没有 wavecycle
```

**方式二：手动安装**

```bash
git clone https://github.com/YShiLMu/WaveCycle-BigA.git wavecycle
cp -r wavecycle ~/.agents/skills/    # 通用技能目录；ZCode 亦识别 ~/.zcode/skills/，Codex 识别 ~/.codex/skills/
# 重启客户端
```

### 第 3 步 · 开始使用

标的换成任意股票名称或代码都行，**非 A 股直接附上图表**：

```text
分析一下贵州茅台的走势
```

技能会自动接管：定级别 → 数浪 → 主备方案校验 → 标失效价位 → 出报告，中途需要确认的地方（如交付深度）会主动问你。

---

## 📄 输出物

每次分析交付两份文档（归档到 `分析输出/<标的>_<代码>_<时间>/`）：

| 文件 | 内容 |
|---|---|
| **分析报告.md** | 8 章节——分析前提（含道氏趋势状态）、主方案、替代方案（各含道氏背景、江恩共振与蜡烛图信号）、八因子概率排序与理由（含共振状态表）、失效价位清单、交易计划、风险提示、更新与跟踪 |
| **网页报告.html** | 同一内容的快捷查看版，主备方案图标签页切换，图片自包含 |

---

## 📖 Skill 内容介绍

### 四层分工

| 层 | 理论 | 管什么 | 角色 |
|---|---|---|---|
| **前提层** | 道氏理论 | 能不能做 | 用高低点结构与指数互证判定趋势状态（牛市/熊市/震荡），作为数浪的方向先验 |
| **主框架** | 波浪理论 | 做到哪一步 | 结构、数浪、级别与失效价位 |
| **验证层** | 江恩理论 | 什么时候到 | 角度线、1/8 分割、时间窗只做目标测算与共振加分 |
| **信号层** | 蜡烛图 | 转折是否确认 | K 线信号（反转/持续）做数浪方向与关键位的交叉确认 |

分析结果按**八因子概率排序**给主备方案打分：**Guideline 得分 ×2（有符号原始累计整数：命中 +1／不适用 0／违反 −1，允许为负）** + 结构完整度 + 斐波那契共振 + 道氏趋势一致性 + 江恩价格共振 + 江恩时间共振 + 蜡烛图信号 + 失效价位距离（权重 2:1:1:1:1:1:1:1；后七项按 0/1/2 打分；不输出伪精确的百分比），并标注**共振状态**：🔴 背离强制观望、🟡 单信号谨慎、🟠 双共振升一档、🟢 三共振再升一档。

### 铁律

> [!WARNING]
> **优先级铁律：波浪 Rule > 几何连线 > 道氏 > 江恩 ≈ 蜡烛图**（唯一定义见 `references/rule_conflicts.md` §3.1）。道氏、江恩、蜡烛图一律是 Guideline 级证据，**永不否决数法、永不覆盖失效价位**。共振时出手、背离时观望——这是本 Skill 的核心纪律。

- **先定级别再数浪**：不谈级别的数浪无效；
- **失效价位最高权威**：任何理论（包括江恩）不得覆盖失效价位；
- **概率表述有边界**：只说"大概率/倾向于/通常"，禁止"必然/一定/绝对"；
- **预期必须标注**：未发生的走势如实标为预期，禁止编造已完成的结构。

底层机制：48 条硬规则 + 42 条准则双层裁决（Rule 违反即数法无效，Guideline 违反只降概率）+ EG-01~EG-08 工程门禁机审；江恩固定时间窗（30/60/90/144/180/360 天 + 周年日）预登记，禁止事后挑窗；A 股指数互证——主板配上证指数、创业板（300）配创业板指、科创板（688）配科创指数，各叠加板块指数；标准分析必给主备双方案，各自独立失效价位，仅豁免条件成立时才允许单方案并披露。

---

## 📁 项目结构

```
├── SKILL.md                  # 技能入口与核心流程
├── agents/openai.yaml        # Agent 配置
├── references/
│   ├── rules.md              # 48 条 Elliott 硬性规则（R 系列，唯一裁决权威）
│   ├── guidelines.md         # 42 条指导准则（G 系列）
│   ├── dow.md                # 道氏理论（趋势判定、指数互证口径）
│   ├── gann.md               # 江恩理论（角度线、时间窗、共振判定）
│   ├── candlestick.md        # 蜡烛图（反转/持续信号、关键位确认）
│   ├── channeling_fib.md     # 通道与交替原则
│   ├── fibonacci.md          # 斐波那契比率目标与空间共振
│   ├── short_term_sr.md      # 短期支撑压力（N 级）
│   ├── multiframe_resonance.md # 多周期共振（N 星）
│   ├── checklists.md         # 校验清单与 EG-01~EG-08 双轨门禁
│   ├── workflow.md           # 分析工作流
│   └── patterns.md / terminology.md / defaults.md / data.md / rule_conflicts.md / tool_discipline.md
├── assets/                   # 报告、网页报告、复盘、失效追踪、交易计划模板
└── scripts/                  # 26 个脚本：取数校验、数浪、评分、绘图、出报告、归档
    ├── ew_chart.py           # K 线 + 浪型标注绘图（--gann 叠加江恩角度线）
    ├── score.py              # 八因子概率排序
    ├── rule_check.py         # R 系列硬规则机审
    └── embed_report_images.py # 图片 base64 内嵌
```

---

## 🙏 致谢

[`a-stock-data`](https://github.com/simonlin1212/a-stock-data) —— 作者 Simon 林（[@linsizhen](https://x.com/linsizhen)）。本技能 A 股**常规取数**已内置（腾讯行情接口 + 新浪复权因子 + 同花顺板块指数），仅研报／资金面／期权／公告等**非常用端点**会调用 a-stock-data。感谢开源。

理论框架：Frost & Prechter《Elliott Wave Principle: Key to Market Behavior》（第 10 版，2005，Wiley）；道氏理论（Dow/Hamilton/Rhea 体系）；江恩理论（W.D. Gann 体系）；蜡烛图（Steve Nison《日本蜡烛图技术》）。

---

## ⚖️ 免责声明

> [!CAUTION]
> 本 Skill 仅用于技术分析研究与学习，**所有输出不构成投资建议**。市场有风险，决策需独立。