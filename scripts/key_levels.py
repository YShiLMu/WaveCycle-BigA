#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""技术分析锚点检测脚本（原"关键结构位提取"，横向锚点）。

用途：workflow 第 1 步「5.2 技术分析锚点提取」与 R32 要求三类横向锚点用脚本
产出、禁止肉眼扫描原始行情（趋势线为第四类，由模型基于本脚本输出的摆动点
自行连线并披露端点，不要求脚本产出）。本脚本覆盖三类：
  1. 前高/前低 —— 被 ≥2 次触及的历史极值（箱体边界），相邻触及间隔 ≥3 根
     K 线，近邻价位按 --cluster-tolerance 聚类合并（D27 第 2 类）
  2. 跳空缺口 —— 未回补区间（D27 第 3 类）
  3. 多日未破压力/支撑位 —— 长影线顶端 + 收盘未破（D27 第 4 类，核心），
     近邻价位聚类去重（同簇取该方向最极端值，避免输出密集重复价位）

数据自检：读取时强制校验 high ≥ low ≥ 0、open/close 落在 [low, high]、
volume ≥ 0（如有）、日期升序无重复（workflow 第 1 步 1.5 口径），
坏数据直接报错并退出，禁止带病数据产出锚点。

用法：
    python key_levels.py --csv data.csv [--shadow-ratio 2.0]
                         [--trend-threshold 0.05] [--window 0] [--swing-k 3]
                         [--cluster-tolerance 0.001]

