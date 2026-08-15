#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""冒烟测试 —— 验证 pandas / matplotlib / 中文字体可用，且三个脚本主流程跑通。

    python smoke_test.py [--keep]

覆盖：
1. key_levels.py —— 合成 CSV（含跳空缺口、长上影/长下影候选）跑三类锚点输出；
   坏数据 CSV（high<low、日期乱序）验证数据自检拦截（应报错退出，workflow 1.5 口径）；
2. ew_chart.py —— 绘制 4 张标准图（中文标题、浪段方向 auto/显式、失效价位、
   江恩 --gann-auto-scale 自动刻度），验证 PNG 非空生成；
3. embed_report_images.py —— 标准 4 图模式与单方案防御 2 图模式各建一个归档
   文件夹，跑内嵌与校验（含模板头部特征注释校验、替代方案图区"不适用"标记）。

退出码：0 = 全部通过；1 = 任一失败。--keep 保留临时产物目录（默认删除）。
"""
import argparse
import datetime
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
HTML_TEMPLATE = os.path.join(SKILL, "assets", "网页报告_web_report.html")
IMAGE_TOKENS = ["{{主方案全景图路径}}", "{{主方案放大图路径}}",
                "{{替代方案全景图路径}}", "{{替代方案放大图路径}}"]
FAILED = []


def run(cmd):
    env = dict(os.environ)
    env.setdefault("PYTHONUTF8", "1")  # 子进程输出固定 UTF-8，避免 Windows 管道默认 GBK 导致中文检查乱码误判
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env)
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


def gen_md(path, n_img=4):
    keys = [("主方案全景", "主方案_全景.png"), ("主方案放大", "主方案_放大.png"),
            ("替代方案全景", "替代方案_全景.png"), ("替代方案放大", "替代方案_放大.png")]
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("# 分析报告（冒烟测试）\n\n## 2 主方案\n\n")
        for name, fn in keys[:n_img]:
            f.write("![%s](图表/%s)\n\n" % (name, fn))


def gen_html(path):
    with open(HTML_TEMPLATE, encoding="utf-8") as f:
        text = f.read()
    text = re.sub(r"\{\{([^}]+)\}\}",
                  lambda m: m.group(0) if m.group(1) in ["主方案全景图路径", "主方案放大图路径",
                                                         "替代方案全景图路径", "替代方案放大图路径"] else "X",
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
    print("== 2. ew_chart.py（4 张标准图：中文标题/浪段方向/失效价位/江恩自动刻度）==")
    charts = {
        "主方案_全景.png": (["--waves",
                             "1:0:60:Impulse（推动浪）:up",
                             "2:60:110:Zigzag（锯齿形）:down",
                             "3:110:220:Impulse（延长浪）:up",
                             "4:220:260:Flat（平台形）:down",
                             "5:260:319:Impulse（推动浪）:up",
                             "--invalid", "130:跌破 130（第 1 浪高点，R7）即失效",
                             "--current", str(last_close),
                             "--gann", "10:110:up", "--gann-auto-scale"],
                            "日线级别 · Intermediate · 主方案：五浪推动（Impulse）"),
        "主方案_放大.png": (["--waves", "5:260:319:Impulse（推动浪）",
                             "--invalid", "130:跌破 130（R7）即失效",
                             "--current", str(last_close), "--last", "80"],
                            "日线级别 · Intermediate · 主方案放大：第 5 浪"),
        "替代方案_全景.png": (["--waves",
                               "A:0:60:Zigzag（锯齿形）:up",
                               "B:60:110:Correction（调整浪）:down",
                               "C:110:319:Impulse（推动浪）:up",
                               "--invalid", "95:跌破 95（A 浪起点，R5）即失效",
                               "--current", str(last_close)],
                              "日线级别 · Intermediate · 替代方案：A-B-C"),
        "替代方案_放大.png": (["--waves", "C:240:319:Impulse（推动浪）",
                               "--invalid", "95:跌破 95（R5）即失效",
                               "--current", str(last_close), "--last", "80"],
                              "日线级别 · Intermediate · 替代方案放大：C 浪"),
    }
    chart_dir = os.path.join(tmp, "图表4")
    os.makedirs(chart_dir)
    for fn, (extra, title) in charts.items():
        code, out, err = run([sys.executable, os.path.join(HERE, "ew_chart.py"),
                              "--csv", csv_path, "--out", os.path.join(chart_dir, fn),
                              "--title", title] + extra)
        png = os.path.join(chart_dir, fn)
        check("生成 %s" % fn, code == 0 and os.path.getsize(png) > 0, err.strip()[:200])

    # ---- 3. embed_report_images.py：4 图模式 + 2 图防御模式 ----
    print("== 3. embed_report_images.py（4 图标准模式 + 2 图防御模式）==")
    for case, n_img in (("标准4图", 4), ("防御2图", 2)):
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
            check("2 图模式替代方案图区标记不适用", "单方案防御模式" in html)
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
