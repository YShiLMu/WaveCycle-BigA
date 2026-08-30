# -*- coding: utf-8 -*-
"""报告生成器——数据与模板分离：AI 只写 JSON 与正文草稿，模板永不进上下文。

设计要点：本脚本**不写任何文件**（校验+渲染后内容走 stdout，由 shell 重定向落盘），
归档文件夹与标准文件名由 init_archive.py 创建并打印，重定向目标照抄其输出即可。

职责（把每次分析中最耗 token 的模板阅读与字段替换收敛到一个脚本）：
  1. 读 data.json（25 个文本字段），渲染 assets/网页报告_web_report.html 后输出到 stdout
     （4 个图片占位符保留给 embed_report_images.py 注入 base64）；
  2. 可选 --md 校验分析报告正文草稿（4 张标准命名图片引用、无 {{残留}}、禁词警告），
     校验通过后原文输出到 stdout；
  3. 自检：模板特征注释、pano-img 结构、{{占位符}} 残留（仅允许 4 个图片占位符）、
     字段齐全非空。校验失败写 stderr 并以退出码 1 结束，stdout 不产出内容。

data.json 模式（字段名与模板一一对应，缺一硬失败）：

    {
      "标的名称": "饮料制造", "标的代码": "881133", "时间戳": "20260830_0924",
      "page": {
        "分析日期": "2026-08-30", "分析级别": "日线级别 · ...", "收盘价": "4980.62（2026-08-28）",
        "核心判断": "...", "当前关键形态": "...", "备选方案": "...", "概率与仓位": "...",
        "数据范围": "2007-08-01 至 2026-08-28", "放大图数据范围": "近 500 根（...）",
        "上方突破观察价位": "...", "上方突破观察说明": "...",
        "下方防守价位": "...", "下方防守说明": "...",
        "纪律止损价位": "...", "纪律止损说明": "...",
        "数据来源": "...", "生成时间": "2026-08-30 09:24"
      },
      "summary": {
        "总结核心判断": "...", "总结当前关键形态": "...", "总结备选方案": "...",
        "总结概率与仓位": "...", "总结关键价位": "...", "总结近期交易计划": "..."
      }
    }

（"标的名称/标的代码" 会同时替换进模板正文；page 内不需重复填写这两个键）

用法（重定向目标必须使用 init_archive.py 打印的标准文件名）：
  python gen_report.py --data data.json --out-dir <归档文件夹> \
      > "<归档文件夹>/网页报告_<标的>_<代码>_<时间>.html"
  python gen_report.py --data data.json --md 报告草稿.md \
      > "<归档文件夹>/分析报告_<标的>_<代码>_<时间>.md"
生成后仍须运行：python embed_report_images.py <归档文件夹>
"""
import argparse
import json
import os
import re
import sys

from naming import CHART_IMAGE_PATHS, IMAGE_PLACEHOLDERS, doc_names, validate_component

PAGE_FIELDS = [
    "分析日期", "分析级别", "收盘价",
    "核心判断", "当前关键形态", "备选方案", "概率与仓位",
    "数据范围", "放大图数据范围",
    "上方突破观察价位", "上方突破观察说明",
    "下方防守价位", "下方防守说明",
    "纪律止损价位", "纪律止损说明",
    "数据来源", "生成时间",
]
SUMMARY_FIELDS = [
    "总结核心判断", "总结当前关键形态", "总结备选方案",
    "总结概率与仓位", "总结关键价位", "总结近期交易计划",
]
BANNED = re.compile(r"必然|一定|绝对")
IMG_REF = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


def info(msg):
    print(msg, file=sys.stderr)


