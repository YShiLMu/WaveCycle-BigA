> **打包说明**：本文件由 「03_工作流_workflow/01_数据获取与市场分析准备」（源文件） 转换生成（2 代，`references/data.md`），**禁止直接修改，修改请改源**。
>

# 数据获取协议

## 一、标的识别与数据源路由（Routing & Protocols）

在分析启动阶段，必须首先对标的代码进行合规化解析，并根据标的类型路由到稳定可靠的外部接口。

### 1.1 标的代码规范化与前缀处理（D59）
为规避不同金融数据源之间的代码碰撞，所有标的必须经过代码标准化层：

| 标的资产大类 | 原始输入示例 | 标准化代码 | 交易所前缀规则与说明 |
| :--- | :---: | :---: | :--- |
| **A 股主板/科创板** | `600519` / `688981` | `sh600519` / `sh688981` | 上交所股票统一添加小写 `sh` 前缀 |
| **A 股深市/创业板** | `000001` / `300750` | `sz000001` / `sz300750` | 深交所股票统一添加小写 `sz` 前缀 |
| **北交所** | `835185` / `430047` | `bj835185` / `bj430047` | 北交所股票统一添加小写 `bj` 前缀 |
| **核心综合指数** | 上证指数 / 科创50 | `sh000001` / `sh000688` 或 `1A0001` / `1B0688` | 行情接口多用 `sh000001`；通达信/部分传统源映射为 `1A0001` |
| **ETF 基金** | `510050` / `159915` | `sh510050` / `sz159915` | 场内 ETF 依所属交易所添加 `sh` 或 `sz` 前缀 |
| **行业/概念板块** | 银行板块 / 半导体 | `881155`（同花顺）/ `BK0475`（东财） | 行业指数按数据源特定代码映射，必须声明编制机构 |
| **港股与美股** | 腾讯控股 / 苹果 | `hk00700` / `usAAPL` | 港股补齐 5 位代码加 `hk`；美股加 `us` 前缀 |

### 1.2 数据源高可用路由与降级链
在当前工业环境中，不同接口的稳定性与限制存在显著差异。流水线执行以下路由降级机制：

```
+----------------------------------------------------------------------------------------------------+
|                                    数据源路由与故障降级决策树                                       |
+----------------------------------------------------------------------------------------------------+
|  [ 日线/周线/月线 K 线 ]                                                                           |
|       |                                                                                            |
|       +--> 首选主源: 腾讯接口 (fqkline) ------------------------+ (支持全市场、自动前复权 QFQ)      |
|       |         | (若超时/网络受阻/被限流)                      |                                  |
|       |         v                                               |                                  |
|       +--> 备选次源: 同花顺 HTTP 接口 (d.10jqka) / 百度股市通    |                                  |
|       |         | (若缺失复权因子)                              |                                  |
|       |         v                                               |                                  |
|       +--> 兜底源: 新浪财经 HTTP 接口 (仅抓取原始未复权作为备考) |                                  |
|                                                                 v                                  |
|  [ 分钟 K 线 (60m/30m/15m) ]                                    |                                  |
|       |                                                         |                                  |
|       +--> 唯一全板块可用源: 腾讯接口 (mkline) -----------------+                                  |
|                 (单次请求上限 800 根; 必须校验返回长度, 警惕 >800 时静默截断为 320 根的严重陷阱!) |
+----------------------------------------------------------------------------------------------------+
```

#### 废弃接口严正声明
- **`mootdx` / 通达信 L1 离线/在线接口已完全作废**：因通达信第三方行情网关频繁断连、IP 封锁与列序协议不透明，严禁在自动化流水线中调用 `mootdx`。
- **东方财富、百度开放 API 分钟线缺陷**：实测东财、百度等接口对指数及 ETF 分钟线的支持存在大范围断流与时间戳错位，分钟分形层统一收敛至腾讯 `mkline`。

### 1.3 复权模式规范与基准披露三要素
在技术分析与波浪形态度量中，必须保证历史价格的几何连续性：
1. **复权口径（与线上 references/data.md 对齐）**：
   - **日线默认前复权（QFQ）**：报告全部价位即同花顺/东财前复权可见价位，与 `02_案例库` 既有口径一致，便于用户直接对照行情软件；腾讯 `fqkline` + 新浪因子链路可直接产出；
   - **可执行路径与可选后复权**：仅当用户显式要求后复权（HFQ）时，才须确保 a-stock-data 的复权因子完整、匹配且 `apply_adjust` 结果通过自检，否则拒绝而非静默降级，**禁止自行推算因子、禁止谎称 hfq**；
   - **不变式与漂移代价**：hfq 与 qfq 只差一个常数比例因子，形态、比例、时间关系完全相同，换口径不得据此推翻既有数浪；但除权后 qfq 历史价格整体漂移，更新报告时必须全量重算失效价位并在第 8 章登记；
   - **分钟层**：分钟分形层一律独立不复权（`none`，D42），与日线只做时间戳锚定，禁止跨周期混算价格。
