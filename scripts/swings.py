# -*- coding: utf-8 -*-
"""主要摆动点提取（分形 Pivot）——数浪与作图的确定性前置计算。

解决三类每次分析都要重写的临时脚本：
  1. 分形摆动点（局部极值 + 相邻同型去重 + H/L 交替化），输出日期/价位/类型/涨跌幅；
  2. CSV 行索引：ew_chart.py 的 --waves/--path/--pivot/--channel 全部按 CSV 行索引定位，
     本脚本直接输出索引，消除手工数行错位；
  3. 上证周线聚合（道氏"主要趋势"口径用周级别高低点），周线摆动回填到周内极端价
     所在交易日的日线索引，参数串可直接用于日线图。

另附 --fib：按起点到终点的方向计算回撤与延伸，消除手算比率。

用法：
  python swings.py --csv data/881133.csv --k 5 --start 2021-01-01
  python swings.py --csv data/881133.csv --start 2024-06-01 --chart-args --tail 8
  python swings.py --csv data/sh000001.csv --weekly --k 4
  python swings.py --csv data/881133.csv --fib "3148.56:5666.35:4234.12"

口径：
  - 摆动判定一律用含影线的最高/最低价（references/rules.md R20）；
  - 索引为 0 起、相对**原始 CSV**的行号（--start/--end 只过滤分析范围，不改变索引基准；
    --weekly 时另输出"周线序号"，但 --chart-args 始终给日线索引）；
  - 去重规则：相邻同型摆动保留更极端者；最终输出严格 H/L 交替。
"""
import argparse
import csv
import datetime
import sys

RETRACES = (0.236, 0.382, 0.5, 0.618, 0.786)
EXTENSIONS = (1.0, 1.272, 1.618, 2.0, 2.618)


def load_ohlc(path):
    """读 CSV（date,open,high,low,close[,volume]），# 开头注释行跳过。
    按表头列名映射列位置（列序无关，防列序错位时按位置错读）；缺必需列即报错。
    返回 (rows, has_volume)；rows 元素为 (date, o, h, l, c[, volume])。
    注：本函数为 swings 专用纯 csv 实现，是有意的例外而非遗漏——分工口径见
    ohlc_io.py 模块 docstring（swings 依赖 # 注释行跳过与「索引=CSV 数据行号」
    基准语义，不强行并入共享模块）。"""
    rows = []
    has_volume = None
    col = {}          # 列名(小写) -> CSV 列位置；读表头行建立
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.reader(f):
            if not r or r[0].lstrip().startswith("#"):
                continue
            if r[0].strip().lower() == "date":
                col = {name.strip().lower(): i for i, name in enumerate(r)}
                needed = {"date", "open", "high", "low", "close"}
                if not needed <= set(col):
                    raise SystemExit("[错误] 表头缺少必需列: %s（需 date,open,high,low,close）"
                                     % sorted(needed - set(col)))
                has_volume = "volume" in col
                continue
            row = (r[col["date"]].strip(),
                   float(r[col["open"]]), float(r[col["high"]]),
                   float(r[col["low"]]), float(r[col["close"]]))
            if has_volume:
                row = row + (float(r[col["volume"]]),)
            rows.append(row)
    if not rows:
        raise SystemExit("[错误] CSV 无数据行: %s" % path)
    return rows, bool(has_volume)


def normalize_date(d):
    """兼容 2026-08-28 / 20260828 两种日期写法 → YYYY-MM-DD。"""
    d = str(d).strip()
    if len(d) == 8 and d.isdigit():
        return "%s-%s-%s" % (d[:4], d[4:6], d[6:8])
    return d


def _normdate(x):
    """统一 20260828 / 2026-08-28 → date 对象（用于与 out 日期匹配，兼容 CSV YYYYMMDD 列）。"""
    s = str(x).strip()
    if len(s) == 8 and s.isdigit():
        return datetime.date(int(s[:4]), int(s[4:6]), int(s[6:8]))
    return datetime.date.fromisoformat(s)


def to_week_key(date_str):
    dt = datetime.date.fromisoformat(date_str)
    iso = dt.isocalendar()
    return (iso[0], iso[1])


