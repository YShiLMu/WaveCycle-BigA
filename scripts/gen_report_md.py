# -*- coding: utf-8 -*-
"""分析报告生成器（.md）——读 data.json 渲染 assets/分析报告_report.md，输出到 stdout。

与 gen_report_web.py 同构；共享 data.json 加载/校验与渲染器在 report_common.py。
本脚本**不写文件**：渲染后内容走 stdout，由 shell 重定向落盘（目标文件名见 init_archive.py 打印）。

用法：
  python gen_report_md.py --data data.json > "<归档文件夹>/分析报告_<标的>_<代码>_<时间>.md"
生成后仍须运行：python embed_report_images.py <归档文件夹>
"""
import argparse
import os
import re
import sys

import report_common as rc
from naming import doc_names


def fail(msg):
    print("[错误] %s" % msg, file=sys.stderr)
    sys.exit(1)


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except AttributeError:
            pass

    p = argparse.ArgumentParser(description="读 data.json 渲染分析报告 .md 到 stdout（本脚本不写文件）")
    p.add_argument("--data", required=True, help="数据 JSON；传 '-' 从 stdin 读")
    args = p.parse_args()

    data = rc.load_data(args.data)
    name, code, stamp = rc.validate(data)
    fields = data["fields"]
    tables = data["tables"]
    jm = data["简明分析说明"]

    script_dir = os.path.dirname(os.path.abspath(__file__))
    tpl_path = rc.template_path(script_dir, "分析报告_report.md")
    if not os.path.isfile(tpl_path):
        fail(rc.missing_asset_message(tpl_path, script_dir))
    with open(tpl_path, encoding="utf-8") as f:
        md = f.read()
    rc.check_invalidation_anchor(md, "分析报告模板 %s" % tpl_path)
    if "{{分析尺度与覆盖}}" not in md:
        fail("分析报告模板缺少分析尺度与覆盖；请从源文件重新构建并同步安装")

    # 1) 表格（Markdown 表格，先于文本，避免表格内容被后续替换误伤）
    for tname, cols in rc.TABLE_FIELDS.items():
        md = md.replace("{{%s表}}" % tname, rc.render_md_table(cols, tables[tname]))

    # 2) 文本字段 + 简明分析说明 + 标的名称/代码
    mapping = dict(fields)
    mapping.update({"标的名称": name, "标的代码": code, "简明分析说明": rc.render_jianming(jm, data["analysis_scope"]),
                    "分析尺度与覆盖": rc.render_scope(data)})
    md = rc.substitute(md, mapping)

    # 3) 模板说明文字里的字面 {{表名}} / {{字段名}} 非数据占位符，中和防残留误判
    md = md.replace("{{表名}}", "表名")
    md = md.replace("{{字段名}}", "字段名")

    if data["报告模式"] == "单方案防御":
        md = re.sub(r"!\[[^\]]*\]\([^)]*替代方案_全景\.png\)", "（单方案防御：替代方案不适用）", md)
        md = "报告模式：单方案防御；原因：" + data["单方案原因"] + "\n\n" + md

    # 4) 自检：无未替换占位符 + 模板特征
    residual = set(re.findall(r"\{\{([^}]+)\}\}", md))
    if residual:
        fail("分析报告渲染后存在未替换字段: %s" % "、".join(sorted(residual)))
    if "Elliott Wave 分析报告" not in md:
        fail("分析报告模板特征缺失（Elliott Wave 分析报告），渲染源可能不是 assets/分析报告_report.md")

    md_name, _html_name = doc_names(name, code, stamp)
    print("[OK] 分析报告渲染完成（剩余图片引用待 embed_report_images.py 注入），输出重定向到标准文件名：", file=sys.stderr)
    print("     " + md_name, file=sys.stderr)
    print("[提示] 请仅捕获 stdout：`> 文件名`，不要加 2>&1——本 [OK]/[NEXT] 走 stderr，加 2>&1 会把日志混进交付文档第一行", file=sys.stderr)
    print("[NEXT] python embed_report_images.py <归档文件夹>", file=sys.stderr)
    sys.stdout.write(md + rc.encode_state(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