2. **基准披露三要素**：在生成的《分析市场准备卡》与最终报告中，必须完整披露：
   $$\text{Benchmark} = \{\text{复权方式: hfq/qfq/none（实际值）}, \quad \text{数据源名称: 如腾讯 fqkline}, \quad \text{数据截至时间戳: YYYY-MM-DD HH:MM}\}$$
3. **口径漂移禁令**：同一标的的日线与分钟线必须分别登记各自复权口径；报告中不得只写"复权"而不注明 hfq/qfq/none。

---

### 1.4 分钟分形层切片协议（Minute Fractal Slicing，D42）

分钟分形层是**附加验证层**：不参与日线交付深度编号，是否启用由 Step 02 的「门禁 B」询问用户后决定（见 「02_数浪实战与多重候选推演」（源文件））。启用后唯一入口为 `scripts/minute_slice.py`，**三轮交互**，脚本只产出切片与摆动候选事实，浪级/形态/完成状态一律由模型裁决。

| 轮次 | 动作 | 脚本命令 | 产出与裁决 |
| :--- | :--- | :--- | :--- |
| 第 1 轮 | 日线深度完成，锁定活跃浪起点 `T_d0`（含 H/L 属性） | 无（模型裁决） | `T_d0` 日期 + 极值属性；写入候选 JSON 与询问记录 |
| 第 2 轮 | 切 60m | `minute_slice.py --freq 60 --anchor-date <T_d0> --anchor-kind H\|L`（可选 `--daily-csv` 做锚点日跨源核对） | 契约 CSV + 元数据 + 指标 sidecar + 分形 Pivot 候选；模型裁决 60m 当前子浪起点 `T_60m0`（精确到 bar 时间戳） |
| 第 3 轮 | 切 30m + 15m | `minute_slice.py --freq 30,15 --anchor-ts <T_60m0>` | 模型完成 30m/15m 分析，检验「日线最深层 — 60m — 30m — 15m」四级分形共振与蜡烛图确认 |

**固定口径（禁止自行改动）**：

1. **数据源**：分钟线唯一全板块可用源为腾讯 `mkline`；**固定按 800 根请求并校验返回根数**——>800 静默回退 320 根属高危陷阱，不足即报错重取。东财/百度分钟线存在断流与时间戳错位，禁用。
2. **bar 密度与保底**：60m=4 根/日、30m=8 根/日、15m=16 根/日；保底根数 60m=32、30m=24、15m=32（15m 窗口上限 64 根，起点取 30m 最新摆动段起点与最近 32 根的较早者）。
3. **前浪缓冲**：60m 左留 8 根、30m 左留 4 根作为前浪上下文，并在元数据标注“前浪上下文”。
4. **锚点对齐**：日级锚点用当日 `argmin(low)`／`argmax(high)` 排名定位（并列取最早）；跨源极值核对容差 0.5%，超差只披露不阻断。时间戳标 **bar 结束时刻**（60m=10:30/11:30/14:00/15:00）。
5. **复权隔离**：分钟线全源不复权（`none`），与日线（hfq/qfq）**只做时间戳锚定与结构映射，严禁跨周期混算价格**；分钟级斐波那契/江恩按本周期切片自身极值独立计算。报告数据基准须分别披露日/60m/30m/15m 四条数据链。
6. **指标**：MACD(12,26,9)／RSI(14)／MA(5,10,20,60) 在全量数据上先算后切片，只进 `*.indicators.csv` sidecar，**仅作动量衰竭/背离的辅助共振证据，禁入结构判定**。
7. **单次分析锁单一时源**；切片参数与锚点写入元数据，供复核复现。

---

## 二、行情数据拉取与前置质量校验（Preflight Check）

数据拉取后，严禁直接送入数浪算法，必须执行自动化的预检质检流水线。

### 2.1 自动化拉取与格式清洗脚本
数据抓取脚本必须无条件遵守 `00_系统工程规范`，在写入磁盘前完成列序重排与路径隔离：

