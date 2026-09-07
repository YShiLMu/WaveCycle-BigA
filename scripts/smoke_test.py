#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""冒烟测试 —— 验证 pandas / matplotlib / 中文字体可用，且各脚本主流程跑通。

    python smoke_test.py [--keep]

覆盖：
1. key_levels.py —— 合成 CSV（含跳空缺口、长上影/长下影候选）跑三类锚点输出；
   坏数据 CSV（high<low、日期乱序）验证数据自检拦截（应报错退出，workflow 1.5 口径）；
2. ew_chart.py —— 绘制 2 张标准图（每方案一张全景，见 naming.CHART_VIEWS；中文标题、浪段方向 auto/显式、失效价位、
   江恩 --gann-auto-scale 自动刻度、--path 连续浪路径），验证 PNG 非空生成；
3. embed_report_images.py —— 标准 4 图模式与单方案防御 2 图模式各建一个归档
   文件夹，跑内嵌与校验（含模板头部特征注释校验、替代方案图区"不适用"标记）；
4. score.py —— 八因子加权排序与共振标签；
5. swings.py —— 合成 CSV 跑分形摆动点提取、--tail 截断与 --chart-args 参数串；
6. init_archive.py —— 建档（图表/ 子目录、幂等拦截）与 --print-dir 单行输出；
7. gen_report_web.py / gen_report_md.py —— data.json 渲染网页与 md（stdout 无 {{残留}}、含模板特征注释）；
8. data_check.py —— 自检表 + 四要素输出、缺 --fq/--source 判不通过、坏数据拦截、
   OHLC 含 NaN/全 NaN 时极值与收盘不输出 nan 假事实；
9. invalidation_check.py —— 已触发已确认 / 未触发 / --since 过滤三态判定；
10. swings.py --dow —— 道氏状态读数（3 点判 2 点定 + DO4 事实 + 无 volume 降级）；
11. rule_check.py —— R5–R7 通过/违反、下跌镜像、缺浪不适用、非法 --wave 报错；
12. preflight.py —— 三段流水线顺序产出 + data_check 不通过即终止（exit 1）；
13. ew_chart._seg_direction —— R20 极端价位判向口径直测（长上影 close 回落
    但 high 新高必须判上行）；
14. 核心纯函数直测 —— fractal_pivots 交替化、cluster_levels 聚类、
    check_level 最后一根触及边界、gann_auto_scale 分档。

