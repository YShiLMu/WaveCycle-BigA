#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2-4 趋势线两阶段确认（Neely Post-Constructive，07 G28 / D36 口径）。

用途：推动浪走完后，用后续行为核对数法可信度。**定位：可信度参考**
（按既有评分接口记录，不新增分值；不产生失效价位，失效价位由 06 R19/R20 承担）。
输入是模型枚举的推动浪关键端点（日期:价）+ 原始 K 线 CSV，脚本做两阶段判定。

Stage 1（时间）：画穿过第 2、4 浪终点的 2-4 趋势线，看第 5 浪结束后市场是否在
「第 5 浪形成所用时间以内」回撤并穿越该线。
Stage 2（深度）：按延长类型核对后续回撤深度——第 1 浪延长 → 先看第 4 浪终点，父级1/5时常进一步至第2浪区；
第 3 浪延长 → 回撤到第 4 浪价位区（整段>61.8% 提示完成更大级别）；
第 5 浪延长 → 至少回撤第 5 浪61.8%，不完全回撤仅为原趋势延续条件。

用法：
    python post_constructive_check.py --csv ohlc.csv \
        --w1 "2440.91:3288.45" --w2 "2020-03-19:2646.80" \
        --w4 "2021-03-09:3328.31" --w5 "2021-09-14:3723.85" --ext 3
    --w1 只有起点价/终点价（用于方向）；--ext 标明哪一浪延长；方向缺省按 w1 判。
