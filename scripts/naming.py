# -*- coding: utf-8 -*-
"""交付文档与图表的标准命名权威（单一出处）。

被 init_archive / gen_report / embed_report_images / ew_chart --out-auto /
smoke_test 共用；各脚本禁止再另写文件名名单、占位符名单或名称校验。
"""
import re

# 4 张标准浪型图（embed_report_images 定位图表/ 目录用；ew_chart --out-auto 同源）
IMAGE_KEYS = (
    ("主方案全景", "主方案_全景.png"),
    ("主方案放大", "主方案_放大.png"),
    ("替代方案全景", "替代方案_全景.png"),
    ("替代方案放大", "替代方案_放大.png"),
)
IMAGE_FILENAMES = tuple(fn for _key, fn in IMAGE_KEYS)
# md 图片引用校验用（带 图表/ 目录前缀，gen_report --md 模式）
CHART_IMAGE_PATHS = tuple("图表/" + fn for fn in IMAGE_FILENAMES)

# 网页占位符：键名 + "图路径"（如 主方案全景 → {{主方案全景图路径}}）
HTML_TOKENS = {key: "{{%s图路径}}" % key for key, _fn in IMAGE_KEYS}
IMAGE_PLACEHOLDERS = {token.strip("{}") for token in HTML_TOKENS.values()}

# ew_chart --out-auto 的方案与图型取值
SCHEME_NAMES = ("主方案", "替代方案")
CHART_VIEWS = ("全景", "放大")

# 交付文档名模板（init_archive 创建、gen_report 校验打印）
REPORT_MD_TPL = "分析报告_%s_%s_%s.md"
WEB_HTML_TPL = "网页报告_%s_%s_%s.html"

# 标的名称/代码白名单：中文/字母/数字/下划线/连字符（堵 .. 与路径分隔符注入）
NAME_RE = re.compile(r"^[0-9A-Za-z_\u4e00-\u9fff-]+$")
BAD_CHARS = r'\\/:*?"<>|'


def validate_component(value, label):
    """标的名称/代码唯一校验器：白名单 + Windows 非法字符/空格双检。
    失败 raise SystemExit("[错误] ...")，调用方（sys.exit(main())）直接透传退出码 1。"""
    value = str(value)
    if not value:
        raise SystemExit("[错误] %s 不能为空" % label)
    bad = [ch for ch in value if ch in BAD_CHARS]
    if bad:
        raise SystemExit("[错误] %s 含 Windows 非法字符: %r" % (label, "".join(set(bad))))
    if re.search(r"\s", value):
        raise SystemExit("[错误] %s 不应含空格: %r" % (label, value))
    if not NAME_RE.fullmatch(value):
        raise SystemExit("[错误] %s 只允许中文/字母/数字/下划线/连字符，收到: %r" % (label, value))
    return value


def doc_names(name, code, stamp):
    """两个交付文档的标准文件名：(分析报告 .md, 网页报告 .html)。"""
    return (REPORT_MD_TPL % (name, code, stamp), WEB_HTML_TPL % (name, code, stamp))


def chart_png(scheme, view):
    """ew_chart --out-auto 的输出文件名（<方案>_<图型>.png）。"""
    return "%s_%s.png" % (scheme, view)