> **可执行片段（唯一取数入口）**：常规 A 股日/周/月 K 线按下面的片段取数，**不需要加载 a-stock-data**；仅当需要非常用端点（研报、资金面、期权、公告、打板等）时才整篇加载它。分钟线走 §1.4 的 mkline 协议；其他市场以用户提供数据为准。

```python
"""最小可执行取数片段：A 股日/周/月 K 线（腾讯 fqkline）+ 复权（新浪因子）。

输出契约：<TEMP>/wavecycle/<symbol>_<freq>_<fq>.csv（date,open,high,low,close,volume）
         同名 .metadata.json（source/fq/as_of/timezone/csv_sha256）
可直接喂 data_check.py / preflight.py；周/月线改 freq="week"/"month"。
"""
import hashlib
import json
import os
import tempfile
from datetime import datetime

import pandas as pd
import requests

UA = {"User-Agent": "Mozilla/5.0"}
KLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
FACTOR_URL = "https://finance.sina.com.cn/realstock/company/{symbol}/{kind}.js"
PRICE_KEYS = ("open", "high", "low", "close")


def to_frame(rows):
    """腾讯列序是 date,open,close,high,low,volume —— 先重排为标准 OHLC 列序（D28）。"""
    df = pd.DataFrame(rows).iloc[:, :6]
    df.columns = ["date", "open", "close", "high", "low", "volume"]
    df["date"] = df["date"].astype(str).str[:10]
    for col in PRICE_KEYS + ("volume",):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df[["date", "open", "high", "low", "close", "volume"]]


def fetch_raw(symbol, freq="day", start="1990-01-01", end=None, pages=12):
    """腾讯 fqkline 不复权全历史：单请求上限 1300 根，按首根日期向前翻页。"""
    end = end or datetime.now().strftime("%Y-%m-%d")
    segs, cursor = [], end
    for _ in range(pages):
        r = requests.get(KLINE_URL, headers=UA, timeout=25,
                         params={"param": f"{symbol},{freq},{start},{cursor},1300,"})
        r.raise_for_status()
        rows = (r.json().get("data") or {}).get(symbol, {}).get(freq) or []
        if not rows:
            break
        segs.append(rows)
        if rows[0][0] <= start:
            break
        cursor = (pd.Timestamp(rows[0][0]) - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    if not segs:
        raise RuntimeError(f"腾讯 fqkline 无数据：{symbol}/{freq}")
    return (pd.concat([to_frame(s) for s in segs], ignore_index=True)
            .drop_duplicates("date").sort_values("date").reset_index(drop=True))


def sina_factor(symbol, kind):
    """新浪复权因子（kind=qfq|hfq，日期升序）；响应尾部挂 base64 注释，必须 raw_decode。"""
    url = FACTOR_URL.format(symbol=symbol, kind=kind)
    r = requests.get(url, timeout=15,
                     headers={"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn/"})
    r.raise_for_status()
    text = r.text
    data, _ = json.JSONDecoder().raw_decode(text[text.find("{"):])
    items = ({"date": it["d"], "factor": float(it["f"])} for it in data.get("data", []))
    return sorted(items, key=lambda x: x["date"])


def check_factors(hfq, qfq):
    """hfq 最早因子=1、qfq 最新因子=1、同日 hfq×qfq 恒定；任一不成立即降级 qfq 并披露。"""
    assert hfq and qfq, "复权因子为空"
    assert hfq[0]["factor"] == 1.0, "hfq 最早因子不为 1.0"
    assert qfq[-1]["factor"] == 1.0, "qfq 最新因子不为 1.0"
    qfq_map = {x["date"]: x["factor"] for x in qfq}
    products = {round(x["factor"] * qfq_map[x["date"]], 9) for x in hfq if x["date"] in qfq_map}
    assert len(products) == 1, f"hfq×qfq 不恒定：{products}"


def apply_adjust(df, factors, kind):
    """hfq 乘因子、qfq 除因子（方向传反不报错，只会把价格整体放大/缩小数倍）。"""
    out, idx, cur = [], 0, None
    for row in df.to_dict("records"):
        while idx < len(factors) and factors[idx]["date"] <= row["date"]:
            cur = factors[idx]["factor"]
            idx += 1
        if cur is None:
            raise ValueError(f"{row['date']} 无复权因子")
        for key in PRICE_KEYS:
            row[key] = round(row[key] * cur, 4) if kind == "hfq" else round(row[key] / cur, 4)
        out.append(row)
    return pd.DataFrame(out)


def factor_evidence(hfq, qfq, kind):
    """把因子链结论固化为 metadata 证据块，供 data_check 复验（不落因子全量）。"""
    qfq_map = {x["date"]: x["factor"] for x in qfq}
    products = {round(x["factor"] * qfq_map[x["date"]], 9)
                for x in hfq if x["date"] in qfq_map}
    payload = json.dumps({"hfq": hfq, "qfq": qfq}, ensure_ascii=False, sort_keys=True)
    return {"kind": kind, "factor_source": "sina",
            "hfq_first": hfq[0]["factor"], "qfq_last": qfq[-1]["factor"],
            "product_constant": len(products) == 1,
            "factor_sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest()}


def write_csv(df, symbol, freq, fq, source, adjust=None):
    """落盘 %TEMP% + 同名 metadata；csv_sha256 缺失时 data_check 拒绝作为正式数据链。"""
    assert (df["high"] >= df[["open", "close", "low"]].max(axis=1)).all(), "high 非最高"
    assert (df["low"] <= df[["open", "close", "high"]].min(axis=1)).all(), "low 非最低"
    out_dir = os.path.join(tempfile.gettempdir(), "wavecycle")
    os.makedirs(out_dir, exist_ok=True)
    csv_path = os.path.join(out_dir, f"{symbol}_{freq}_{fq}.csv")
    df.to_csv(csv_path, index=False, lineterminator="\n")
    with open(csv_path, "rb") as fh:
        digest = hashlib.sha256(fh.read()).hexdigest()
    meta = {"source": source, "fq": fq, "as_of": f"{df['date'].iloc[-1]} 15:00",
            "timezone": "Asia/Shanghai", "csv_sha256": digest}
    if adjust is not None:
        meta["adjust"] = adjust
    with open(os.path.splitext(csv_path)[0] + ".metadata.json", "w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=2)
    return csv_path


def main(symbol="sh603259", freq="day", fq="qfq"):
    raw = fetch_raw(symbol, freq)
    if fq == "none":
        return write_csv(raw, symbol, freq, fq, "腾讯 fqkline", {"kind": "none"})
    hfq, qfq = sina_factor(symbol, "hfq"), sina_factor(symbol, "qfq")
    check_factors(hfq, qfq)
    evidence = factor_evidence(hfq, qfq, fq)
    adjusted = apply_adjust(raw, hfq if fq == "hfq" else qfq, fq)
    return write_csv(adjusted, symbol, freq, fq, "腾讯 fqkline + 新浪因子", evidence)
```

