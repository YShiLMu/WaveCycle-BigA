#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""单浪归口（Neely Pre-Constructive，06 R33 / 09 D33-D34 口径）。

用途：按给定观察段端点计算m2/m1（及可选m0/m1），输出Neely Rule 1–7条件分档。
m1可以是单浪或已压缩形态；m0/m2可由一个或奇数个单浪组成。观察段须由调用者
按原书Rules of Observation选定并记录确认时刻；脚本不验证其选取或完整行为期。
端点价格遵守项目R20口径，输入不是CSV。

分档边界见06 R33 / D33；Condition、Category及行为期须另行核对原书和完整序列。
用法：
    python monowave_judge.py --m1 "100:200" --m2 "200:120" --m0 "130:100"
输出：给定端点的长度、比率和条件Rule分档；行为期始终待核对，不推断完成或终止。

"""

import argparse
import math
import sys


def parse_pair(text):
    parts = text.split(":")
    if len(parts) != 2:
        raise SystemExit("[错误] 端点需为「起点价:终点价」，收到：%r" % text)
    try:
        pair = float(parts[0]), float(parts[1])
        if not all(math.isfinite(p) for p in pair):
            raise SystemExit("[错误] 端点价格必须是有限数值。")
        return pair
    except ValueError:
        raise SystemExit("[错误] 端点价格不是数字：%r" % text)


def move_len(pair):
    return abs(pair[1] - pair[0])


def rule_of(ratio):
    """回撤% → Rule 1–7（D33 分档，含边界）。"""
    if ratio < 38.2:
        return "Rule 1"
    # 仅消除二进制浮点计算误差，不代表市场比率容差。
    if math.isclose(ratio, 61.8, rel_tol=0, abs_tol=1e-9):
        return "Rule 3"
    if ratio < 61.8:
        return "Rule 2"
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
    ap.add_argument("--m2", required=True, help="m2 观察段端点（可含奇数个单浪）「起点价:终点价」")
    ap.add_argument("--m0", default=None, help="可选 m0 观察段端点「起点价:终点价」（前观察段）")
    args = ap.parse_args(argv)

    m1 = parse_pair(args.m1)
    m2 = parse_pair(args.m2)
    l1 = move_len(m1)
    l2 = move_len(m2)
    if l1 == 0:
        raise SystemExit("[错误] m1 长度为 0，无法计算比例。")
    def check_adjacent(left, right):
        if left[1] != right[0]:
            raise SystemExit("[错误] 相邻观察段端点必须相接。")
        if (left[1] - left[0]) * (right[1] - right[0]) >= 0:
            raise SystemExit("[错误] 相邻观察段须反向且长度非零。")

    check_adjacent(m1, m2)
    m0 = parse_pair(args.m0) if args.m0 else None
    if m0 is not None:
        check_adjacent(m0, m1)
    ratio = l2 / l1 * 100.0
    if not math.isfinite(ratio):
        raise SystemExit("[错误] 价格尺度超出比例计算范围。")
    rule = rule_of(ratio)
    dlabel = "待核对（缺行为期序列）"

    print("## 单浪归口（monowave_judge.py，06 R33 / D33-D34 口径）\n")
    print("| m1 长度 | m2 长度 | m2/m1 回撤% | 条件Rule分档 | 行为期状态 |")
    print("| --- | --- | --- | --- | --- |")
    print("| %.3f | %.3f | %.2f%% | %s | %s |"
          % (l1, l2, ratio, rule, dlabel))

    print("\n| 数值与行为期核对 | 判定 | 依据 |")
    print("| --- | --- | --- |")
    print("| 比率是否>100%%（仅数值对照） | %s | 回撤 %.2f%%；不证明方向行为终止 |"
          % ("是" if ratio > 100 else "否", ratio))
    print("| Non-Directional 通常终止线索（全范围161.8%或以上） | 待核对 | 缺整个非方向期序列和范围，不能用m2/m1替代 |")

    if m0 is not None:
        l0 = move_len(m0)
        if l1:
            r0 = l0 / l1 * 100.0
            print("\n| m0/m1 比例 | %.2f%% |（Condition 字母与 Category 需对照原书表，06 R33）|"
                  % r0)
            print("> 注：m0/m1 用于 Condition 标识，本脚本给数值、不硬编字母。")

    print("\n> 边界：单浪归口（R33）粒度与 R5–R7（整浪铁律）不同；"
          "Rule 1–7 是 Neely 分档名，非项目 R1–R7；未计算完整 Condition/Category 或结构序列。"
          "观察段端点及其确认时刻须另行核对，条件分档不证明正式归口通过；任意一次回撤不能确认整个行为期或其终止；Directional/Non-Directional 与 Impulsive/Corrective 是不同维度。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
