#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""技术分析锚点检测脚本（原"关键结构位提取"，横向锚点）。

用途：workflow 第 1 步「5.2 技术分析锚点提取」要求横向锚点全部用脚本产出，
禁止肉眼扫描原始行情。本脚本覆盖三类（趋势线由模型基于摆动点自行连线）：
  1. 前高/前低 —— 分形摆动点（D27 第 2 类）
  2. 跳空缺口 —— 未回补区间（D27 第 3 类）
  3. 多日未破压力/支撑位 —— 长影线顶端 + 收盘未破（D27 第 4 类，核心）

用法：
    python key_levels.py --csv data.csv [--shadow-ratio 2.0]
                         [--trend-threshold 0.05] [--window 0] [--swing-k 3]

CSV 列：date,open,high,low,close（date 兼容 YYYY-MM-DD 与 YYYYMMDD 两种格式）。
"""

import argparse

import pandas as pd


def load_ohlc(csv_path):
    df = pd.read_csv(csv_path)
    required = {"date", "open", "high", "low", "close"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError("CSV 缺少列: %s" % sorted(missing))
    raw = df["date"].astype(str)
    if raw.str.contains("-").any():
        df["date"] = pd.to_datetime(raw)
    else:
        df["date"] = pd.to_datetime(raw, format="%Y%m%d")
    return df


def detect_swings(df, k=3):
    """分形摆动点（前高/前低）。返回 [(date, 'H'/'L', price), ...]"""
    out = []
    highs = df["high"].astype(float).values
    lows = df["low"].astype(float).values
    dates = df["date"].values
    n = len(df)
    for i in range(k, n - k):
        w_hi = highs[i - k:i + k + 1]
        w_lo = lows[i - k:i + k + 1]
        if highs[i] >= w_hi.max():
            out.append((dates[i], "H", highs[i]))
        elif lows[i] <= w_lo.min():
            out.append((dates[i], "L", lows[i]))
    return out


def detect_gaps(df):
    """跳空缺口（未回补区间）。返回 [(date, '上跳'/'下跳', 下沿, 上沿), ...]"""
    gaps = []
    highs = df["high"].astype(float).values
    lows = df["low"].astype(float).values
    dates = df["date"].values
    for i in range(1, len(df)):
        if lows[i] > highs[i - 1]:
            gaps.append((dates[i], "上跳", highs[i - 1], lows[i]))
        elif highs[i] < lows[i - 1]:
            gaps.append((dates[i], "下跳", highs[i], lows[i - 1]))
    return gaps


def adaptive_window(closes, threshold=0.05):
    """按最近走势自适应选择候选扫描窗口与找位方向（D27 第 4 类）。

    用最近 10 天首尾收盘涨跌幅判定趋势（涨跌幅 = (收盘[-1]-收盘[-11])/收盘[-11]）：
      - >= +threshold —— 上升 → 扫近 10 天，只找压力位（长上影线顶端）
      - <= -threshold —— 下跌 → 扫近 10 天，只找支撑位（长下影线底端）
      - 其间（横盘）   —— 扫近 30 天；若最近 20 天也横盘（|涨跌幅| < threshold）
        则扫近 60 天；横盘时压力位、支撑位两侧都找

    返回 (window, trend)，trend ∈ {"上升", "下跌", "横盘"}；数据不足时
    窗口取全部根数并视为横盘。
    """
    n = len(closes)
    if n >= 11:
        pct10 = (closes[-1] - closes[-11]) / closes[-11]
        if pct10 >= threshold:
            return min(10, n), "上升"
        if pct10 <= -threshold:
            return min(10, n), "下跌"
        if n >= 21:
            pct20 = (closes[-1] - closes[-21]) / closes[-21]
            if abs(pct20) < threshold:
                return min(60, n), "横盘"
        return min(30, n), "横盘"
    return min(30, n), "横盘"


def detect_horizontal_levels(df, shadow_ratio=2.0, window=250, mode="both"):
    """多日未破压力/支撑位（长影线顶端 + 收盘未破，D27 第 4 类）。

    压力位/支撑位 = 长影线的顶端/底端，且后续收盘未突破/跌破：
    - 压力位候选：上影线 >= 实体 × shadow_ratio（长上影线，同蜡烛图
      "流星线/射击之星"口径），顶端 = 最高价；该 K 线之后直到最新的
      所有收盘价都 < 顶端，才算压力位（任一收盘 >= 顶端即已突破，跳过）；
    - 支撑位候选（对称）：下影线 >= 实体 × shadow_ratio（长下影线，同
      "锤子线"口径），底端 = 最低价；该 K 线之后直到最新的所有收盘价
      都 > 底端，才算支撑位（任一收盘 <= 底端即已跌破，跳过）。

    候选只在最近 window 根 K 线内扫描（跳过窗口内最后一根之后的候选由
    趋势窗口规则另行控制），但"后续收盘未破"始终验证到数据最新一根。
    mode 控制找位方向："both" 两侧都找，"压力" 只找压力位，"支撑" 只找
    支撑位（由 adaptive_window 的趋势方向决定）。

    返回 [{center, date, direction, kind}, ...]，center 降序。
    """
    highs = df["high"].astype(float).values
    lows = df["low"].astype(float).values
    opens = df["open"].astype(float).values
    closes = df["close"].astype(float).values
    dates = df["date"].values
    n = len(df)
    start = max(0, n - window)  # 候选扫描起点（只扫最近 window 根）

    levels = []
    for i in range(start, n - 1):  # 最后一根之后没有"后续"，跳过
        body = abs(closes[i] - opens[i])
        upper = highs[i] - max(opens[i], closes[i])   # 上影线
        lower = min(opens[i], closes[i]) - lows[i]    # 下影线

        # 压力位候选：长上影线，顶端 = 最高价，后续收盘未破
        if mode in ("both", "压力") and upper >= body * shadow_ratio:
            tip = highs[i]
            if all(closes[j] < tip for j in range(i + 1, n)):
                levels.append({"center": float(tip), "date": dates[i],
                               "direction": "压力", "kind": "长上影顶端"})
        # 支撑位候选（对称）：长下影线，底端 = 最低价，后续收盘未破
        if mode in ("both", "支撑") and lower >= body * shadow_ratio:
            tip = lows[i]
            if all(closes[j] > tip for j in range(i + 1, n)):
                levels.append({"center": float(tip), "date": dates[i],
                               "direction": "支撑", "kind": "长下影底端"})

    levels.sort(key=lambda x: -x["center"])
    return levels


def _fmt(d):
    return pd.Timestamp(d).strftime("%Y-%m-%d") if d is not None else "-"


def main(argv=None):
    ap = argparse.ArgumentParser(description="技术分析锚点提取（横向锚点）")
    ap.add_argument("--csv", required=True, help="行情 CSV 路径")
    ap.add_argument("--shadow-ratio", type=float, default=2.0,
                    help="长影线判定倍率：影线 >= 实体 × 该值（默认 2.0，同流星线/锤子线口径）")
    ap.add_argument("--trend-threshold", type=float, default=0.05,
                    help="趋势判定阈值：近 10 天首尾收盘涨跌幅 >= +该值为上升、<= -该值为下跌、其间为横盘（默认 0.05）")
    ap.add_argument("--window", type=int, default=0,
                    help="候选扫描窗口（默认 0 = 按最近走势自适应：上升/下跌近 10 天，横盘近 30 天，近 20 天横盘则近 60 天）")
    ap.add_argument("--swing-k", type=int, default=3,
                    help="摆动点分形窗口（默认 3）")
    args = ap.parse_args(argv)

    df = load_ohlc(args.csv)

    print("== 1. 前高/前低（摆动点，k=%d）==" % args.swing_k)
    for d, t, p in detect_swings(df, args.swing_k):
        print("  %s %s %.2f" % (_fmt(d), t, p))

    print("\n== 2. 跳空缺口 ==")
    gaps = detect_gaps(df)
    if not gaps:
        print("  （无）")
    for d, t, lo, hi in gaps:
        print("  %s %s %.2f–%.2f" % (_fmt(d), t, lo, hi))

    closes = df["close"].astype(float).values
    window, trend = adaptive_window(closes, args.trend_threshold)
    if args.window > 0:
        window = args.window
    mode = {"上升": "压力", "下跌": "支撑", "横盘": "both"}[trend]
    side = "只找压力位（长上影线顶端）" if trend == "上升" else \
           "只找支撑位（长下影线底端）" if trend == "下跌" else \
           "压力位、支撑位两侧都找"
    print("\n== 3. 多日未破压力/支撑位（最近走势判定：%s → 扫近 %d 根，%s，长影线 >= 实体×%.1f，后续收盘未破）=="
          % (trend, window, side, args.shadow_ratio))
    levels = detect_horizontal_levels(df, args.shadow_ratio, window, mode)
    if not levels:
        print("  （无）")
    for lv in levels:
        print("  %.3f %s（%s）—— %s，后续收盘未破"
              % (lv["center"], lv["direction"], _fmt(lv["date"]), lv["kind"]))


if __name__ == "__main__":
    main()
