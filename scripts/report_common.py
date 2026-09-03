# -*- coding: utf-8 -*-
"""报告生成共享层——data.json 加载/校验 + 无副作用的通用渲染器。

单一职责：本模块只做「数据准备 + 纯渲染」，不读具体报表模板、不写出报表——
由 gen_report_md.py（分析报告 .md）与 gen_report_web.py（网页报告 .html）两个入口分别调用。

data.json 模式（顶层键）：
    {
      "标的名称": "...", "标的代码": "...", "时间戳": "YYYYMMDD_HHMM",
      "fields": { <PAGE_FIELDS 中各字符串字段> },
      "tables": { <TABLE_FIELDS> 各表为 list[dict]，键与列头一一对应 },
      "简明分析说明": { "大级别浪": "第4浪", "小级别浪": "第4浪的b浪",
                        "neely得分": 1, "neely强度": "中等", "结论": "偏多",
                        "端点": [ {"价": 1111, "日": "2025-01-01"}, ... ] }  # 末项=终点
    }
"""
import json
import os
import re
import sys

from naming import IMAGE_PLACEHOLDERS, validate_component

# 文本字段（字符串直接替换占位符）；简明分析说明为独立对象，不在此列
PAGE_FIELDS = [
    "分析日期", "分析级别", "收盘价",
    "主方案说明", "主方案失效", "替代方案",
    "概率说明", "概率结论", "交易计划", "风险提示", "更新跟踪",
    "数据来源", "生成时间",
]
# 简明分析说明对象必填键（不含"端点"，端点单独校验为数组）
JIANMING_KEYS = ["大级别浪", "小级别浪", "neely得分", "neely强度", "结论"]
# 表格：表名 → 固定列头
TABLE_FIELDS = {
    "分析前提": ["项", "内容"],
    "主方案数浪": ["浪", "端点", "结构", "说明"],
    "neely参考": ["脚本", "输出", "意义"],
    "八因子": ["因子", "主方案", "替代方案"],
    "失效价位": ["方案", "失效价位", "规则依据", "触发后果"],
}


def fail(msg):
    print("[错误] %s" % msg, file=sys.stderr)
    sys.exit(1)


def load_data(path_or_dash):
    """读取 data.json；'-' 表示从 stdin 读。校验失败 fail()，成功返回顶层 dict。"""
    if path_or_dash == "-":
        try:
            data = json.loads(sys.stdin.read())
        except json.JSONDecodeError as e:
            fail("stdin JSON 解析失败: %s" % e)
    else:
        if not os.path.isfile(path_or_dash):
            fail("数据文件不存在: %s" % path_or_dash)
        with open(path_or_dash, encoding="utf-8-sig") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as e:
                fail("data.json 解析失败: %s" % e)
    if not isinstance(data, dict):
        fail("data.json 顶层应为 JSON 对象")
    return data


def validate(data):
    """校验 data.json 并返回 (名称, 代码, 时间戳)；失败即 fail()。"""
    name = validate_component(data.get("标的名称", ""), "标的名称")
    code = validate_component(data.get("标的代码", ""), "标的代码")
    stamp = str(data.get("时间戳", ""))
    if not re.fullmatch(r"\d{8}_\d{4}", stamp):
        fail("时间戳 格式应为 YYYYMMDD_HHMM，收到: %r" % stamp)

    fields = data.get("fields")
    tables = data.get("tables")
    jm = data.get("简明分析说明")
    if not isinstance(fields, dict):
        fail("data.json 顶层应含 'fields' 对象")
    if not isinstance(tables, dict):
        fail("data.json 顶层应含 'tables' 对象")
    if not isinstance(jm, dict):
        fail("data.json 顶层应含 '简明分析说明' 对象")

    missing = [k for k in PAGE_FIELDS if not str(fields.get(k, "")).strip()]
    if missing:
        fail("data.json 缺少非空文本字段: %s" % "、".join(missing))

    jm_missing = [k for k in JIANMING_KEYS if k not in jm]
    if jm_missing:
        fail("简明分析说明 缺少键: %s" % "、".join(jm_missing))
    endpoints = jm.get("端点")
    if not isinstance(endpoints, list) or not endpoints:
        fail("简明分析说明.端点 应为非空数组（末项=终点）")
    for i, ep in enumerate(endpoints):
        if not isinstance(ep, dict) or "价" not in ep or "日" not in ep:
            fail("简明分析说明.端点 第 %d 项应为 {价, 日}" % (i + 1))

    empty_tables = []
    for tname, cols in TABLE_FIELDS.items():
        rows = tables.get(tname)
        if not isinstance(rows, list) or not rows:
            empty_tables.append(tname)
            continue
        for i, r in enumerate(rows):
            if not isinstance(r, dict):
                fail("%s 表第 %d 行应为对象" % (tname, i + 1))
            bad = [c for c in cols if c not in r]
            if bad:
                fail("%s 表第 %d 行缺列: %s" % (tname, i + 1, "、".join(bad)))
    if empty_tables:
        fail("data.json 表格为空或缺失: %s" % "、".join(empty_tables))

    return name, code, stamp


def render_html_table(cols, rows):
    """生成网页 HTML 表格：<table><thead>…</thead><tbody>…</tbody></table>。"""
    thead = "".join("<th>%s</th>" % c for c in cols)
    body = "".join("<tr>%s</tr>" % "".join("<td>%s</td>" % str(r.get(c, "")) for c in cols)
                   for r in rows)
    return "<table><thead><tr>%s</tr></thead><tbody>%s</tbody></table>" % (thead, body)


def render_md_table(cols, rows):
    """生成 Markdown 表格：| 列头 |…| 与 | --- |…| 与数据行。竖线转义防破坏列。"""
    def esc(v):
        return str(v).replace("|", "\\|").replace("\n", "<br>")
    header = "| " + " | ".join(esc(c) for c in cols) + " |"
    sep = "|" + "|".join([" --- "] * len(cols)) + "|"
    lines = [header, sep]
    for r in rows:
        lines.append("| " + " | ".join(esc(r.get(c, "")) for c in cols) + " |")
    return "\n".join(lines)


def render_jianming(jm):
    """简明分析说明对象 → 4 行文本（日期 YYYY-MM-DD）。"""
    parts = ["%s/%s" % (e["价"], e["日"]) for e in jm["端点"]]
    pts = parts[0]
    for i in range(1, len(parts)):
        pts += ("→" if i == 1 else "-") + parts[i]
    return (
        "主方案：大级别%s，%s（最后一个为终点）\n"
        "小级别：目前处于%s，点位日期和上面一样\n"
        "Neely：得分+%s，%s\n"
        "总结：目前%s"
        % (jm["大级别浪"], pts, jm["小级别浪"], jm["neely得分"], jm["neely强度"], jm["结论"])
    )


def substitute(text, mapping):
    """把 {{key}} 替换为 mapping[key]；未知占位符保留，供各入口做残留校验。"""
    for key, val in mapping.items():
        text = text.replace("{{%s}}" % key, str(val))
    return text
