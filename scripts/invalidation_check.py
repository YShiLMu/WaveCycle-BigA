#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""失效价位触发判定脚本（workflow 第 5 步 2.2 节，D29 口径）。

用途：更新轮（05 更新数浪）把上一份报告的失效价位清单与最新行情 CSV 交给
本脚本，机械判定每个失效价位是否触发。禁止模型重读 CSV 逐根比价。
本脚本只输出事实（是否触发、首次触及日、确认窗口状态、距离），触发后的
分支处理（降级/切换/退回）仍由模型按 05 第 2.3 节判断。

判定口径（D29，与 05 第 2.2 节一致）：
  - 触及按极端价位（R20）：break-down（跌破支撑/失效位）= low ≤ 价位；
    break-up（升破压力/失效位）= high ≥ 价位
  - 确认窗口："触及后连续 N 根收盘未收回"（默认 N=2，--confirm-bars），
    从触及 bar 的下一根起计；收回定义：break-down 后收盘 > 价位，
    break-up 后收盘 < 价位
  - --since YYYY-MM-DD 只从该日起判定触及（增量更新用；此前触及不计）

用法：
    python invalidation_check.py --csv data.csv \
        --level "160|break-down|主方案|规则失效|R7" \
        --level "185|break-down|主方案|结构失效|06 6.6注" \
        [--since 2026-08-14] [--confirm-bars 2]

--level 五段格式（竖线分隔，解析失败即报错退出，防止静默漏判）：
    价位|方向(break-down/break-up)|方案|类型(规则失效/结构失效)|对应规则

输出：markdown 表 + 触发摘要一行。退出码：0 正常（触发与否都算正常完成）。
CSV 列：date,open,high,low,close[,volume]（复用 key_levels.load_ohlc，坏数据硬拦截）。
"""

import argparse
import sys

import pandas as pd

from ohlc_io import load_ohlc, fmt_date


def parse_level(text):
    parts = [p.strip() for p in text.split("|")]
    if len(parts) != 5:
        raise SystemExit("[错误] --level 需为 5 段「价位|方向|方案|类型|规则」，收到 %d 段：%r"
                         % (len(parts), text))
    price_s, direction, plan, kind, rule = parts
    if direction not in ("break-down", "break-up"):
        raise SystemExit("[错误] --level 方向段须为 break-down（跌破）或 break-up（升破），收到：%r" % direction)
    try:
        price = float(price_s)
    except ValueError:
        raise SystemExit("[错误] --level 价位段不是数字：%r" % price_s)
    return {"price": price, "direction": direction, "plan": plan, "kind": kind, "rule": rule}


def check_level(df, lv, since=None, confirm_bars=2):
    """判定单个失效价位。返回 dict（状态、首次触及日、确认根数、确认日、距离）。"""
    price = lv["price"]
    down = lv["direction"] == "break-down"
    dates = df["date"].values
    lows = df["low"].astype(float).values
    highs = df["high"].astype(float).values
    closes = df["close"].astype(float).values

    start = 0
    if since is not None:
        ts = pd.Timestamp(since)
        idx = df.index[df["date"] >= ts]
        if len(idx) == 0:
            return {**lv, "status": "数据范围在 --since 之后为空", "first_touch": None,
                    "confirmed": None, "run": 0, "dist": None}
        start = int(idx[0])

    touch = None
    for i in range(start, len(df)):
        if (lows[i] <= price) if down else (highs[i] >= price):
            touch = i
            break
    last_close = float(closes[-1])
    dist = last_close - price  # 正=在价位上方

    if touch is None:
        return {**lv, "status": "未触发", "first_touch": None,
                "confirmed": None, "run": 0, "dist": dist}

    # 触及后逐根扫描：streak = 当前连续未收回根数；streak 首次达到 confirm_bars
    # 的那根即确认日（确认后 streak 只表示当前尾段，不再影响判定）
    def recovered(c):
        return c > price if down else c < price

    confirm_idx = None
    streak = 0
    for j in range(touch + 1, len(df)):
        if not recovered(closes[j]):
            streak += 1
            if confirm_idx is None and streak >= confirm_bars:
                confirm_idx = j
        else:
            streak = 0
    confirmed = confirm_idx is not None
    status = ("已触发且已确认（连续 %d 根收盘未收回）" % confirm_bars if confirmed
              else "已触发待确认（触及后连续未收回 %d 根，确认窗口 %d）" % (streak, confirm_bars))
    return {**lv, "status": status, "first_touch": dates[touch],
            "confirmed": dates[confirm_idx] if confirmed else None,
            "run": streak, "dist": dist}


def main(argv=None):
    ap = argparse.ArgumentParser(description="失效价位触发判定（workflow 第 5 步 2.2，D29）")
    ap.add_argument("--csv", required=True, help="行情 CSV 路径")
    ap.add_argument("--level", action="append", required=True,
                    help="失效价位，5 段「价位|break-down/break-up|方案|类型|规则」，可重复")
    ap.add_argument("--since", default=None, help="只从该日期起判定触及（YYYY-MM-DD，增量更新用）")
    ap.add_argument("--confirm-bars", type=int, default=2,
                    help="确认窗口：触及后连续 N 根收盘未收回（默认 2，D 口径）")
    args = ap.parse_args(argv)

    levels = [parse_level(t) for t in args.level]
    df = load_ohlc(args.csv)

    print("## 失效价位触发判定（invalidation_check.py，确认窗口 = 触及后连续 %d 根收盘未收回%s）\n"
          % (args.confirm_bars, "，--since %s 起" % args.since if args.since else ""))
    print("| 方案 | 失效价位 | 方向 | 类型 | 对应规则 | 状态 | 首次触及 | 确认日 | 距最新收盘 |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    n_trig = 0
    n_conf = 0
    for lv in levels:
        r = check_level(df, lv, args.since, args.confirm_bars)
        arrow = "跌破" if lv["direction"] == "break-down" else "升破"
        dist = ("%.3f（价格在上方）" % r["dist"]) if r["dist"] is not None and r["dist"] > 0 else \
               ("%.3f（价格在下方）" % -r["dist"]) if r["dist"] is not None else "-"
        print("| %s | %.3f | %s | %s | %s | %s | %s | %s | %s |"
              % (lv["plan"], lv["price"], arrow, lv["kind"], lv["rule"], r["status"],
                 fmt_date(r["first_touch"]), fmt_date(r["confirmed"]), dist))
        if "已触发" in r["status"]:
            n_trig += 1
            if "已确认" in r["status"]:
                n_conf += 1

    print("\n触发摘要：%d/%d 个失效价位已触发，其中 %d 个已过确认窗口。"
          % (n_trig, len(levels), n_conf))
    if n_trig:
        print("触发后的分支处理（降级/切换/退回，05 第 2.3 节）由模型判断，本脚本不替代。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