退出码：0 = 全部通过；1 = 任一失败。--keep 保留临时产物目录（默认删除）。
"""
import argparse
import datetime
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile

from naming import IMAGE_KEYS, chart_png

import pandas as pd

from naming import HTML_TOKENS, IMAGE_KEYS, IMAGE_PLACEHOLDERS

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
HTML_TEMPLATE = os.path.join(SKILL, "assets", "网页报告_web_report.html")
FAILED = []


def run(cmd, stdin_text=None):
    env = dict(os.environ)
    env.setdefault("PYTHONUTF8", "1")  # 子进程输出固定 UTF-8，避免 Windows 管道默认 GBK 导致中文检查乱码误判
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env,
                          input=stdin_text)
    return proc.returncode, proc.stdout, proc.stderr


def check(name, cond, detail=""):
    tag = "PASS" if cond else "FAIL"
    print("  [%s] %s%s" % (tag, name, (" —— " + detail) if detail else ""))
    if not cond:
        FAILED.append(name)


def gen_csv(path, n=320, seed=7):
    """生成合成 OHLC：随机游走 + 一处长上影 + 一处长下影 + 一处跳空缺口。"""
    rng = random.Random(seed)
    rows = []
    price = 100.0
    date = datetime.date(2024, 1, 1)
    prev_hi = None
    for i in range(n):
        o = price
        r = rng.uniform(-0.02, 0.02)
        c = o * (1 + r)
        hi = max(o, c) * (1 + rng.uniform(0.001, 0.012))
        lo = min(o, c) * (1 - rng.uniform(0.001, 0.012))
        if i == 60:  # 长上影（流星线口径：上影 ≥ 实体 ×2）
            c = o * 1.0005
            hi = max(o, c) * 1.035
            lo = min(o, c) * 0.998
        elif i == 90:  # 长下影（锤子线口径）
            c = o * 0.9995
            lo = min(o, c) * 0.965
            hi = max(o, c) * 1.002
        elif i == 200 and prev_hi is not None:  # 上跳缺口
            lo = prev_hi * 1.02
            o = lo * 1.005
            c = o * 1.004
            hi = max(o, c) * 1.01
        rows.append((date.isoformat(), round(o, 2), round(hi, 2), round(lo, 2),
                     round(c, 2), rng.randint(1000, 9999)))
        price = c
        prev_hi = hi
        date += datetime.timedelta(days=1)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("date,open,high,low,close,volume\n")
        for r in rows:
            f.write("%s,%s,%s,%s,%s,%s\n" % r)
    return rows


def gen_md(path, n_img=2):
    keys = list(IMAGE_KEYS)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("# 分析报告（冒烟测试）\n\n## 2 主方案\n\n")
        for name, fn in keys[:n_img]:
            f.write("![%s](图表/%s)\n\n" % (name, fn))


def gen_html(path):
    with open(HTML_TEMPLATE, encoding="utf-8") as f:
        text = f.read()
    text = re.sub(r"\{\{([^}]+)\}\}",
                  lambda m: m.group(0) if m.group(1) in IMAGE_PLACEHOLDERS else "X",
                  text)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def main(argv=None):
    parser = argparse.ArgumentParser(description="wavecycle 三脚本冒烟测试")
    parser.add_argument("--keep", action="store_true", help="保留临时产物目录")
    args = parser.parse_args(argv)

    tmp = tempfile.mkdtemp(prefix="wavecycle_smoke_")
    print("临时目录：%s" % tmp)
    csv_path = os.path.join(tmp, "sample.csv")
    rows = gen_csv(csv_path)
    last_close = rows[-1][4]

    # ---- 1. key_levels.py ----
    print("== 1. key_levels.py（三类锚点 + 数据自检）==")
    code, out, err = run([sys.executable, os.path.join(HERE, "key_levels.py"),
                          "--csv", csv_path])
    check("锚点检测正常退出", code == 0, err.strip()[:200])
    check("输出含前高/前低节", "== 1. 前高/前低" in out)
    check("输出含跳空缺口节", "== 2. 跳空缺口" in out)
    check("输出含多日未破节", "== 3. 多日未破压力/支撑位" in out)
    check("检出跳空缺口", "上跳" in out)

    bad_csv = os.path.join(tmp, "bad.csv")
    with open(bad_csv, "w", encoding="utf-8", newline="\n") as f:
        f.write("date,open,high,low,close\n")
        f.write("2024-01-01,100,101,99,100.5\n")
        f.write("2024-01-02,100,99,101,100\n")  # high < low
    code, out, err = run([sys.executable, os.path.join(HERE, "key_levels.py"),
                          "--csv", bad_csv])
    check("坏数据（high<low）被数据自检拦截", code != 0 and "数据自检失败" in (out + err),
          (out + err).strip()[:200])

    bad_csv2 = os.path.join(tmp, "bad2.csv")
    with open(bad_csv2, "w", encoding="utf-8", newline="\n") as f:
        f.write("date,open,high,low,close\n")
        f.write("2024-01-02,100,101,99,100.5\n")
        f.write("2024-01-01,100,101,99,100.5\n")  # 日期乱序
    code, out, err = run([sys.executable, os.path.join(HERE, "key_levels.py"),
                          "--csv", bad_csv2])
    check("坏数据（日期乱序）被数据自检拦截", code != 0 and "数据自检失败" in (out + err),
          (out + err).strip()[:200])

    # ---- 2. ew_chart.py ----
    print("== 2. ew_chart.py（2 张标准图[全景]：中文标题/浪段方向/失效价位/江恩自动刻度）==")
    charts = {
        chart_png("主方案", "全景"): (["--waves",
                             "1:0:60:Impulse（推动浪）:up",
                             "2:60:110:Zigzag（锯齿形）:down",
                             "3:110:220:Impulse（延长浪）:up",
                             "4:220:260:Flat（平台形）:down",
                             "5:260:319:Impulse（推动浪）:up",
                             "--invalid", "130:跌破 130（第 1 浪高点，R7）即失效",
                             "--current", str(last_close),
                             "--gann", "10:110:up", "--gann-auto-scale",
                             "--path", "1@0,2@60,3@110,4@220,5@260,A@319"],
                            "日线级别 · Intermediate · 主方案：五浪推动（Impulse）"),
        chart_png("替代方案", "全景"): (["--waves",
                               "A:0:60:Zigzag（锯齿形）:up",
                               "B:60:110:Correction（调整浪）:down",
                               "C:110:319:Impulse（推动浪）:up",
                               "--invalid", "95:跌破 95（A 浪起点，R5）即失效",
                               "--current", str(last_close)],
                              "日线级别 · Intermediate · 替代方案：A-B-C"),
    }
    chart_dir = os.path.join(tmp, "图表4")
    os.makedirs(chart_dir)
    for fn, (extra, title) in charts.items():
        code, out, err = run([sys.executable, os.path.join(HERE, "ew_chart.py"),
                              "--csv", csv_path, "--out", os.path.join(chart_dir, fn),
                              "--title", title] + extra)
        png = os.path.join(chart_dir, fn)
        check("生成 %s" % fn, code == 0 and os.path.getsize(png) > 0, err.strip()[:200])

    # ---- 2b. ew_chart.py --path 层级一致性：分层级正例通过 / 混层级硬拒绝 ----
    print("== 2b. ew_chart.py --path 层级一致性（一条=一个浪链，混层级拒绝出图）==")
    layered_png = os.path.join(chart_dir, "层级正例_全景.png")
    code, out, err = run([sys.executable, os.path.join(HERE, "ew_chart.py"),
                          "--csv", csv_path, "--out", layered_png, "--title", "层级正例",
                          "--start", "0",
                          "--path", "[I]@0,[II]@60",            # 第1级白链（无连字符）
                          "--path", "1-1@0,1-2@60,1-3@110"])      # 第2级叠层（1连字符）
    check("分层级多条 --path 正常出图", code == 0 and os.path.getsize(layered_png) > 0,
          err.strip()[:200])
    mixed_png = os.path.join(chart_dir, "混层级_应拒绝.png")
    code, out, err = run([sys.executable, os.path.join(HERE, "ew_chart.py"),
                          "--csv", csv_path, "--out", mixed_png, "--title", "混层级应拒绝",
                          "--start", "0",
                          "--path", "[I]@0,1-1@60"])              # 1级+2级 混一条 --path
    check("混层级 --path 被拒绝(exit!=0 且提示层级)", code != 0 and "层级" in (out + err),
          (out + err).strip()[:200])

    # ---- 3. embed_report_images.py：2 图标准模式 + 1 图防御模式 ----
    print("== 3. embed_report_images.py（2 图标准模式 + 1 图防御模式）==")
    for case, n_img in (("标准2图", 2), ("防御1图", 1)):
        folder = os.path.join(tmp, "case_" + case)
        os.makedirs(os.path.join(folder, "图表"))
        for fn in list(charts)[:n_img]:
            shutil.copy2(os.path.join(chart_dir, fn), os.path.join(folder, "图表", fn))
        gen_md(os.path.join(folder, "分析报告_冒烟_000000_20260101.md"), n_img)
        gen_html(os.path.join(folder, "网页报告_冒烟_000000_20260101.html"))
        code, out, err = run([sys.executable, os.path.join(HERE, "embed_report_images.py"), folder])
        check("%s 内嵌校验通过" % case, code == 0, (out + err).strip()[:300])
        html = open(os.path.join(folder, "网页报告_冒烟_000000_20260101.html"),
                    encoding="utf-8").read()
        check("%s html 内嵌 %d 张" % (case, n_img),
              html.count("data:image/png;base64,") == n_img)
        if n_img == 2:
            if case == "防御1图":
                check("防御1图 替代方案图区标记不适用", "单方案防御模式" in html)
        md = open(os.path.join(folder, "分析报告_冒烟_000000_20260101.md"),
                  encoding="utf-8").read()
        check("%s md 内嵌 %d 张" % (case, n_img),
              md.count("data:image/png;base64,") == n_img)

    # ---- 4. score.py 快速自检 ----
    print("== 4. score.py（八因子加权 + 共振标签 + 闸门）==")
    code, out, err = run([sys.executable, os.path.join(HERE, "score.py"),
                          "--scheme", "主方案:3:2:2:2:2:1:2:1",
                          "--scheme", "替代方案:1:2:1:0:2:0:1:0"])
    check("score.py 正常退出并输出排序", code == 0 and "加权总分" in out and "背离" in out,
          (out + err).strip()[:200])

    # ---- 5. swings.py ----
    print("== 5. swings.py（分形摆动点 + --tail + --chart-args 参数串）==")
    code, out, err = run([sys.executable, os.path.join(HERE, "swings.py"),
                          "--csv", csv_path, "--tail", "5"])
    check("摆动点提取正常退出", code == 0, err.strip()[:200])
    check("输出含摆动点表头", "摆动点" in out)
    check("--tail 5 截断生效", "共 5 个" in out, out.strip()[:120])
    code, out, err = run([sys.executable, os.path.join(HERE, "swings.py"),
                          "--csv", csv_path, "--chart-args"])
    check("--chart-args 输出 --pivot 参数串", code == 0 and "--pivot" in out,
          (out + err).strip()[:200])
    code, out, err = run([sys.executable, os.path.join(HERE, "swings.py"),
                          "--csv", csv_path, "--weekly", "--tail", "3"])
    check("--weekly 周线聚合正常退出", code == 0 and "摆动点" in out, (out + err).strip()[:200])

    # ---- 6. init_archive.py ----
    print("== 6. init_archive.py（建档 + --print-dir 单行输出 + 幂等拦截）==")
    arch_root = os.path.abspath(os.path.join(tmp, "归档"))
    code, out, err = run([sys.executable, os.path.join(HERE, "init_archive.py"),
                          "--name", "冒烟", "--code", "000000",
                          "--root", arch_root, "--time", "20260101_1200"])
    folder = os.path.abspath(os.path.join(arch_root, "冒烟_000000_20260101_1200"))
    check("建档正常退出", code == 0, err.strip()[:200])
    check("建档路径确实存在", os.path.isdir(folder), folder)
    check("图表/ 子目录已创建", os.path.isdir(os.path.join(folder, "图表")))
    check("多行输出含标准文件名", "分析报告_冒烟_000000_20260101_1200.md" in out)
    code, out, err = run([sys.executable, os.path.join(HERE, "init_archive.py"),
                          "--name", "冒烟", "--code", "000000",
                          "--root", arch_root, "--time", "20260101_1200"])
    check("重复建档被幂等拦截", code != 0 and "已存在" in (out + err), (out + err).strip()[:200])
    code, out, err = run([sys.executable, os.path.join(HERE, "init_archive.py"),
                          "--name", "冒烟", "--code", "000000",
                          "--root", arch_root, "--time", "20260101_1200",
                          "--force", "--print-dir"])
    printed = out.strip()
    check("--print-dir 单行输出且 --force 复用",
          code == 0 and printed == folder, printed[:200])

    # ---- 7. gen_report_web / gen_report_md（data.json 走 stdin，零落盘）----
    print("== 7. gen_report_web.py / gen_report_md.py（stdin data.json 渲染网页与 md）==")
    data = {
        "标的名称": "冒烟", "标的代码": "000000", "时间戳": "20260101_1200",
        "细分深度": 2, "细分深度来源": "用户确认-2层",
        "fields": {
            "分析日期": "2026-01-01", "分析级别": "日线级别", "收盘价": str(last_close),
            "主方案说明": "测试", "主方案失效": "测试", "替代方案": "测试",
            "概率说明": "测试", "概率结论": "测试", "交易计划": "测试",
            "风险提示": "测试", "更新跟踪": "测试",
            "数据来源": "合成数据", "生成时间": "2026-01-01 12:00",
        },
        "tables": {
            "分析前提": [{"项": "细分深度来源", "内容": "用户确认-2层"},
                        {"项": "级别", "内容": "日线级别"}],
            "主方案数浪": [{"浪": "1", "端点": "100/2024-01-01 → 160/2024-02-01", "结构": "Impulse", "说明": "测试"}],
            "neely参考": [{"脚本": "结构阶梯", "输出": "通过", "意义": "测试"}],
            "八因子": [{"因子": "波浪 Rule", "主方案": "通过", "替代方案": "通过"}],
            "失效价位": [{"方案": "主方案", "失效价位": "130", "规则依据": "R7", "触发后果": "测试"}],
        },
        "简明分析说明": {
            "大级别浪": "第4浪", "小级别浪": "第4浪的b浪",
            "neely得分": 1, "neely强度": "中等", "结论": "偏多",
            "端点": [{"价": 100, "日": "2024-01-01"}, {"价": 160, "日": "2024-02-01"}],
        },
    }
    payload = json.dumps(data, ensure_ascii=False)
    # 负例：缺"细分深度来源"应被校验拦截（06 R35/D37，未确认深度不得出报告）
    bad_payload = json.dumps({k: v for k, v in data.items() if k != "细分深度来源"},
                             ensure_ascii=False)
    code, out, err = run([sys.executable, os.path.join(HERE, "gen_report_md.py"),
                          "--data", "-"], stdin_text=bad_payload)
    check("缺细分深度来源被拦截（R35/D37）", code != 0 and "细分深度来源" in err,
          (out + err).strip()[:150])
    # 网页
    code, out, err = run([sys.executable, os.path.join(HERE, "gen_report_web.py"),
                          "--data", "-"], stdin_text=payload)
    img_slugs = IMAGE_PLACEHOLDERS
    leftover = [m for m in re.findall(r"\{\{([^}]+)\}\}", out) if m not in img_slugs]
    check("stdin 渲染网页正常退出", code == 0, err.strip()[:200])
    check("渲染含模板特征注释", "波浪理论网页报告模板" in out)
    check("stdout 无非图片 {{残留}}", code == 0 and not leftover, str(leftover)[:200])
    # md
    code, out, err = run([sys.executable, os.path.join(HERE, "gen_report_md.py"),
                          "--data", "-"], stdin_text=payload)
    md_leftover = re.findall(r"\{\{([^}]+)\}\}", out)
    check("stdin 渲染分析报告 md 正常退出", code == 0, err.strip()[:200])
    check("md 渲染含标题特征", code == 0 and "Elliott Wave 分析报告" in out, (out + err).strip()[:150])
    check("md 无未替换 {{残留}}", code == 0 and not md_leftover, str(md_leftover)[:200])

    # ---- 8. data_check.py ----
    print("== 8. data_check.py（自检表 + 四要素 + 坏数据披露）==")
    code, out, err = run([sys.executable, os.path.join(HERE, "data_check.py"),
                          "--csv", csv_path, "--source", "合成数据", "--fq", "qfq"])
    check("自检正常退出（exit 0）", code == 0, (out + err).strip()[:200])
    check("输出自检表与四要素", "## 数据自检表" in out and "## 数据基准（四要素）" in out)
    check("全部通过", "自检全部通过" in out)
    check("披露循环覆盖素材", "循环覆盖判定素材" in out)
    code, out, err = run([sys.executable, os.path.join(HERE, "data_check.py"), "--csv", csv_path])
    check("缺 --fq/--source 判不通过（exit 1）",
          code == 1 and "未标注" in out and "复权口径" in out, out.strip()[:150])
    bad_csv3 = os.path.join(tmp, "bad3.csv")
    pd.DataFrame({"date": ["2024-01-01", "2024-01-02"],
                  "open": [0.0, 100.0], "high": [0.0, 101.0],
                  "low": [0.0, 99.0], "close": [3926.76, 100.5]}).to_csv(bad_csv3, index=False)
    code, out, err = run([sys.executable, os.path.join(HERE, "data_check.py"),
                          "--csv", bad_csv3, "--source", "测试", "--fq", "none"])
    check("坏数据记为不通过而非崩溃（exit 1）",
          code == 1 and "不通过" in out and "close 超出" in out, out.strip()[:150])
    nan_csv = os.path.join(tmp, "bad4_nan.csv")
    nan = float("nan")
    pd.DataFrame({"date": ["2024-01-01", "2024-01-02", "2024-01-03"],
                  "open": [100.0, nan, 102.0], "high": [101.0, nan, 103.0],
                  "low": [99.0, nan, 101.0], "close": [100.5, nan, 102.5]}).to_csv(nan_csv, index=False)
    code, out, err = run([sys.executable, os.path.join(HERE, "data_check.py"),
                          "--csv", nan_csv, "--source", "测试", "--fq", "none"])
    check("OHLC 含 NaN 记为不通过且极值不输出 nan（exit 1）",
          code == 1 and "不通过" in out and "nan" not in out.lower(), out.strip()[:200])
    nan_all_csv = os.path.join(tmp, "bad5_nan_all.csv")
    pd.DataFrame({"date": ["2024-01-01"],
                  "open": [nan], "high": [nan], "low": [nan], "close": [nan]}).to_csv(nan_all_csv, index=False)
    code, out, err = run([sys.executable, os.path.join(HERE, "data_check.py"),
                          "--csv", nan_all_csv, "--source", "测试", "--fq", "none"])
    check("OHLC 全 NaN 时极值/收盘缺失分支（exit 1，无 nan 输出）",
          code == 1 and "无可靠极值" in out and "nan" not in out.lower(), out.strip()[:200])

    # ---- 9. invalidation_check.py ----
    print("== 9. invalidation_check.py（触发/确认/未触发/--since）==")
    inv_csv = os.path.join(tmp, "inv.csv")
    pd.DataFrame({"date": ["2024-01-0%d" % d for d in range(1, 7)],
                  "open": [100.0, 102.0, 107.0, 105.0, 100.0, 97.0],
                  "high": [105.0, 108.0, 110.0, 106.0, 101.0, 99.0],
                  "low": [95.0, 100.0, 104.0, 99.0, 96.0, 95.0],
                  "close": [102.0, 107.0, 105.0, 100.0, 97.0, 98.0]}).to_csv(inv_csv, index=False)
    code, out, err = run([sys.executable, os.path.join(HERE, "invalidation_check.py"),
                          "--csv", inv_csv,
                          "--level", "99|break-down|主方案|规则失效|R7",
                          "--level", "94|break-down|主方案|结构失效|06 6.6注",
                          "--level", "112|break-up|替代方案|规则失效|R19"])
    check("判定正常退出", code == 0, (out + err).strip()[:200])
    check("已触发已确认（99，首根已触及，确认于 2024-01-06）",
          "已触发且已确认" in out and "2024-01-01" in out and "2024-01-06" in out)
    check("未触发（94）", "未触发" in out)
    check("升破方向未触发（112）", "112.000" in out)
    check("触发摘要计数 1/3（1 个已确认）",
          "1/3 个失效价位已触发，其中 1 个已过确认窗口" in out)
    code, out, err = run([sys.executable, os.path.join(HERE, "invalidation_check.py"),
                          "--csv", inv_csv, "--since", "2024-01-05",
                          "--level", "99|break-down|主方案|规则失效|R7"])
    check("--since 过滤生效", code == 0 and "2024-01-05" in out and "2024-01-04" not in out,
          out.strip()[:150])
    code, out, err = run([sys.executable, os.path.join(HERE, "invalidation_check.py"),
                          "--csv", inv_csv, "--level", "99|向下|主方案|R7"])
    check("非法 --level 报错退出", code != 0 and "5 段" in (out + err), (out + err).strip()[:150])

    # ---- 10. swings.py --dow ----
    print("== 10. swings.py --dow（道氏状态读数 + DO4 + 无 volume 降级）==")
    code, out, err = run([sys.executable, os.path.join(HERE, "swings.py"),
                          "--csv", csv_path, "--dow"])
    check("--dow 正常退出", code == 0, err.strip()[:200])
    check("输出道氏读数四要素", all(s in out for s in
          ("道氏趋势状态读数", "高点：", "低点：", "状态：", "成交量：")), out[-400:])
    check("3 点判 2 点定口径", "3 点判、2 点定" in out)
    code, out, err = run([sys.executable, os.path.join(HERE, "swings.py"),
                          "--csv", inv_csv, "--dow", "--k", "1"])
    check("无 volume 列 DO4 不适用", code == 0 and "DO4 不适用" in out, out[-200:])

    # ---- 11. rule_check.py ----
    print("== 11. rule_check.py（R5/R6/R7/R17/R29 数值判定）==")
    code, out, err = run([sys.executable, os.path.join(HERE, "rule_check.py"),
                          "--wave", "1:100:160", "--wave", "2:160:130",
                          "--wave", "3:130:220", "--wave", "4:220:185", "--wave", "5:185:190"])
    check("上升推动全通过（exit 0）",
          code == 0 and out.count("通过") >= 3 and "R17/R29" in out, (out + err).strip()[:200])
    code, out, err = run([sys.executable, os.path.join(HERE, "rule_check.py"),
                          "--wave", "1:100:160", "--wave", "2:160:130",
                          "--wave", "3:130:220", "--wave", "4:220:155"])
    check("R7 违反（exit 1）", code == 1 and "| R7 | 违反 |" in out, out.strip()[:200])
    code, out, err = run([sys.executable, os.path.join(HERE, "rule_check.py"),
                          "--wave", "1:100:80", "--wave", "2:80:90",
                          "--wave", "3:90:55", "--wave", "4:55:70", "--wave", "5:70:60"])
    check("下跌推动镜像识别", code == 0 and "下跌推动" in out and "| R7 | 通过 |" in out,
          out.strip()[:200])
    code, out, err = run([sys.executable, os.path.join(HERE, "rule_check.py"),
                          "--wave", "1:100:160", "--wave", "2:160:130"])
    check("缺第 3 浪报错退出", code != 0 and "缺少第 3 浪" in (out + err), (out + err).strip()[:150])
    code, out, err = run([sys.executable, os.path.join(HERE, "rule_check.py"),
                          "--wave", "1:100:160", "--wave", "2:160:130", "--wave", "3:abc:220"])
    check("非法价格段报错退出", code != 0 and "不是数字" in (out + err), (out + err).strip()[:150])

    # ---- 12. preflight.py ----
    print("== 12. preflight.py（三段流水线 + data_check 终止）==")
    code, out, err = run([sys.executable, os.path.join(HERE, "preflight.py"),
                          "--csv", csv_path, "--source", "合成数据", "--fq", "qfq", "--tail", "4"])
    check("流水线正常完成（exit 0）", code == 0, err.strip()[:200])
    check("三段顺序产出", all(s in out for s in
          ("preflight 1/3", "preflight 2/3", "preflight 3/3", "preflight 完成")))
    check("含自检表与道氏读数", "## 数据自检表" in out and "状态：" in out)
    pf_bad = os.path.join(tmp, "pf_bad.csv")
    pd.DataFrame({"date": ["2024-01-01"], "open": [0.0], "high": [0.0],
                  "low": [0.0], "close": [100.0]}).to_csv(pf_bad, index=False)
    code, out, err = run([sys.executable, os.path.join(HERE, "preflight.py"),
                          "--csv", pf_bad, "--source", "t", "--fq", "none"])
    check("data_check 不通过即终止（exit 1，不跑 swings）",
          code == 1 and "preflight 终止" in out and "preflight 2/3" not in out,
          out.strip()[-200:])

    # ---- 13. ew_chart._seg_direction 判向口径直测 ----
    print("== 13. ew_chart._seg_direction（R20 极端价位判向口径）==")
    sys.path.insert(0, HERE)
    import ew_chart as _ew
    mini = pd.DataFrame({
        "high": [101.0, 103.0, 106.0, 104.0, 107.0, 107.0],
        "low": [99.0, 100.0, 101.0, 98.0, 100.0, 99.5],
        "close": [100.5, 102.0, 101.5, 99.0, 105.0, 98.0],
    })
    check("终点 high/low 均高 → 上行", _ew._seg_direction(mini, 0, 1) is True)
    check("终点 high/low 均低 → 下行", _ew._seg_direction(mini, 2, 3) is False)
    check("长上影（close 回落但 high 新高）→ 上行（原 --path 用收盘判向会判反的 bug 场景）",
          _ew._seg_direction(mini, 1, 2) is True)
    check("区间重叠回退收盘比较（close 升 → 上行）", _ew._seg_direction(mini, 2, 4) is True)
    check("区间重叠回退收盘比较（close 降 → 下行）", _ew._seg_direction(mini, 1, 5) is False)

    # ---- 14. 核心纯函数直测（swings/key_levels/invalidation_check/ew_chart）----
    print("== 14. 核心纯函数直测（分形交替/聚类容差/失效判定边界/江恩分档）==")
    import swings as _sw
    import key_levels as _kl
    import invalidation_check as _iv

    piv = _sw.fractal_pivots([2, 5, 2, 5, 2, 6, 2, 4, 2], [2, 5, 2, 5, 2, 6, 2, 4, 2], 1)
    check("fractal_pivots 严格 H/L 交替",
          [p[2] for p in piv] == ["H", "L", "H", "L", "H", "L", "H"]
          and [p[1] for p in piv] == [5, 2, 5, 2, 6, 2, 4], str(piv))
    piv2 = _sw.fractal_pivots([2, 5, 5, 2], [2, 5, 5, 2], 1)
    check("fractal_pivots 相邻同型保留更极端（合并为 1 个 H）",
          piv2 == [[2, 5.0, "H"]], str(piv2))

    cl = _kl.cluster_levels([
        {"center": 100.0, "date": "a", "direction": "压力"},
        {"center": 100.05, "date": "b", "direction": "压力"},
        {"center": 50.0, "date": "c", "direction": "支撑"},
    ], tol=0.001)
    check("cluster_levels 近邻合并且压力取最高、方向不串簇",
          len(cl) == 2 and cl[0]["center"] == 100.05 and cl[0]["count"] == 2
          and cl[1]["center"] == 50.0 and cl[1]["count"] == 1, str(cl))

    df_last = pd.DataFrame({
        "date": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]),
        "open": [100.0, 101.0, 102.0], "high": [101.0, 102.0, 103.0],
        "low": [99.0, 100.0, 90.0], "close": [100.5, 101.5, 102.0]})
    r_last = _iv.check_level(df_last, {"price": 90.0, "direction": "break-down",
                                       "plan": "主", "kind": "规则失效", "rule": "R7"})
    check("check_level 触及在最后一根 → 待确认 0 根",
          r_last["status"].startswith("已触发待确认") and "0 根" in r_last["status"]
          and r_last["confirmed"] is None and r_last["first_touch"] is not None,
          str(r_last["status"]))

    check("gann_auto_scale 分档边界（9.99→0.05、10→0.5、999.99→5、1000→50、指数固定 50）",
          _ew.gann_auto_scale(9.99) == 0.05 and _ew.gann_auto_scale(10) == 0.5
          and _ew.gann_auto_scale(999.99) == 5.0 and _ew.gann_auto_scale(1000) == 50.0
          and _ew.gann_auto_scale(123, is_index=True) == 50.0)

    if FAILED:
        print("\nSMOKE FAILED：%d 项 —— %s" % (len(FAILED), "、".join(FAILED)))
        print("临时产物保留于：%s（可重跑或人工检查）" % tmp)
        return 1
    print("\nSMOKE PASSED：全部通过。")
    if not args.keep:
        shutil.rmtree(tmp, ignore_errors=True)
    else:
        print("临时产物保留于：%s" % tmp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
