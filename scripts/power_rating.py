#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Power Rating 功率评级查询（Neely 修正浪量化评级，16 口径 / D35）。

用途：根据**已完成修正浪的类型** → 输出该修正浪的功率评级（+3…0…-3，按
"向上完成 / 向下完成"两种方向）+ "被下一形态回撤的预期比例"。
——类型由模型数浪确定（脚本不识别形态），脚本只做"查表 + 回撤预测"。

用法：
    python power_rating.py --type "Double Zigzag"
    python power_rating.py --type "Zigzag"

--type 取值（16 功率评级表所列 19 种）：
    Triple Zigzag / Triple Combination / Triple Flat
    Double Zigzag / Double Combination / Double Flat
    Elongated Zigzag / Elongated Flat / Zigzag
    B-Failure / Common / C-Failure
    Irregular / Irregular Failure
    Double Three / Triple Three / Running Correction
    Double Three-Running / Triple Three-Running

输出：markdown 表（类型 | 向上完成 | 向下完成 | 预期回撤）+ 关联提示。
回撤预测：评级 0 → 约 100%；±1 → ≤90%；±2 → ≤80%；±3 → 60–70%。
"""

import argparse
import sys

# (类型, 向上完成评级, 向下完成评级)
RATINGS = [
    ("Triple Zigzag", 3, -3),
    ("Triple Combination", 3, -3),
    ("Triple Flat", 3, -3),
    ("Double Zigzag", 2, -2),
    ("Double Combination", 2, -2),
    ("Double Flat", 2, -2),
    ("Elongated Zigzag", 1, -1),
    ("Elongated Flat", 1, -1),
    ("Zigzag", 1, -1),
    ("B-Failure", 0, 0),
    ("Common", 0, 0),
    ("C-Failure", 0, 0),
    ("Irregular", -1, 1),
    ("Irregular Failure", -1, 1),
    ("Double Three", -2, 2),
    ("Triple Three", -2, 2),
    ("Running Correction", -2, 2),
    ("Double Three-Running", -3, 3),
    ("Triple Three-Running", -3, 3),
]

# Triangle 例外：下列变体在三角形内评级归 0（16 表注）
TRI_EXC = {"Elongated Zigzag", "Elongated Flat", "Zigzag"}


def retrace_label(rating):
    """评级 → 下一形态预期回撤比例（16 第 3 节 / D35）。"""
    a = abs(rating)
    if a == 0:
        return "约 100%（可被完全回撤）"
    if a == 1:
        return "不超过约 90%"
    if a == 2:
        return "不超过约 80%"
    return "最少，约 60–70%"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Power Rating 功率评级查询（16 / D35）")
    ap.add_argument("--type", required=True, help="修正浪类型，如 \"Double Zigzag\"")
    args = ap.parse_args(argv)

    key = args.type.strip()
    hit = next((r for r in RATINGS if r[0].lower() == key.lower()), None)
    if hit is None:
        raise SystemExit("[错误] 未知修正浪类型：%r（可用：%s）"
                         % (args.type, ", ".join(r[0] for r in RATINGS)))

    name, up, down = hit
    print("## Power Rating 功率评级（power_rating.py，16 口径 / D35）\n")
    print("| 类型 | 向上完成 | 向下完成 | 预期回撤（按绝对值） |")
    print("| --- | --- | --- | --- |")
    print("| %s | %+d | %+d | %s |" % (name, up, down, retrace_label(up)))
    if name in TRI_EXC:
        print("\n> 提示：%s 在三角形（Triangle）内部分变体评级归 0（16 表注）。" % name)
    print("\n> 应用：\u00b1(1\u20133) 的向上修正浪**不应**被下一同级形态完全回撤；"
          "若被「更接近 0 但同级」形态完全回撤 → 市场在酝酿 Triangle 或 Terminal。"
          "Power Rating 仅作波浪层内部量化参考，**不并入 8 因子权重（D25）**。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