def aggregate_weekly(rows):
    """日 K → 周 K（ISO 周）。返回 [(周末日, open, high, low, close, 周内各原始行号)]。"""
    buckets = []
    cur_key, cur = None, None
    for i, r in enumerate(rows):
        key = to_week_key(r[0])
        if key != cur_key:
            if cur is not None:
                buckets.append(cur)
            cur = [r[0], r[1], r[2], r[3], r[4], [i]]
            cur_key = key
        else:
            cur[2] = max(cur[2], r[2])
            cur[3] = min(cur[3], r[3])
            cur[4] = r[4]
            cur[5].append(i)
    if cur is not None:
        buckets.append(cur)
    return [(b[0], b[1], b[2], b[3], b[4], b[5]) for b in buckets]


def fractal_pivots(highs, lows, k):
    """分形 Pivot：±k 窗口内为极值即候选；相邻同型保留更极端；输出严格交替。"""
    cand = []
    n = len(highs)
    for i in range(k, n - k):
        if highs[i] >= max(highs[i - k:i + k + 1]):
            cand.append([i, highs[i], "H"])
        if lows[i] <= min(lows[i - k:i + k + 1]):
            cand.append([i, lows[i], "L"])
    cand.sort(key=lambda p: p[0])
    # 同一根 K 线同时为高低点极值时，按与前一个摆动交替的方向取舍
    dedup = []
    for p in cand:
        if dedup and dedup[-1][0] == p[0]:
            if dedup[-1][2] == p[2]:
                # 同点同型：保留更极端
                if (p[2] == "H" and p[1] > dedup[-1][1]) or \
                   (p[2] == "L" and p[1] < dedup[-1][1]):
                    dedup[-1] = p
            # 同点异型：都保留，交给下一步交替化
            else:
                dedup.append(p)
            continue
        if dedup and dedup[-1][2] == p[2]:
            if (p[2] == "H" and p[1] >= dedup[-1][1]) or \
               (p[2] == "L" and p[1] <= dedup[-1][1]):
                dedup[-1] = p
            continue
        dedup.append(p)
    # 交替化：同型相邻保留更极端（再跑一遍以防同点异型引入的新相邻）
    out = []
    for p in dedup:
        if out and out[-1][2] == p[2]:
            if (p[2] == "H" and p[1] >= out[-1][1]) or \
               (p[2] == "L" and p[1] <= out[-1][1]):
                out[-1] = p
        else:
            out.append(p)
    return out


def fmt_price(x):
    return ("%.3f" % x).rstrip("0").rstrip(".") if x == x else str(x)