输出：markdown 表（Stage | 判定 | 依据）——脚本只给"符合/不完全"事实，
不自动识别延长类型、父级位置或内部完成；按既有G21接口说明证据。
"""

import argparse
import math
import sys
from ohlc_io import load_ohlc


def parse_dp(text):
    parts = text.split(":")
    if len(parts) != 2:
        raise SystemExit("[错误] 端点需为「日期:价」，收到：%r" % text)
    d, p = parts[0].strip(), parts[1].strip()
    try:
        price = float(p)
        if not math.isfinite(price):
            raise SystemExit("[错误] 端点价格必须是有限数值。")
        return d, price
    except ValueError:
        raise SystemExit("[错误] 「日期:价」的价格不是数字：%r" % text)


def line_at(row, r2, p2, r4, p4):
    """2-4 趋势线在行号 row 处的价格（(r2,p2)-(r4,p4) 线性插值）。"""
    if r4 == r2:
        return p2
    return p2 + (p4 - p2) * (row - r2) / (r4 - r2)


def main(argv=None):
    ap = argparse.ArgumentParser(description="2-4 趋势线两阶段确认（07 G28 / D36）")
    ap.add_argument("--csv", required=True, help="原始 OHLC CSV（date,open,high,low,close）")
    ap.add_argument("--w1", required=True, help="第 1 浪「起点价:终点价」（用于判方向）")
    ap.add_argument("--w2", required=True, help="第 2 浪终点「日期:价」")
    ap.add_argument("--w4", required=True, help="第 4 浪终点「日期:价」")
    ap.add_argument("--w5", required=True, help="第 5 浪终点「日期:价」")
    ap.add_argument("--ext", type=int, choices=[1, 3, 5], default=3,
                    help="哪一浪延长（1/3/5），区分 Stage2 回撤要求")
    ap.add_argument("--up", action="store_true", help="上升推动（缺省按 w1 判）")
    ap.add_argument("--down", action="store_true", help="下跌推动（缺省按 w1 判）")
    ap.add_argument("--scan", type=int, default=60,
                    help="第 5 浪结束后扫描的最大 K 线数（默认 60）")
    args = ap.parse_args(argv)
    if args.scan < 1 or (args.up and args.down):
        ap.error("扫描根数须为正整数，方向不能同时指定")

    df = load_ohlc(args.csv, set_date_index=True)
    idx = df.index

    w2 = parse_dp(args.w2)
    w4 = parse_dp(args.w4)
    w5 = parse_dp(args.w5)

    _w1p = args.w1.split(":")
    if len(_w1p) != 2:
        raise SystemExit("[错误] --w1 需为「起点价:终点价」，收到：%r" % args.w1)
    try:
        w1s, w1e = float(_w1p[0]), float(_w1p[1])
    except ValueError:
        raise SystemExit("[错误] --w1 价格不是数字：%r" % args.w1)

    if not all(math.isfinite(p) for p in (w1s, w1e)) or w1s == w1e:
        raise SystemExit("[错误] 第1浪价格必须有限且长度非零。")

    if args.up and not args.down:
        up = True
    elif args.down and not args.up:
        up = False
    else:
        up = w1e >= w1s

    def row_of(date):
        try:
            return idx.get_loc(date)
        except KeyError:
            raise SystemExit("[错误] 端点日期不在数据中：%s" % date)

    r2, p2 = row_of(w2[0]), w2[1]
    r4, p4 = row_of(w4[0]), w4[1]
    r5, p5 = row_of(w5[0]), w5[1]

    if not r2 < r4 < r5:
        raise SystemExit("[错误] 第2、4、5浪终点日期须严格递增。")
    if (p5 <= p4 if up else p5 >= p4):
        raise SystemExit("[错误] 第5浪须沿指定推动方向运动且长度非零。")
    w5_bars = r5 - r4

    # Stage 1：第 5 浪结束后，找首次穿越 2-4 趋势线的根数
    scan_end = min(r5 + 1 + args.scan, len(idx))
    crossover_row = None
    for row in range(r5 + 1, scan_end):
        line = line_at(row, r2, p2, r4, p4)
        # 项目含影线口径；单根K内的精确穿越时刻无法由OHLC还原。
        price = float(df["low" if up else "high"].iloc[row])
        broke = (price < line) if up else (price > line)
        if broke:
            crossover_row = row
            break

    if crossover_row is not None:
        ret_bars = crossover_row - r5
        stage1_ok = ret_bars <= w5_bars
        note = ("%d 根穿越 2-4 趋势线，第 5 浪用 %d 根 —— %s"
                % (ret_bars, w5_bars,
                   "符合（在第 5 浪用时以内）" if stage1_ok
                   else "超过第 5 浪用时（提示：可能是 Terminal / 第 4 浪未走完 / 数法需复查）"))
    else:
        observed = scan_end - r5 - 1
        stage1_ok = False if observed >= w5_bars else None
        note = "已观察 %d 根，第 5 浪用 %d 根；%s" % (observed, w5_bars, "窗口已满但未穿越" if stage1_ok is False else "观察窗口不足，待确认")

    # Stage 2：回撤极限 + 相对第 5 浪回撤% + 目标区间提示
    lows = [float(df["low"].iloc[row]) for row in range(r5 + 1, scan_end)]
    highs = [float(df["high"].iloc[row]) for row in range(r5 + 1, scan_end)]
    extreme = (min(lows) if up else max(highs)) if (lows if up else highs) else None

    if extreme is not None:
        w5_span = abs(p5 - p4)
        retrace_pct = max(0.0, (p5 - extreme) if up else (extreme - p5)) / w5_span * 100
        if args.ext == 1:
            hint = "先看第4浪终点（%.3f）；父级1/5时常进一步至第2浪区（%.3f），父级3未必" % (p4, p2)
        elif args.ext == 3:
            hint = "应回撤到第 4 浪价位区（%.3f 附近）；整段>61.8%% 提示完成更大级别" % p4
        else:
            hint = "至少回撤第五浪61.8%；不完全回撤仅为原趋势延续条件，完全回撤提示更大趋势终结"
        s2_note = ("回撤极限 %.3f（相对第 5 浪 %.1f%%）；%s" % (extreme, retrace_pct, hint))
        stage2_ok = None
        if args.ext == 5:
            if retrace_pct >= 100:
                stage2_ok = False
            elif retrace_pct >= 61.8 or math.isclose(retrace_pct, 61.8, rel_tol=0, abs_tol=1e-9):
                stage2_ok = True
            else:
                s2_note += "；尚未达到深度，继续观察（不以扫描上限判失败）"
    else:
        s2_note = "扫描内无有效回撤数据"
        stage2_ok = None

    print("## 2-4 趋势线两阶段确认（post_constructive_check.py，07 G28 / D36 口径）\n")
    print("| Stage | 判定 | 依据 |")
    print("| --- | --- | --- |")
    print("| Stage 1（时间） | %s | %s |" % ("符合" if stage1_ok else ("待确认" if stage1_ok is None else "不完全"), note))
    print("| Stage 2（深度） | %s | %s |" %
          ("符合" if stage2_ok else ("核对" if stage2_ok is None else "不完全"), s2_note))
    if stage1_ok is False:
        print("\n> Stage 1未获支持：应撤回Neely完成确认并复查标签；经典框架候选须独立核对。")
    elif stage1_ok is None:
        print("\n> Stage 1证据不足：不得标为Neely已确认完成。")
    print("\n> 按K线序号计时、含影线极值检查穿线；扫描上限不是统一完成期限。"
          "Stage2仅列观察值和条件，第五浪延长的‘符合’只表示当前观察到的深度符合延续条件。"
          "脚本不证明内部完成、延长类型或父级位置；按既有G21说明证据，不新增分值，"
          "不产生失效价位（06 R19/R20）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
