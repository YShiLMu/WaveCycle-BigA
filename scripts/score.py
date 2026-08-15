#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""八因子概率排序脚本 —— 按 G21 加权（权重 2:1:1:1:1:1:1:1，D25）计算加权总分，
按 G26 标注共振状态标签，按 G27 给出仓位闸门结论。口径唯一权威：
references/guidelines.md（G21/G26/G27）、references/defaults.md（D25）、
references/workflow.md 第 5 步第 7 节（评分维度）。

用法：
    python score.py --scheme "主方案:3:2:2:2:2:1:2:1" ^
                    --scheme "替代方案:1:2:1:0:2:0:1:0"

每个 --scheme 一段（可多段），冒号分隔 9 个字段：
    名称 : Guideline 得分 : 结构完整度 : 斐波那契共振 : 道氏一致性 :
    江恩价格共振 : 江恩时间共振 : 蜡烛图信号 : 失效距离

口径（references/workflow.md 第 5 步第 7 节 7.2）：
- Guideline 得分 = 原始累计分（命中 +1 / 不适用 0 / 违反 −1），任意整数，加权 ×2；
- 其余七因子各取 0–2 分（禁止 10 分制、5 分制等其他分制，脚本直接报错）：
  结构完整度 2=细分清晰且级别嵌套自洽、1=基本清晰、0=部分待确认；
  斐波那契共振 2=关键比率命中 ≥2 个、1=1 个、0=0 个；
  道氏一致性 2=一致且互证成立、1=一致但互证背离、0=与道氏状态矛盾（G26 背离）；
  江恩价格共振 2=落入江恩-斐波那契共振区、1=单体系命中、0=无；
  江恩时间共振 2=预登记江恩时间窗且与斐波那契时间带重叠、1=仅一体系、0=无；
  蜡烛图信号 2=方向一致的明确转折/确认信号、1=弱信号、0=无信号或矛盾；
  失效距离 2=≥1.618× 基准浪长度、1=0.618×–1.618×、0=<0.618×。
- 道氏一致性可写 NA：标的为大盘指数本身，因子从分母剔除（不参与总分与共振计数）。

排序：加权总分降序；总分相同按失效距离因子降序（更远优先）；再相同按名称升序，
并提示按 D7「失效距离相近」判定带（相对差 < 当前价格 10%）人工复核。

输出：每方案明细 + 共振状态标签 + 仓位闸门结论（G27）+ 最终排名。
"""
import argparse
import sys

# 因子名（按 workflow 第 5 步第 7 节 7.2 顺序）
FACTORS = ["结构完整度", "斐波那契共振", "道氏一致性", "江恩价格共振",
           "江恩时间共振", "蜡烛图信号", "失效距离"]


def parse_scheme(s):
    parts = s.split(":")
    if len(parts) != 9:
        raise SystemExit(
            "scheme 应为 9 个冒号分隔字段（名称:Guideline:结构:斐波:道氏:江恩价:江恩时:蜡烛:失效距离），收到: %s" % s)
    name = parts[0].strip()
    if not name:
        raise SystemExit("scheme 名称不能为空：%s" % s)
    try:
        guideline = int(parts[1])
    except ValueError:
        raise SystemExit("Guideline 得分必须为整数（命中 +1/不适用 0/违反 −1 累计）：%s" % s)
    scores = []
    for label, v in zip(FACTORS, parts[2:]):
        v = v.strip()
        if label == "道氏一致性" and v.upper() == "NA":
            scores.append("NA")
            continue
        try:
            n = float(v)
        except ValueError:
            raise SystemExit("%s 必须是 0/1/2（道氏一致性可为 NA）：%s" % (label, s))
        if n != int(n) or not (0 <= n <= 2):
            raise SystemExit("%s 必须是 0/1/2（禁止 10 分制、5 分制等其他分制）：%s" % (label, s))
        scores.append(int(n))
    return {"name": name, "guideline": guideline, "factors": scores}


def resonance_label(f):
    """G26 四态：背离（道氏方向与数浪矛盾 = 道氏因子 0）；三共振/双共振/单信号
    按道氏一致、江恩价格共振、江恩时间共振中计 2 分的项数判定（道氏 NA 不参与）。"""
    dow = f[2]
    if dow == 0:
        return "背离"
    n2 = int(dow == 2) + int(f[3] == 2) + int(f[4] == 2)
    if n2 >= 3:
        return "三共振"
    if n2 == 2:
        return "双共振"
    return "单信号"


def gate_conclusion(f):
    """G27 仓位闸门结论（在 04 生成报告三档基础档位之上的附加约束）。"""
    label = resonance_label(f)
    if label == "背离":
        return "背离：强制观望（不论得分差多大）"
    if label == "三共振":
        return "三共振：允许再升一档（相对双共振，累计最多升两档）"
    if label == "双共振":
        if f[2] == 2:
            return "双共振（含道氏一致）：允许升一档"
        return "双共振（不含道氏一致）：不干预"
    return "单信号：封顶轻仓试探"


def main(argv=None):
    ap = argparse.ArgumentParser(description="八因子概率排序（G21 加权 + G26 共振 + G27 闸门）")
    ap.add_argument("--scheme", action="append", required=True, metavar="S",
                    help="方案评分段（可多次）：名称:Guideline:结构:斐波:道氏:江恩价:江恩时:蜡烛:失效距离")
    args = ap.parse_args(argv)

    schemes = [parse_scheme(s) for s in args.scheme]
    for sc in schemes:
        dow = sc["factors"][2]
        base = 2 * sc["guideline"] + sum(v for v in sc["factors"] if v != "NA")
        sc["total"] = base
        sc["dow"] = dow
        sc["label"] = resonance_label(sc["factors"])
        sc["gate"] = gate_conclusion(sc["factors"])

    schemes.sort(key=lambda x: (-x["total"], -(x["factors"][6] if x["factors"][6] != "NA" else -1), x["name"]))

    print("== 八因子评分（G21 加权 2:1:1:1:1:1:1:1，D25；各因子 0–2 分，道氏 NA=大盘标的剔除）==")
    for sc in schemes:
        f = sc["factors"]
        print("  %s" % sc["name"])
        print("    Guideline 原始分 %+d（×2=%d）｜结构 %s｜斐波 %s｜道氏 %s｜江恩价 %s｜江恩时 %s｜蜡烛 %s｜失效距离 %s"
              % (sc["guideline"], 2 * sc["guideline"],
                 *[v if v != "NA" else "NA" for v in f]))
        denom = 16 if sc["dow"] == "NA" else 18
        print("    加权总分 %d/%d%s ｜ 共振状态：%s ｜ 闸门：%s"
              % (sc["total"], denom,
                 "（道氏 NA：分母剔除，参考满分 16）" if sc["dow"] == "NA" else "",
                 sc["label"], sc["gate"]))

    print("\n== 排序 ==")
    for rank, sc in enumerate(schemes, 1):
        print("  %d. %s —— 总分 %d，失效距离 %s，%s"
              % (rank, sc["name"], sc["total"],
                 sc["factors"][6] if sc["factors"][6] != "NA" else "NA", sc["label"]))

    totals = [sc["total"] for sc in schemes]
    if len(set(totals)) < len(totals):
        same = [sc["name"] for sc in schemes if totals.count(sc["total"]) > 1]
        print("\n[提示] 存在同分方案：%s —— 同分时按失效距离因子优先，"
              "若仍相同请按 D7「失效距离相近」判定带（相对差 < 当前价格 10%%）人工复核。"
              % "、".join(same))


if __name__ == "__main__":
    sys.exit(main())