CSV 列：date,open,high,low,close[,volume]（date 兼容 YYYY-MM-DD 与 YYYYMMDD 两种格式）。
"""

import argparse

import pandas as pd


def _validate_ohlc(df):
    """数据自检（workflow 第 1 步 1.5 口径）：high ≥ low ≥ 0、open/close 落在
    [low, high]、volume ≥ 0（如有）、日期升序无重复。坏数据直接报错（行号按 CSV）。"""

    def rows(mask):
        return [int(i) + 2 for i in df.index[mask][:10]]

    h = df["high"].astype(float)
    l = df["low"].astype(float)
    o = df["open"].astype(float)
    c = df["close"].astype(float)
    if (h < l).any():
        raise ValueError("数据自检失败：high < low 的行号 %s" % rows(h < l))
    if (l < 0).any():
        raise ValueError("数据自检失败：low < 0 的行号 %s" % rows(l < 0))
    oob_o = (o < l - 1e-9) | (o > h + 1e-9)
    if oob_o.any():
        raise ValueError("数据自检失败：open 超出 [low, high] 的行号 %s" % rows(oob_o))
    oob_c = (c < l - 1e-9) | (c > h + 1e-9)
    if oob_c.any():
        raise ValueError("数据自检失败：close 超出 [low, high] 的行号 %s" % rows(oob_c))
    if "volume" in df.columns:
        v = df["volume"].astype(float)
        if (v < 0).any():
            raise ValueError("数据自检失败：volume < 0 的行号 %s" % rows(v < 0))
    dup = df["date"].duplicated()
    if dup.any():
        raise ValueError("数据自检失败：日期重复：%s" % sorted(df.loc[dup, "date"].astype(str).head(5)))
    if not df["date"].is_monotonic_increasing:
        raise ValueError("数据自检失败：日期未按升序排列")


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
    _validate_ohlc(df)
    return df


def cluster_levels(candidates, tol=0.001):
    """把近邻候选价位聚类合并（容差 tol×价位），同一方向的簇只保留该方向最极端值
    （压力取最高、支撑取最低）。candidates: [{center, date, direction}, ...]；
    返回 [{center, direction, dates, count}, ...]，center 降序。"""
    clusters = []
    for cand in sorted(candidates, key=lambda x: -x["center"]):
        merged = False
        for cl in clusters:
            if cl["direction"] != cand["direction"]:
                continue
            base = max(abs(cand["center"]), abs(cl["center"])) or 1.0
            if abs(cand["center"] - cl["center"]) <= tol * base:
                if cand["direction"] == "压力":
                    cl["center"] = max(cl["center"], cand["center"])
                else:
                    cl["center"] = min(cl["center"], cand["center"])
                cl["dates"].append(cand["date"])
                cl["count"] += 1
                merged = True
                break
        if not merged:
            clusters.append({"center": float(cand["center"]), "direction": cand["direction"],
                             "dates": [cand["date"]], "count": 1})
    clusters.sort(key=lambda x: -x["center"])
    return clusters


def detect_swing_levels(df, k=3, tol=0.001, min_gap=3):
    """前高/前低（D27 第 2 类）：被 ≥2 次触及的历史极值（箱体边界），
    两次触及间隔 ≥ min_gap 根 K 线。

    以 k=3 分形摆动点为候选极值，先按容差聚类成近邻价位簇（簇价取该方向最极端值），
    再统计全样本中的触及事件：压力（前高）= 最高价到达簇价（容差内），
    支撑（前低）= 最低价到达簇价（容差内）；价格连续停留在价位之上/之下的
    若干根 K 线只合并计为一次触及（离开后再回来才算新触及），相邻触及
    间隔不足 min_gap 根的并入上一次。有效触及 ≥2 次才输出。

    返回 [{center, direction("前高"/"前低"), touches, first, last}, ...]，center 降序。
    """
    highs = df["high"].astype(float).values
    lows = df["low"].astype(float).values
    dates = df["date"].values
    n = len(df)
    seeds = []
    for i in range(k, n - k):
        if highs[i] >= highs[i - k:i + k + 1].max():
            seeds.append({"center": float(highs[i]), "date": dates[i], "direction": "压力"})
        elif lows[i] <= lows[i - k:i + k + 1].min():
            seeds.append({"center": float(lows[i]), "date": dates[i], "direction": "支撑"})
    out = []
    for cl in cluster_levels(seeds, tol):
        if cl["direction"] == "压力":
            mask = highs >= cl["center"] * (1 - tol)
        else:
            mask = lows <= cl["center"] * (1 + tol)
        # 一次接近事件 = 一次触及：连续满足的 K 线合并，离开后再回来才算新触及
        events = [i for i, m in enumerate(mask) if m and (i == 0 or not mask[i - 1])]
        touches = []
        for i in events:
            if not touches or i - touches[-1] >= min_gap:
                touches.append(i)
        if len(touches) >= 2:
            out.append({"center": cl["center"],
                        "direction": "前高" if cl["direction"] == "压力" else "前低",
                        "touches": len(touches),
                        "first": dates[touches[0]], "last": dates[touches[-1]]})
    out.sort(key=lambda x: -x["center"])
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


def detect_horizontal_levels(df, shadow_ratio=2.0, window=250, mode="both", tol=0.001):
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
    支撑位（由 adaptive_window 的趋势方向决定）。检出候选后按 tol 容差
    聚类去重，同簇取该方向最极端值（kind 注明合并条数）。

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
    # 近邻价位聚类去重（同簇取该方向最极端值），避免长影线密集区输出重复价位
    merged = []
    for cl in cluster_levels(levels, tol):
        kind = "长上影顶端" if cl["direction"] == "压力" else "长下影底端"
        if cl["count"] > 1:
            kind += "×%d" % cl["count"]
        merged.append({"center": cl["center"], "date": max(cl["dates"]),
                       "direction": cl["direction"], "kind": kind})
    return merged


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
    ap.add_argument("--cluster-tolerance", type=float, default=0.001,
                    help="近邻价位聚类容差（相对值，默认 0.001 = ±0.1%%，同簇只保留方向最极端值）")
    args = ap.parse_args(argv)

    df = load_ohlc(args.csv)

    print("== 1. 前高/前低（D27 第 2 类：被 ≥2 次触及的历史极值，相邻触及间隔 ≥3 根，"
          "聚类容差 ±%.1f%%）==" % (args.cluster_tolerance * 100))
    swing_levels = detect_swing_levels(df, args.swing_k, args.cluster_tolerance)
    if not swing_levels:
        print("  （无）")
    for lv in swing_levels:
        print("  %s %.3f —— 触及 %d 次（首次 %s，最近 %s）"
              % (lv["direction"], lv["center"], lv["touches"],
                 _fmt(lv["first"]), _fmt(lv["last"])))

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
    print("\n== 3. 多日未破压力/支撑位（最近走势判定：%s → 扫近 %d 根，%s，长影线 >= 实体×%.1f，后续收盘未破，聚类容差 ±%.1f%%）=="
          % (trend, window, side, args.shadow_ratio, args.cluster_tolerance * 100))
    levels = detect_horizontal_levels(df, args.shadow_ratio, window, mode,
                                      args.cluster_tolerance)
    if not levels:
        print("  （无）")
    for lv in levels:
        print("  %.3f %s（%s）—— %s，后续收盘未破"
              % (lv["center"], lv["direction"], _fmt(lv["date"]), lv["kind"]))


if __name__ == "__main__":
    main()
