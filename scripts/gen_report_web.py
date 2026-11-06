# -*- coding: utf-8 -*-
"""网页报告生成器（.html）——读 data.json 渲染 assets/网页报告_web_report.html，输出到 stdout。

与 gen_report_md.py 同构；共享 data.json 加载/校验与渲染器在 report_common.py。
本脚本**不写文件**：渲染后内容走 stdout，由 shell 重定向落盘（目标文件名见 init_archive.py 打印）；
2 个图片占位符保留给 embed_report_images.py 注入 base64。

用法：
  python gen_report_web.py --data data.json > "<归档文件夹>/网页报告_<标的>_<代码>_<时间>.html"
生成后仍须运行：python embed_report_images.py <归档文件夹>
"""
import argparse
import os
import re
import sys

import report_common as rc
from naming import IMAGE_PLACEHOLDERS, doc_names


def fail(msg):
    print("[错误] %s" % msg, file=sys.stderr)
    sys.exit(1)


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except AttributeError:
            pass

    p = argparse.ArgumentParser(description="读 data.json 渲染网页报告 .html 到 stdout（本脚本不写文件）")
    p.add_argument("--data", required=True, help="数据 JSON；传 '-' 从 stdin 读")
    args = p.parse_args()

    data = rc.load_data(args.data)
    name, code, stamp = rc.validate(data)
    fields = data["fields"]
    tables = data["tables"]
    jm = data["简明分析说明"]

    script_dir = os.path.dirname(os.path.abspath(__file__))
    tpl_path = rc.template_path(script_dir, "网页报告_web_report.html")
    if not os.path.isfile(tpl_path):
        fail(rc.missing_asset_message(tpl_path, script_dir))
    with open(tpl_path, encoding="utf-8") as f:
        html = f.read()
    rc.check_invalidation_anchor(html, "网页报告模板 %s" % tpl_path)
    if any("{{%s}}" % key not in html for key in ("网页分析前提", "网页主方案", "网页替代方案")):
        fail("网页报告模板缺少精简前提或方案表；请从源文件重新构建并同步安装")

    # 程序生成的 HTML 与用户文本分别传入，避免 JSON 内容进入标记或被再次替换。
    fragments = {}
    for tname, cols in rc.TABLE_FIELDS.items():
        fragments[tname + "表"] = rc.render_html_table(cols, tables[tname])

    # 2) 文本字段 + 简明分析说明 + 标的名称/代码（简明说明换行转 <br>，避免 HTML 折叠成一行）
    mapping = dict(fields)
    mapping.update({"标的名称": name, "标的代码": code,
                    "简明分析说明": rc.render_jianming(jm, data["analysis_scope"])})
    fragments.update({"网页分析前提": rc.render_web_premise(data),
                    "网页主方案": rc.render_web_scheme(data, "主方案"),
                    "网页替代方案": rc.render_web_scheme(data, "替代方案")})
    html = rc.substitute_html(html, mapping, fragments)

    if data["报告模式"] == "单方案防御":
        html = html.replace("<body>", "<body><p>报告模式：单方案防御；原因：" + rc.html_text(data["单方案原因"]) + "</p>")

    # 3) 模板说明文字里的字面 {{表名}} / {{字段名}} 非数据占位符，中和防残留误判
    html = html.replace("{{表名}}", "表名")
    html = html.replace("{{字段名}}", "字段名")

    # 4) 自检：残留占位符（仅允许图片） + 模板特征 + pano-img 结构
    residual = set(re.findall(r"\{\{([^}]+)\}\}", html))
    bad_residual = residual - IMAGE_PLACEHOLDERS
    if bad_residual:
        fail("网页渲染后存在未替换字段: %s" % "、".join(sorted(bad_residual)))
    if "波浪理论网页报告模板" not in html:
        fail("网页模板特征注释缺失，渲染源可能不是 assets/网页报告_web_report.html")
    if html.count('class="pano-img"') != len(IMAGE_PLACEHOLDERS):
        fail("网页 pano-img 结构数应为 %d（主/替代 × 全景/60m/30m/15m），实际 %d"
             % (len(IMAGE_PLACEHOLDERS), html.count('class="pano-img"')))

    print("[OK] 网页渲染完成（剩余图片占位符 %d 个，待 embed_report_images.py 注入），输出重定向到标准文件名："
          % len(residual - IMAGE_PLACEHOLDERS), file=sys.stderr)
    _md_name, html_name = doc_names(name, code, stamp)
    print("     " + html_name, file=sys.stderr)
    print("[提示] 请仅捕获 stdout：`> 文件名`，不要加 2>&1——本 [OK]/[NEXT] 走 stderr，加 2>&1 会把日志混进交付文档第一行", file=sys.stderr)
    print("[NEXT] python embed_report_images.py <归档文件夹>", file=sys.stderr)
    sys.stdout.write(html + rc.encode_state(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
