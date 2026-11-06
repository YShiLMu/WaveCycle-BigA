#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""冒烟测试 —— 验证 pandas / matplotlib / 中文字体可用，且各脚本主流程跑通。

    python smoke_test.py [--keep]

覆盖：
1. key_levels.py —— 合成 CSV（含跳空缺口、长上影/长下影候选）跑三类锚点输出；
   坏数据 CSV（high<low、日期乱序）验证数据自检拦截（应报错退出，workflow 1.5 口径）；
2. ew_chart.py —— 绘制 2 张标准图（每方案一张全景，见 naming.CHART_VIEWS；中文标题、浪段方向 auto/显式、失效价位、
   江恩 --gann-auto-scale 自动刻度、--path 连续浪路径），验证 PNG 非空生成；
   2d 另测 Y 轴视口锁定：陡刻度江恩/价外参考位只被裁切，不得撑大坐标轴；
3. embed_report_images.py —— 标准 2 图模式与单方案防御 1 图模式各建一个归档
   文件夹，跑内嵌与校验（含模板头部特征注释校验、替代方案图区"不适用"标记）；
4. score.py —— 八因子加权排序与共振标签；
5. swings.py —— 合成 CSV 跑分形摆动点提取、--tail 截断与 --chart-args 参数串；
6. init_archive.py —— 建档（图表/ 子目录、幂等拦截）与 --print-dir 单行输出；
7. gen_report_web.py / gen_report_md.py —— data.json 渲染网页与 md（stdout 无 {{残留}}、含模板特征注释）；
8. data_check.py —— 自检表 + 四要素输出、缺 --fq/--source 判不通过、坏数据拦截、
   OHLC 含 NaN/全 NaN 时极值与收盘不输出 nan 假事实；
9. invalidation_check.py —— 已触发已确认 / 未触发 / --since 过滤三态判定；
10. swings.py --dow —— 道氏状态读数（3 点判 2 点定 + DO4 事实 + 无 volume 降级）；
11. rule_check.py —— R-IMP-07/09/10 通过/违反、下跌镜像、缺浪不适用、非法 --wave 报错；
12. preflight.py —— 三段流水线顺序产出 + data_check 不通过即终止（exit 1）；
13. ew_chart._seg_direction —— EG-05 极端价位判向口径直测（长上影 close 回落
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

from naming import IMAGE_KEYS, IMAGE_PLACEHOLDERS, chart_png

import pandas as pd

import report_common as rc