def fail(msg):
    print("[错误] %s" % msg, file=sys.stderr)
    sys.exit(1)


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except AttributeError:
            pass

    p = argparse.ArgumentParser(
        description="校验 data.json 并渲染报告内容到 stdout（本脚本不写文件）")
    p.add_argument("--data", required=True,
                   help="数据 JSON（模式见脚本头部 docstring）；传 '-' 时从 stdin 读入（测试/管道场景避免落盘）")
    p.add_argument("--md", default=None, help="分析报告正文草稿 md（校验后原样输出）")
    args = p.parse_args()

    if args.data == "-":
        try:
            data = json.loads(sys.stdin.read())
        except json.JSONDecodeError as e:
            fail("stdin JSON 解析失败: %s" % e)
    else:
        if not os.path.isfile(args.data):
            fail("数据文件不存在: %s" % args.data)
        with open(args.data, encoding="utf-8-sig") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as e:
                fail("data.json 解析失败: %s" % e)
    if not isinstance(data, dict):
        fail("data.json 顶层应为 JSON 对象")

    name = validate_component(data.get("标的名称", ""), "标的名称")
    code = validate_component(data.get("标的代码", ""), "标的代码")
    stamp = str(data.get("时间戳", ""))
    if not re.fullmatch(r"\d{8}_\d{4}", stamp):
        fail("时间戳 格式应为 YYYYMMDD_HHMM，收到: %r" % stamp)
    page = data.get("page") or {}
    summary = data.get("summary") or {}

    missing = [k for k in PAGE_FIELDS if not str(page.get(k, "")).strip()]
    missing += [k for k in SUMMARY_FIELDS if not str(summary.get(k, "")).strip()]
    if missing:
        fail("data.json 缺少非空字段: %s" % "、".join(missing))

    # ---- 模式二：校验分析报告草稿并原样输出 ----
    if args.md:
        if not os.path.isfile(args.md):
            fail("报告草稿不存在: %s" % args.md)
        if ".." in args.md:
            fail("--md 路径不允许包含 ..（路径穿越防护）")
        with open(args.md, encoding="utf-8") as f:
            body = f.read()

        refs = IMG_REF.findall(body)
        std = [r.replace("\\", "/").lstrip("./") for r in refs
               if r.replace("\\", "/").lstrip("./") in CHART_IMAGE_PATHS]
        if len(std) != 4 or len(set(std)) != 4:
            fail("报告草稿图片引用应为 4 张标准命名图片 %s，实际引用: %s"
                 % (CHART_IMAGE_PATHS, refs))
        if "{{" in body:
            fail("报告草稿存在未替换占位符 {{...}}")
        for i, line in enumerate(body.splitlines(), 1):
            m = BANNED.search(line)
            if m:
                info("[警告] 概率禁词 %r（第 %d 行，若为引用规则原文请人工确认）: %s"
                     % (m.group(0), i, line.strip()[:80]))
        md_name, _html_name = doc_names(name, code, stamp)
        info("[OK] 草稿校验通过（禁词警告见上，无输出即通过），输出重定向到标准文件名：")
        info("     " + md_name)
        sys.stdout.write(body)
        return 0

    # ---- 模式一：渲染网页报告到 stdout ----
    script_dir = os.path.dirname(os.path.abspath(__file__))
    tpl_path = os.path.normpath(os.path.join(os.path.dirname(script_dir),
                                             "assets", "网页报告_web_report.html"))
    if not os.path.isfile(tpl_path):
        fail("网页模板不存在: %s" % tpl_path)
    with open(tpl_path, encoding="utf-8") as f:
        html = f.read()

    fields = dict(page)
    fields.update(summary)
    fields["标的名称"] = name
    fields["标的代码"] = code
    for key in PAGE_FIELDS + SUMMARY_FIELDS + ["标的名称", "标的代码"]:
        html = html.replace("{{%s}}" % key, str(fields[key]))

    # 模板头部的说明文字（"将全部 {{字段名}} 替换"）不属于数据字段
    html = html.replace("将全部 {{字段名}} 替换", "将全部数据字段替换")

    residual = set(re.findall(r"\{\{([^}]+)\}\}", html))
    bad_residual = residual - IMAGE_PLACEHOLDERS
    if bad_residual:
        fail("网页渲染后存在未替换字段: %s" % "、".join(sorted(bad_residual)))
    if "波浪理论网页报告模板" not in html:
        fail("网页模板特征注释缺失，渲染源可能不是 assets/网页报告_web_report.html")
    if html.count('class="pano-img"') != 4:
        fail("网页 pano-img 结构数应为 4，实际 %d" % html.count('class="pano-img"'))

    info("[OK] 网页渲染完成（剩余图片占位符 %d 个，待 embed_report_images.py 注入），"
         "输出重定向到标准文件名：" % len(residual))
    _md_name, html_name = doc_names(name, code, stamp)
    info("     " + html_name)
    info("[NEXT] python embed_report_images.py <归档文件夹>")
    sys.stdout.write(html)
    return 0


if __name__ == "__main__":
    sys.exit(main())