def significant_filter(piv_seq):
    """D11 显著度筛（脚本侧代理口径）：入摆幅度 < 中位入摆幅度 × 0.382 的摆动剔除
    （分形 k 已保证时间跨度 ≥ k+1 根，"或跨度≥3 根"分支天然满足）。
    piv_seq: [(idx, date, price, kind), ...]，H/L 严格交替。返回同构列表。"""
    if len(piv_seq) < 4:
        return piv_seq
    amps = [abs(piv_seq[i][2] - piv_seq[i - 1][2]) for i in range(1, len(piv_seq))]
    amps_sorted = sorted(amps)
    m = len(amps_sorted)
    median = (amps_sorted[m // 2] if m % 2 else (amps_sorted[m // 2 - 1] + amps_sorted[m // 2]) / 2)
    if median <= 0:
        return piv_seq
    out = [piv_seq[0]]
    for i in range(1, len(piv_seq)):
        if abs(piv_seq[i][2] - piv_seq[i - 1][2]) >= median * 0.382:
            out.append(piv_seq[i])
    return out


def dow_state(dow_pivs, rows, has_volume):
    """道氏趋势状态（D30：3点判、2点定，第3点一致性校验）+ DO4 成交量事实。

    dow_pivs: D11 筛后的交替摆动序列；rows: 原始 OHLC（取近 20 根成交量）。
    返回 (状态行文本, 明细行文本列表)。"""
    highs = [p for p in dow_pivs if p[3] == "H"][-3:]
    lows = [p for p in dow_pivs if p[3] == "L"][-3:]

    def trend(seq):
        if len(seq) < 2:
            return None
        a, b = seq[-2][2], seq[-1][2]
        return "抬高" if b > a else "降低" if b < a else "持平"

    def fmt_seq(seq):
        return " > ".join("%s %s(%s)" % (p[3], fmt_price(p[2]), p[1]) for p in seq)

    lines = ["高点：%s" % (fmt_seq(highs) if highs else "（不足）"),
             "低点：%s" % (fmt_seq(lows) if lows else "（不足）")]
    th, tl = trend(highs), trend(lows)
    if len(highs) < 2 or len(lows) < 2:
        state = "摆动点不足（各侧至少需 2 个）——模型补判或扩大分析范围"
    elif th == "抬高" and tl == "抬高":
        state = "牛市（HH+HL）"
    elif th == "降低" and tl == "降低":
        state = "熊市（LH+LL）"
    else:
        state = "结构冲突（高%s、低%s）——模型按震荡处理并披露张力" % (th, tl)
    if len(highs) >= 3 and len(lows) >= 3 and state.startswith(("牛市", "熊市")):
        # 第 3 点一致性校验：倒数第 2→3 对的方向
        def prev_trend(seq):
            a, b = seq[-3][2], seq[-2][2]
            return "抬高" if b > a else "降低" if b < a else "持平"
        ph, pl = prev_trend(highs), prev_trend(lows)
        last = "抬高" if state.startswith("牛市") else "降低"
        if ph == last and pl == last:
            state += "；第 3 点同向"
        else:
            # 第 3 点方向不一致 = 只凭最近 3 高/3 低得出的"牛市/熊市"标签不牢靠，
            # 可能是次级折返被误当主要趋势（dow.md 第 4 节：道氏看主要趋势、次级折返不改状态）。
            # 降级标签，避免使用者在报告中把近期读数当趋势确认结论。
            base = state.split("；")[0]
            state = ("%s（疑似近期读数，可能为次级折返，非主要趋势确认）；"
                     "第 3 点方向（高%s、低%s）与最近 2 点不一致——结构未完全走出，"
                     "模型须按主要趋势（long-term）复核并披露张力" % (base, ph, pl))
    lines.append("状态：%s" % state)

    # DO4 成交量事实（近 20 根：上涨日均量 / 下跌日均量）
    if has_volume:
        seg = [r for r in rows if len(r) >= 6][-20:]
        if len(seg) >= 4:
            up, dn = [], []
            for prev_bar, bar in zip(seg, seg[1:]):
                if bar[4] > prev_bar[4]:
                    up.append(bar[5])
                elif bar[4] < prev_bar[4]:
                    dn.append(bar[5])
            if up and dn:
                up_mean, down_mean = sum(up) / len(up), sum(dn) / len(dn)
                if down_mean == 0:
                    lines.append("成交量：上涨日均量 %.3f；下跌日均量 %.3f；比值不可定义（分母为零）——不能据此确认量价互证（DO4）"
                                 % (up_mean, down_mean))
                else:
                    ratio = up_mean / down_mean
                    label = "涨放量跌缩量" if ratio > 1 else "涨缩量跌放量" if ratio < 1 else "涨跌均量相同"
                    lines.append("成交量：上涨日均量 %.3f；下跌日均量 %.3f；近 20 根上涨日均量/下跌日均量 = %.2f（%s）——与道氏状态是否互证由模型判定（DO4）"
                                 % (up_mean, down_mean, ratio, label))
            else:
                lines.append("成交量：近 20 根单边涨或跌，比值不可比——模型披露")
        else:
            lines.append("成交量：数据不足 4 根——不适用")
    else:
        lines.append("成交量：CSV 无 volume 列——DO4 不适用")
    return state, lines


def fib_values(text):
    """复用目标计算器，输入顺序是基准方向，不能排序端点。"""
    from target_calc import calculate
    parts = text.split(":")
    if len(parts) not in (2, 3):
        raise ValueError("--fib 须为 起点:终点[:锚点]，恰好两段或三段")
    try:
        values = [float(part) for part in parts]
    except ValueError as exc:
        raise ValueError("--fib 各段须为有限数字") from exc
    start, end = values[:2]
    anchor = values[2] if len(values) == 3 else start
    retracement = calculate(start, end, "retracement", RETRACES)
    projection = calculate(start, end, "projection", EXTENSIONS, anchor,
                           "up" if end > start else "down")
    return retracement, projection


def main(argv=None):
    p = argparse.ArgumentParser(
        description="主要摆动点提取（分形 Pivot + 行索引 + 周线聚合 + 斐波比率）")
    p.add_argument("--csv", required=True, help="OHLC CSV（date,open,high,low,close[,volume]）")
    p.add_argument("--k", type=int, default=5,
                   help="分形窗口（左右各 k 根，默认 5；周线建议 4，日线粗结构 7–8）")
    p.add_argument("--start", default=None, help="分析起始日期 YYYY-MM-DD（索引基准不变）")
    p.add_argument("--end", default=None, help="分析结束日期 YYYY-MM-DD")
    p.add_argument("--weekly", action="store_true",
                   help="先聚合为周 K 再取摆动（道氏主要趋势口径）；"
                        "--chart-args 输出的索引仍是日线 CSV 行索引")
    p.add_argument("--chart-args", action="store_true",
                   help="输出 ew_chart.py 可粘贴的 --pivot 参数串（标签留 ? 待填，"
                        "含 peak/trough 定位，按极端价位 R20 口径）")
    p.add_argument("--tail", type=int, default=None,
                   help="只输出最近 N 个摆动点（表与参数串均生效）")
    p.add_argument("--path", default=None, metavar="标签@日期,...",
                   help="把选定的浪端点(标签@日期)转成 ew_chart --path 索引串：按日期在摆动点中定位"
                        "(须为 swings 含影线极值，R20)，校验索引严格递增，首点即起画点(ew_chart --start)；"
                        "索引由脚本定，禁止手填。例：--path \"1@2024-02-06,2@2026-06-30\"")
    p.add_argument("--dow", action="store_true",
                   help="输出道氏趋势状态读数（D30：最近 3 高/3 低、D11 显著筛、"
                        "3点判2点定 + 第3点一致性校验 + DO4 成交量事实）；"
                        "翻转裁决仍按 D22/DO5 由模型执行")
    p.add_argument("--fib", default=None, metavar="起点:终点[:锚点]",
                   help="区间回撤/延伸：--fib \"3148.56:5666.35:4234.12\"；"
                        "按起点到终点顺序识别上涨/下跌；锚省略时延伸自起点")
    args = p.parse_args(argv)
    fib = None
    if args.fib:
        try:
            fib = fib_values(args.fib)
        except ValueError as exc:
            p.error(str(exc))

    rows, has_volume = load_ohlc(args.csv)
    rows = [(normalize_date(r[0]), *r[1:]) for r in rows]
    lo_i = 0
    if args.start:
        s = normalize_date(args.start)
        lo_i = next((i for i, r in enumerate(rows) if r[0] >= s), None)
        if lo_i is None:
            raise SystemExit("[错误] --start 晚于数据末尾")
    hi_i = len(rows)
    if args.end:
        e = normalize_date(args.end)
        hi_i = next((i for i, r in enumerate(rows) if r[0] > e), len(rows))
        if hi_i <= lo_i:
            raise SystemExit("[错误] --end 早于 --start 范围")

    if args.weekly:
        wk = aggregate_weekly(rows[lo_i:hi_i])
        highs = [w[2] for w in wk]
        lows = [w[3] for w in wk]
        piv = fractal_pivots(highs, lows, args.k)
        # 周线摆动回填：周内极端价所在交易日的日线绝对索引
        out = []
        for idx, price, kind in piv:
            w = wk[idx]
            if kind == "H":
                j = max(range(len(w[5])), key=lambda t: rows[lo_i + w[5][t]][2])
            else:
                j = min(range(len(w[5])), key=lambda t: rows[lo_i + w[5][t]][3])
            day_i = lo_i + w[5][j]
            out.append((day_i, rows[day_i][0], price, kind, idx))
    else:
        seg = rows[lo_i:hi_i]
        piv = fractal_pivots([r[2] for r in seg], [r[3] for r in seg], args.k)
        out = [(lo_i + idx, rows[lo_i + idx][0], price, kind, idx)
               for idx, price, kind in piv]

    dow_seq = [(idx, date, price, kind) for idx, date, price, kind, _ in out] \
        if args.dow else None

    tail_dropped = 0
    if args.tail:
        tail_dropped = max(0, len(out) - args.tail)
        out = out[-args.tail:]

    mode = "周线聚合（摆动=周内极端价所在交易日）" if args.weekly else "日线"
    print("== 摆动点（k=%d，%s，共 %d 个；索引=CSV 绝对行号，R20 含影线口径）=="
          % (args.k, mode, len(out)))
    prev = None
    for idx, date, price, kind, _ in out:
        if prev is None:
            seg_txt = "  （首摆动）"
        else:
            chg = (price - prev[2]) / prev[2] * 100
            seg_txt = "  自上一点 %s(%s) %+.1f%%" % (prev[1], fmt_price(prev[2]), chg)
        print("  idx=%-5d %s  %s %10s%s" % (idx, date, kind, fmt_price(price), seg_txt))
        prev = (idx, date, price)
    if tail_dropped:
        print("  （--tail %d：已省略 %d 条更早摆动点；传 --tail 0 查看全量）"
              % (args.tail, tail_dropped))

    if args.dow:
        sig = significant_filter(dow_seq)
        dropped = len(dow_seq) - len(sig)
        print("\n== 道氏趋势状态读数（D30：D11 显著筛后 %d 个摆动%s，3 点判、2 点定）=="
              % (len(sig), "，已剔除小摆动 %d 个" % dropped if dropped else ""))
        _state, dow_lines = dow_state(sig, rows[lo_i:hi_i], has_volume)
        for ln in dow_lines:
            print("  " + ln)

    if args.chart_args:
        frag = " ".join('"?:%d:%s"' % (idx, "peak" if kind == "H" else "trough")
                        for idx, _d, _p, kind, _w in out)
        print("\n--pivot 参数串（把 ? 换成浪标签即可直接粘贴；大级别标注用，子浪请用 --path/--waves）：")
        print("  --pivot " + frag)

    if args.path:
        seq = []
        for tok in args.path.split(","):
            tok = tok.strip()
            if "@" not in tok:
                raise SystemExit("[错误] --path 每条应为 标签@日期，收到: %s" % tok)
            label, d = tok.split("@", 1)
            d = normalize_date(d)
            hit = next((o for o in out if _normdate(o[1]) == _normdate(d)), None)
            if hit is None:
                raise SystemExit("[错误] 日期 %s 不在摆动点中（端点须为 swings 含影线极值，R20）：%s"
                                 % (d, label))
            seq.append((label, hit[0], hit[1]))
        idxs = [i for _l, i, _d in seq]
        dup = {d for _l, i, _d in seq if idxs.count(i) > 1}
        if dup:
            raise SystemExit("[错误] --path 端点日期重复（同一条浪链内各子浪端点日期须唯一）：%s"
                             % sorted(dup))
        if any(idxs[k] >= idxs[k + 1] for k in range(len(idxs) - 1)):
            raise SystemExit("[错误] --path 端点索引未严格递增（日期须升序）")
        frag = ",".join("%s@%d" % (l, i) for l, i, _d in seq)
        print("\n--path 参数串（索引由 swings 摆动点定位，禁止手填；首点即起画点）：")
        print("  --path \"" + frag + "\"")
        print("  起画点(ew_chart --start): %s (idx %s)" % (seq[0][2], seq[0][1]))
        print("  （一条 --path = 一个连续浪链；不同大级别/层级浪请拆分多条 --path 传）")

    if fib:
        retracement, projection = fib
        print("\n== 斐波那契（起点 %.3f→终点 %.3f，宽 %.3f；延伸锚 %.3f）=="
              % (retracement["start"], retracement["end"], retracement["length"], projection["origin"]))
        print("  回撤位（自终点%s）：" % ("向上" if retracement["direction"] == "up" else "向下"))
        for value in retracement["values"]:
            print("    %.1f%% → %.3f" % (value["ratio"] * 100, value["price"]))
        print("  延伸位（自锚点%s投影）：" % ("向上" if projection["direction"] == "up" else "向下"))
        for value in projection["values"]:
            print("    %.3f×区间 → %.3f" % (value["ratio"], value["price"]))


if __name__ == "__main__":
    sys.exit(main())