HERE = os.path.dirname(os.path.abspath(__file__))
HTML_TEMPLATE = rc.template_path(HERE, "网页报告_web_report.html")
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
        f.write("## 5. 失效价位清单\n\n<!-- INVALIDATION-TABLE-BEGIN -->\n\n"
                "| 方案 | 失效价位 | 方向 | 规则依据 | 触发后果 |\n"
                "| --- | --- | --- | --- | --- |\n"
                "| 主方案 | 130 | break-down | R-IMP-10 | 测试 |\n\n"
                "<!-- INVALIDATION-TABLE-END -->\n")


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
    parser.add_argument("--dev-root", action="store_true",
                        help="从源码树运行：把 05_模板_templates 映射成临时 assets（仅开发用）")
    args = parser.parse_args(argv)

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except AttributeError:
            pass

    tmp = tempfile.mkdtemp(prefix="wavecycle_smoke_")
    print("临时目录：%s" % tmp)

    global HTML_TEMPLATE
    if args.dev_root:
        # 源码树没有 assets/：把源模板按打包名复制到临时 assets，供子进程解析。
        assets = os.path.join(tmp, "assets")
        os.makedirs(assets, exist_ok=True)
        source_assets = os.path.join(os.path.dirname(HERE), "05_模板_templates")
        for source_name, target_name in (
                ("05_网页报告_web_report.html", "网页报告_web_report.html"),
                ("01_分析报告_report.md", "分析报告_report.md")):
            shutil.copy2(os.path.join(source_assets, source_name),
                         os.path.join(assets, target_name))
        os.environ["WAVECYCLE_ASSETS"] = assets
        HTML_TEMPLATE = rc.template_path(HERE, "网页报告_web_report.html")

    # 执行根不对时先停：缺 assets/ 是安装位置问题，不是依赖问题，避免被当成缺包深挖脚本
    if not os.path.isfile(HTML_TEMPLATE):
        print(rc.missing_asset_message(HTML_TEMPLATE, HERE), file=sys.stderr)
        print("\nSMOKE FAILED：技能资源缺失（执行根不对，不是依赖或环境问题）")
        return 1

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
    check("已回补的历史缺口不再列出", "上跳" not in out and "== 2. 跳空缺口 ==\n  （无）" in out)

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

    # --max-levels 封顶 + 截断披露（D40：按触及次数降序、同次数按距收盘升序截断）
    code, out, err = run([sys.executable, os.path.join(HERE, "key_levels.py"),
                          "--csv", csv_path, "--max-levels", "3"])
    n_kept = len([ln for ln in out.splitlines()
                  if re.match(r"\s+(前高|前低) [\d.]+ —— 触及", ln)])
    check("--max-levels 3 封顶生效（保留 ≤3 条）", code == 0 and 0 < n_kept <= 3,
          out.strip()[:150])
    check("--max-levels 截断披露省略行数", "--max-levels 3：已省略" in out, out.strip()[-200:])

    # ---- 2. ew_chart.py ----
    print("== 2. ew_chart.py（2 张标准图[全景]：中文标题/浪段方向/失效价位/江恩自动刻度）==")
    charts = {
        chart_png("主方案", "全景"): (["--waves",
                             "1:0:60:Impulse（推动浪）:up",
                             "2:60:110:Zigzag（锯齿形）:down",
                             "3:110:220:Impulse（延长浪）:up",
                             "4:220:260:Flat（平台形）:down",
                             "5:260:319:Impulse（推动浪）:up",
                             "--invalid", "130:跌破 130（第 1 浪高点，R-IMP-10）即失效",
                             "--current", str(last_close),
                             "--gann", "10:110:up", "--gann-auto-scale",
                             "--path", "1@0,2@60,3@110,4@220,5@260,A@319"],
                            "日线级别 · Intermediate · 主方案：五浪推动（Impulse）"),
        chart_png("替代方案", "全景"): (["--waves",
                               "A:0:60:Zigzag（锯齿形）:up",
                               "B:60:110:Correction（调整浪）:down",
                               "C:110:319:Impulse（推动浪）:up",
                               "--invalid", "95:跌破 95（A 浪起点，R-IMP-07）即失效",
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

    # ---- 2c. ew_chart --path 显式峰谷（外包线端点强制取 high/low）----
    print("== 2c. ew_chart --path 显式峰谷（:peak/:trough 覆盖自动判向）==")
    explicit_png = os.path.join(chart_dir, "显式峰谷_全景.png")
    code, out, err = run([sys.executable, os.path.join(HERE, "ew_chart.py"),
                          "--csv", csv_path, "--out", explicit_png, "--title", "显式峰谷",
                          "--start", "0",
                          "--path", "[I]@0,[II]@60",
                          "--path", "1-1@0,1-2@60:trough,1-3@110"])
    check("显式 :trough 正常出图", code == 0 and os.path.getsize(explicit_png) > 0,
          err.strip()[:200])
    code, out, err = run([sys.executable, os.path.join(HERE, "ew_chart.py"),
                          "--csv", csv_path, "--out", os.path.join(chart_dir, "非法后缀.png"),
                          "--title", "非法峰谷后缀", "--path", "1@0:foo,2@60"])
    check("非法峰谷后缀被拒绝(exit!=0)", code != 0, (out + err).strip()[:200])

    # ---- 2d. ew_chart Y 轴视口锁定：外推辅助线不得撑大坐标轴 ----
    print("== 2d. ew_chart 视口锁定（江恩/通道等外推线只裁切、不撑轴）==")
    import ew_chart as _ew
    vdf = pd.DataFrame({"low": [60.0, 0.0, 62.0], "high": [108.0, 0.0, 109.0]})
    vy = _ew._price_viewport(vdf, current_price=None,
                             levels=[(105.0, "关键位")], invalids=[(300.0, "远目标")])
    span = 109.0 - 60.0
    want_lo, want_hi = 60.0 - span * _ew._VIEWPORT_PAD_RATIO, 109.0 + span * _ew._VIEWPORT_PAD_RATIO
    check("视口=K线区间±8%（脏行 low=0 不参与定界）",
          vy is not None and abs(vy[0] - want_lo) < 1e-6 and abs(vy[1] - want_hi) < 1e-6,
          "" if vy is None else "得到 %s" % (vy[:2],))
    check("窗口内参考位并入视口、窗口外参考位只裁切",
          vy is not None and len(vy[2]) == 1 and vy[2][0][0] == 300.0,
          "" if vy is None else "clipped=%s" % (vy[2],))
    gann_png = os.path.join(chart_dir, "陡刻度江恩_全景.png")
    code, out, err = run([sys.executable, os.path.join(HERE, "ew_chart.py"),
                          "--csv", csv_path, "--out", gann_png, "--title", "陡刻度江恩",
                          "--invalid", "9999:远目标(价外)",
                          "--gann", "10:110:20:up"])
    check("陡刻度江恩不撑爆 Y 轴（远目标被裁切且仍出图）",
          code == 0 and os.path.getsize(gann_png) > 0
          and "已裁切" in err and "9999" in err,
          (err.strip() or out.strip())[:300])

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
        if case == "防御1图":
            check("防御1图 替代方案图区标记不适用", "单方案防御模式" in html and "不适用" in html)
            alternate_imgs = re.findall(r'<img\b[^>]*(?:data-scheme="替代方案"|alt="替代方案全景图")[^>]*>', html)
            check("防御1图 无替代方案图片", not alternate_imgs)
            html_path = os.path.join(folder, "网页报告_冒烟_000000_20260101.html")
            with open(html_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(html.replace("不适用", "未标明"))
            bad_code, _bad_out, bad_err = run([sys.executable, os.path.join(HERE, "embed_report_images.py"), folder])
            check("防御1图 缺少不适用提示被拒绝", bad_code != 0 and "不适用" in bad_err)
            with open(html_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(html)
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
        "报告模式": "标准", "细分深度": 3, "细分深度来源": "默认-3层",
        "analysis_scope": {
            "version": 3, "delivery_depth": 3, "inspection_depth": 1, "profile": "daily-year-month-day", "data_start": "2024-01-01",
            "data_end": "2026-01-01", "history_review": "合成长期框架；不代表真实市场结论",
            "schemes": [{"name": plan, "framework_start": "2024-01-01", "current_parent": "1",
                         "basis": "合成框架", "review_condition": "补核内部子浪",
                         "waves": [{"path": "1", "start": "2024-01-01", "end": "2026-01-01",
                                    "state": "unresolved", "completed": False, "confirmed": False,
                                    "start_price": 100., "end_price": 160.,
                                    "completion_status": "in_progress", "completion_basis": "合成阶段，未核验完成",
                                    "internal_structure": {"status": "pending", "basis": "合成输入缺内部行情"},
                                    "parent_identity": {"status": "pending", "basis": "合成框架待核验"},
                                    "inspection": {"start": "2024-01-01", "end": "2026-01-01",
                                                   "extrema": {"high": {"date": "2026-01-01", "price": 160.},
                                                               "low": {"date": "2024-01-01", "price": 100.}},
                                                   "windows": [{"k": k, "pivots": []} for k in (5, 3, 1)]},
                                    "review": {"reason": "resolution", "next_action": "finer_data",
                                               "windows": [{"k": k, "finding": "合成%d窗口未提供内部行情，仅验证渲染契约" % k}
                                                           for k in (5, 3, 1)]},
                                    "evidence": "该合成父浪未核验内部形态", "needed": "补核内部结构"}]}
                        for plan in ("主方案", "替代方案")],
        },
        "fields": {
            "分析日期": "2026-01-01", "分析级别": "日线级别", "收盘价": str(last_close),
            "主方案说明": "测试", "主方案失效": "测试", "替代方案": "测试",
            "概率说明": "测试", "概率结论": "测试", "交易计划": "测试",
            "风险提示": "测试", "更新跟踪": "测试",
            "数据来源": "合成数据", "生成时间": "2026-01-01 12:00",
        },
        "tables": {
            "分析前提": [{"项": "细分深度来源", "内容": "默认-3层"},
                        {"项": "分钟分形层", "内容": "已询问-不启用"},
                        {"项": "级别", "内容": "日线级别"}],
            "主方案数浪": [{"浪": "1", "端点": "100/2024-01-01 → 160/2024-02-01", "结构": "Impulse", "说明": "测试"}],
            "neely参考": [{"脚本": "结构阶梯", "输出": "通过", "意义": "测试"}],
            "八因子": [{"因子": factor, "主方案": 1, "替代方案": 1}
                       for factor in ("Guideline 得分", "结构完整度", "斐波那契共振", "道氏一致性",
                                      "江恩价格共振", "江恩时间共振", "蜡烛图信号", "失效距离")],
            "失效价位": [{"方案": plan, "类型": "规则失效", "失效价位": "130", "方向": "break-down",
                          "规则依据": "R-IMP-10", "触发后果": "测试"} for plan in ("主方案", "替代方案")],
            "短期支撑压力": [{"周期": "日线", "方向": "支撑", "浪": "4", "基准": "回撤 3 浪 L3→H3",
                              "比率": "0.382", "价位": "150.00", "级别": "2 级"}],
            "多周期共振": [{"共振带": "148.00–150.00", "方向": "支撑", "浪族": "调整",
                            "参与周期": "日线／60m", "各轴原级": "日线 2 级／60m 3 级",
                            "星数": "1 星", "级别": "3 级",
                            "结论": "1 星支撑（日线／60m），取 3 级"}],
        },
        "简明分析说明": {
            "大级别浪": "第4浪", "小级别浪": "第4浪的b浪",
            "neely得分": 1, "neely强度": "中等", "结论": "偏多",
        },
    }
    four_data = json.loads(json.dumps(data, ensure_ascii=False))
    four_data["细分深度"] = 4
    four_data["细分深度来源"] = "用户确认-4层"
    four_data["analysis_scope"]["delivery_depth"] = 4
    for scheme in four_data["analysis_scope"]["schemes"]:
        scheme["fourth_layer_roots"] = ["1"]
    four_data["tables"]["分析前提"][0]["内容"] = "用户确认-4层"
    for script in ("gen_report_md.py", "gen_report_web.py"):
        code, out, err = run([sys.executable, os.path.join(HERE, script), "--data", "-"],
                             stdin_text=json.dumps(four_data, ensure_ascii=False))
        visible = out.split("<!-- REPORT-STATE-v1:")[0]
        content_ok = ("交付4层" in visible and "实际端点登记到1层" in visible) if script == "gen_report_md.py" else (
            "4层" in visible and "是否细分" in visible and "扫描事实" not in visible)
        check("四层报告按MD完整／HTML精简展示：" + script,
              code == 0 and content_ok, err[-200:])
    payload = json.dumps(data, ensure_ascii=False)
    # 负例：缺"细分深度来源"应被校验拦截（D37，未确认深度不得出报告）
    bad_payload = json.dumps({k: v for k, v in data.items() if k != "细分深度来源"},
                             ensure_ascii=False)
    code, out, err = run([sys.executable, os.path.join(HERE, "gen_report_md.py"),
                          "--data", "-"], stdin_text=bad_payload)
    check("缺细分深度来源被拦截（D37）", code != 0 and "细分深度来源" in err,
          (out + err).strip()[:150])
    # 负例：缺"分钟分形层"询问记录应被拦截（04 EG-07，未登记答复不得出报告）
    bad_ask = json.loads(payload)
    bad_ask["tables"]["分析前提"] = [r for r in bad_ask["tables"]["分析前提"]
                                     if r["项"] != "分钟分形层"]
    code, out, err = run([sys.executable, os.path.join(HERE, "gen_report_md.py"),
                          "--data", "-"], stdin_text=json.dumps(bad_ask, ensure_ascii=False))
    check("缺分钟分形层询问记录被拦截（EG-07）", code != 0 and "分钟分形层" in err,
          (out + err).strip()[:150])
    # 负例：非法答复值（模型自行判定跳过）不得通过
    bad_ask_value = json.loads(payload)
    for row in bad_ask_value["tables"]["分析前提"]:
        if row["项"] == "分钟分形层":
            row["内容"] = "跳过"
    code, out, err = run([sys.executable, os.path.join(HERE, "gen_report_md.py"),
                          "--data", "-"], stdin_text=json.dumps(bad_ask_value, ensure_ascii=False))
    check("非法分钟分形层答复被拦截（EG-07）", code != 0 and "分钟分形层" in err,
          (out + err).strip()[:150])
    # 负例：失效价位表缺"方向"列应被校验拦截（--from-report 零推断依赖）
    bad_dir = json.loads(payload)
    del bad_dir["tables"]["失效价位"][0]["方向"]
    code, out, err = run([sys.executable, os.path.join(HERE, "gen_report_md.py"),
                          "--data", "-"], stdin_text=json.dumps(bad_dir, ensure_ascii=False))
    check("失效价位表缺方向列被拦截", code != 0 and "方向" in err, (out + err).strip()[:150])
    # 2代编号：可推导数值边界的公理可作规则失效；非边界公理（延长浪独占）不得冒充
    alpha_ok = json.loads(payload)
    for row in alpha_ok["tables"]["失效价位"]:
        row["规则依据"] = "R-IMP-07 浪2回撤上限"
    code, out, err = run([sys.executable, os.path.join(HERE, "gen_report_md.py"),
                          "--data", "-"], stdin_text=json.dumps(alpha_ok, ensure_ascii=False))
    check("2代编号 R-IMP-07 被规则失效接受", code == 0, (out + err).strip()[:150])
    alpha_bad = json.loads(payload)
    for row in alpha_bad["tables"]["失效价位"]:
        row["规则依据"] = "R-IMP-11 延长浪独占"
    code, out, err = run([sys.executable, os.path.join(HERE, "gen_report_md.py"),
                          "--data", "-"], stdin_text=json.dumps(alpha_bad, ensure_ascii=False))
    check("非数值边界公理不得冒充规则失效", code != 0 and "R-IMP-07" in err,
          (out + err).strip()[:150])
    bad_scope = {k: v for k, v in data.items() if k != "analysis_scope"}
    code, out, err = run([sys.executable, os.path.join(HERE, "gen_report_md.py"),
                          "--data", "-"], stdin_text=json.dumps(bad_scope, ensure_ascii=False))
    check("缺第一层框架与逐浪覆盖被拦截（D41）", code != 0 and "analysis_scope" in err,
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
          code == 1 and "不通过" in out and "缺失或非有限" in out and "nan" not in out.lower(), out.strip()[:200])

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
                          "--level", "99|break-down|主方案|规则失效|R-IMP-10",
                          "--level", "94|break-down|主方案|结构失效|06 6.6注",
                          "--level", "112|break-up|替代方案|规则失效|R-IMP-10"])
    check("判定正常退出", code == 0, (out + err).strip()[:200])
    check("规则失效首根立即生效（99，2024-01-01）",
          "已触发规则失效（立即生效" in out and "2024-01-01 | 2024-01-01" in out)
    check("未触发（94）", "未触发" in out)
    check("升破方向未触发（112）", "112.000" in out)
    check("触发摘要分列 3 个价位、3 个分支、1 个已触发（规则立即失效）",
          "价位数 3；判定分支 3，其中 1 个已触发，0 个已确认；方向待确认 0" in out)
    code, out, err = run([sys.executable, os.path.join(HERE, "invalidation_check.py"),
                          "--csv", inv_csv, "--since", "2024-01-05",
                          "--level", "99|break-down|主方案|规则失效|R-IMP-10"])
    check("--since 过滤生效", code == 0 and "2024-01-05" in out and "2024-01-04" not in out,
          out.strip()[:150])
    code, out, err = run([sys.executable, os.path.join(HERE, "invalidation_check.py"),
                          "--csv", inv_csv, "--level", "99|向下|主方案|R-IMP-10"])
    check("非法 --level 报错退出", code != 0 and "5 段" in (out + err), (out + err).strip()[:150])

    # ---- 9b. invalidation_check.py --from-report（锚点/降级/方向三层降级/观察位分离）----
    print("== 9b. invalidation_check.py --from-report（锚点抽取 + 无锚点降级 + 方向待确认）==")
    rep_new = os.path.join(tmp, "报告_新格式.md")
    with open(rep_new, "w", encoding="utf-8", newline="\n") as f:
        f.write("# 报告\n\n## 5. 失效价位清单\n\n<!-- INVALIDATION-TABLE-BEGIN -->\n\n"
                "| 方案 | 失效价位 | 方向 | 规则依据 | 触发后果 |\n"
                "| --- | --- | --- | --- | --- |\n"
                "| 主方案 | 99 | break-down | R-IMP-10 | 测试 |\n"
                "| 替代方案（观察位） | 108 | break-up | 非规则失效价位，实务观察 | 测试 |\n\n"
                "<!-- INVALIDATION-TABLE-END -->\n")
    code, out, err = run([sys.executable, os.path.join(HERE, "invalidation_check.py"),
                          "--csv", inv_csv, "--from-report", rep_new])
    check("--from-report 锚点抽取正常退出", code == 0, (out + err).strip()[:200])
    check("锚点抽取标注来源", "锚点抽取" in out)
    check("新报告方向列零推断（方向待确认数为 0）",
          "方向待确认 0" in out and "（方向待确认）" not in out)
    check("观察位单列且不参与判定", "观察位" in out and "不参与触发判定" in out
          and "| 升破 |" not in out, out.strip()[-300:])

    # 旧格式样本保留历史编号，仅用于验证归档兼容解析；新输出禁止使用旧编号
    rep_old = os.path.join(tmp, "报告_旧格式.md")
    with open(rep_old, "w", encoding="utf-8", newline="\n") as f:
        f.write("# 报告\n\n## 【5. 失效价位清单】\n\n"
                "| 方案 | 类型 | 失效价位 | 判定标准 | 触发后动作 |\n"
                "| --- | --- | --- | --- | --- |\n"
                "| 主方案 | 规则失效（下） | 99 | 跌破第 [1] 浪顶，违反 R7 | 失效 |\n"  # legacy-ok 历史归档兼容样本
                "| 主方案 | 结构预警 | 96 | 跌破后连续 2 根收盘未收回 | 阶段切换 |\n"
                "| 替代方案 | 规则失效 | 105 | 价格触及该位后结构重估 | 重估 |\n\n"
                "## 【6. 交易计划建议】\n")
    code, out, err = run([sys.executable, os.path.join(HERE, "invalidation_check.py"),
                          "--csv", inv_csv, "--from-report", rep_old])
    check("旧报告降级解析并披露", code == 0 and "已降级解析" in out, (out + err).strip()[:200])
    check("类型括号定方向（下→跌破）", "| 跌破 | 规则失效 |" in out)
    check("结构预警默认不判定且单列", "结构失效价位（不参与本次触发判定" in out)
    check("方向不定行双向各查并标注待确认", "方向待确认" in out and "跌破?" in out and "升破?" in out)
    code, out, err = run([sys.executable, os.path.join(HERE, "invalidation_check.py"),
                          "--csv", inv_csv, "--from-report", rep_old, "--include-structural"])
    check("--include-structural 纳入结构失效", code == 0 and "已纳入判定" in out
          and "| 结构失效 |" in out, (out + err).strip()[:200])
    code, out, err = run([sys.executable, os.path.join(HERE, "invalidation_check.py"),
                          "--csv", inv_csv])
    check("无 --from-report 且无 --level 报错退出", code != 0 and "未提供失效价位" in (out + err),
          (out + err).strip()[:150])

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
    print("== 11. rule_check.py（R-IMP-07/09/10 与失败浪位置判定）==")
    code, out, err = run([sys.executable, os.path.join(HERE, "rule_check.py"),
                          "--wave", "1:100:160", "--wave", "2:160:130",
                          "--wave", "3:130:220", "--wave", "4:220:185", "--wave", "5:185:190"])
    check("上升推动全通过（exit 0）",
          code == 0 and out.count("通过") >= 3 and "失败浪（结构判断）" in out, (out + err).strip()[:200])
    code, out, err = run([sys.executable, os.path.join(HERE, "rule_check.py"),
                          "--wave", "1:100:160", "--wave", "2:160:130",
                          "--wave", "3:130:220", "--wave", "4:220:155"])
    check("R-IMP-10 违反（exit 1）", code == 1 and "| R-IMP-10 | 违反 |" in out, out.strip()[:200])
    code, out, err = run([sys.executable, os.path.join(HERE, "rule_check.py"),
                          "--wave", "1:100:80", "--wave", "2:80:90",
                          "--wave", "3:90:55", "--wave", "4:55:70", "--wave", "5:70:60"])
    check("下跌推动镜像识别", code == 0 and all("| %s | 通过 |" % rule in out for rule in ("R-IMP-07", "R-IMP-09", "R-IMP-10")),
          out.strip()[:200])
    code, out, err = run([sys.executable, os.path.join(HERE, "rule_check.py"),
                          "--wave", "1:100:160", "--wave", "2:160:130"])
    check("缺第 3 浪报错退出", code != 0 and "缺少第1/2/3浪" in (out + err), (out + err).strip()[:150])
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
    # compact 默认开启（D40）与 --no-compact 全量
    code, out, err = run([sys.executable, os.path.join(HERE, "preflight.py"),
                          "--csv", csv_path, "--source", "合成数据", "--fq", "qfq"])
    check("compact 默认开启并披露口径", code == 0 and "compact 默认口径" in out,
          (out + err).strip()[-200:])
    code, out, err = run([sys.executable, os.path.join(HERE, "preflight.py"),
                          "--csv", csv_path, "--source", "合成数据", "--fq", "qfq",
                          "--no-compact"])
    check("--no-compact 关闭紧凑（无 compact 口径行）",
          code == 0 and "compact 默认口径" not in out, (out + err).strip()[-200:])

    # ---- 13. ew_chart._seg_direction 判向口径直测 ----
    print("== 13. ew_chart._seg_direction（EG-05 极端价位判向口径）==")
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
    check("parse_path_arg 显式 :trough 后缀", _ew.parse_path_arg("3-1-2@1642:trough") == ([1642], ["3-1-2"], ["trough"]))
    check("parse_path_arg 显式 :p 缩写", _ew.parse_path_arg("3@100:p") == ([100], ["3"], ["peak"]))
    check("parse_path_arg 无后缀 overrides 全 None", _ew.parse_path_arg("1@10,2@20") == ([10, 20], ["1", "2"], [None, None]))
    check("parse_path_arg 旧式 overrides 全 None", _ew.parse_path_arg("[1]:10:20") == ([10, 20], ["[1]"], [None, None]))
    try:
        _ew.parse_path_arg("1@10:foo")
        _bad_flag = False
    except Exception:
        _bad_flag = True
    check("parse_path_arg 非法峰谷后缀报错", _bad_flag)

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
                                       "plan": "主", "kind": "规则失效", "rule": "R-IMP-10"})
    check("check_level 规则触及在最后一根仍立即失效",
          "立即生效" in r_last["status"]
          and r_last["confirmed"] is not None and r_last["first_touch"] is not None,
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