拿到返回的 CSV 路径后，依次跑 「data_check」（源文件）（带 `--fq` 与 `--require-metadata`）和 「preflight」（源文件）。复权口径只能取 `hfq`／`qfq`／`none` 三者之一，并在报告【1 分析前提】如实披露。

metadata 的 `adjust` 块是复权证据（kind、因子边界、hfq×qfq 乘积恒定、因子 SHA-256）。「data_check」（源文件） 对 `qfq` 允许"声明未验证"并披露；对 `hfq` 无 `adjust` 块或校验失败直接判不通过，禁止以声明代替验证。

### 2.2 运行 「data_check」（源文件） 质量守门
执行质检脚本，验证 CSV 列序契约与元信息完整性：
```bash
python 06_技能_skill/scripts/data_check.py --csv "<标准化CSV绝对路径>" --source "<数据源>" --fq qfq --require-metadata
```
- **检查内容**：首行表头精准度、是否存在空行/NaN/无穷大值、交易日期是否单调严格递增、是否有重复日期。
- **熔断处理**：若返回状态码非 0，必须停止流水线并输出错误日志，排查数据源污染，严禁带病运行。

### 2.3 运行 「preflight」（源文件） 提取行情全景摘要
通过预检集成脚本提取关键摘要：
```bash
python 06_技能_skill/scripts/preflight.py --csv "<标准化CSV绝对路径>" --metadata "<同stem.metadata.json>" --require-metadata
```
「preflight」（源文件） 自动在终端打印并输出以下结构化内容：
1. **行情全局基本面**：数据起点日期、终点日期、总 K 线根数、历史最高点（含日期）、历史最低点（含日期）、最新收盘价。
2. **道氏趋势状态（D22 / D30）**：自动分析最近的 3 个波峰与 3 个波谷，**3 点判、2 点定**——牛市 = 更高的高点 + 更高的低点；熊市 = 更低的高点 + 更低的低点；其余为结构冲突，按震荡处理并披露张力。第 3 点仅作一致性校验。
3. **尾部摆动点分布（D40）**：默认截断输出最近 40 个摆动极值点（索引、日期、价格、多空性质），为后续细分提供微观骨架。
