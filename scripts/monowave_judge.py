#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""单浪归口（Neely Pre-Constructive，06 R33 / 09 D33-D34 口径）。

用途：对候选 Monowave 序列，算 m2/m1（及可选 m0/m1）价格覆盖比例 →
给出 Rule 1–7 标识 + Directional / Non-Directional 行为归类。消除手算比例、
对分档表记错的误差。输入是**模型枚举出的单浪端点价格**（按 R20 极端价位口径
取自 swings.py 输出），不是 CSV。

判定口径（源自 Neely ch03，转引 06 R33 / D33-D34）：
  - 回撤% = |m2| / |m1| × 100（m1 = 当前分析浪，m2 = 其后回撤浪）
  - Rule 分档（按 m2/m1）：<38.2%→R1；≥38.2%且<61.8%→R2；=61.8%→R3；
    61.8%<x<100%→R4；≥100%且<161.8%→R5；161.8%≤x≤261.8%→R6；>261.8%→R7
  - 方向/非方向：m2/m1 ≤61.8% → Directional；>61.8% → Non-Directional；
    方向行为终止阈值 = 回撤 >100%；非方向行为终止阈值 = 超过全范围 161.8%

用法：
    python monowave_judge.py --m1 "起点价:终点价" --m2 "起点价:终点价"
    python monowave_judge.py --m1 "100:180" --m2 "180:130" --m0 "80:100"

输出：markdown 表（回撤% | Rule 标识 | 方向归类 | 相关容忍阈值提示）。
说明：Condition（小写字母）/ Category（罗马数字）需对照原书表（06 R33 引用），
本脚本只给最确定的 Rule + 行为归类，不硬编字母。
"""

import argparse
import sys


def parse_pair(text):
    parts = text.split(":")
    if len(parts) != 2:
        raise SystemExit("[错误] 端点需为「起点价:终点价」，收到：%r" % text)
    try:
        return float(parts[0]), float(parts[1])
    except ValueError:
        raise SystemExit("[错误] 端点价格不是数字：%r" % text)


def move_len(pair):
    return abs(pair[1] - pair[0])


def rule_of(ratio):
    """回撤% → Rule 1–7（D33 分档，含边界）。"""
    if ratio < 38.2:
        return "Rule 1"
    if ratio < 61.8:
        return "Rule 2"
    if abs(ratio - 61.8) < 1e-9:
        return "Rule 3"
    if ratio < 100:
        return "Rule 4"
    if ratio < 161.8:
        return "Rule 5"
    if ratio <= 261.8:
        return "Rule 6"
    return "Rule 7"


def main(argv=None):
    ap = argparse.ArgumentParser(description="单浪归口（06 R33 / D33-D34）")
    ap.add_argument("--m1", required=True, help="m1 浪端点「起点价:终点价」")
    ap.add_argument("--m2", required=True, help="m2 浪端点（回撤浪）「起点价:终点价」")
    ap.add_argument("--m0", default=None, help="可选 m0 浪端点「起点价:终点价」（前浪）")
    args = ap.parse_args(argv)

    m1 = parse_pair(args.m1)
    m2 = parse_pair(args.m2)
    l1 = move_len(m1)
    l2 = move_len(m2)
    if l1 == 0:
        raise SystemExit("[错误] m1 长度为 0，无法计算比例。")
    ratio = l2 / l1 * 100.0
    rule = rule_of(ratio)
    directional = ratio <= 61.8
    dlabel = "Directional（方向性）" if directional else "Non-Directional（非方向性）"

    print("## 单浪归口（monowave_judge.py，06 R33 / D33-D34 口径）\n")
    print("| m1 长度 | m2 长度 | m2/m1 回撤% | Rule 标识 | 行为归类 |")
    print("| --- | --- | --- | --- | --- |")
    print("| %.3f | %.3f | %.2f%% | %s | %s |"
          % (l1, l2, ratio, rule, dlabel))

    print("\n| 相关容忍阈值 | 判定 | 依据 |")
    print("| --- | --- | --- |")
    print("| Directional 终止（回撤 >100%%） | %s | 回撤 %.2f%% %s 100%% |"
          % ("已触发" if ratio > 100 else "未触发", ratio, "＞" if ratio > 100 else "≤"))
    print("| Non-Directional 终止（超全范围 161.8%%） | %s | 回撤 %.2f%% %s 161.8%% |"
          % ("已触发" if ratio > 161.8 else "未触发", ratio, "＞" if ratio > 161.8 else "≤"))

    if args.m0:
        m0 = parse_pair(args.m0)
        l0 = move_len(m0)
        if l1:
            r0 = l0 / l1 * 100.0
            print("\n| m0/m1 比例 | %.2f%% |（Condition 字母与 Category 需对照原书表，06 R33）|"
                  % r0)
            print("> 注：m0/m1 用于 Condition 标识，本脚本给数值、不硬编字母。")

    print("\n> 边界：单浪归口（R33）粒度与 R5–R7（整浪铁律）不同；"
          "Directional/Non-Directional 与 Impulsive/Corrective 是不同维度。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
