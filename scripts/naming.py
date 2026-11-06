# -*- coding: utf-8 -*-
"""交付文档与图表的标准命名权威（单一出处）。

被 init_archive / gen_report_md / gen_report_web / embed_report_images / ew_chart --out-auto /
smoke_test 共用；各脚本禁止再另写文件名名单、占位符名单或名称校验。
"""
import re

# 标准浪型图清单（embed_report_images 定位图表/ 目录用；ew_chart --out-auto 同源）。
# 日线全景 2 张为必备核心（单方案防御模式仅主方案）；分钟分形层 6 张成组可选
# （启用分钟分形层时随方案各出 60m/30m/15m 三张，未启用时图位标注"未启用分钟分形层"）。
DAILY_IMAGE_KEYS = (
    ("主方案全景", "主方案_全景.png"),
    ("替代方案全景", "替代方案_全景.png"),
)
MINUTE_IMAGE_KEYS = (
    ("主方案60m", "主方案_60m.png"),
    ("主方案30m", "主方案_30m.png"),
    ("主方案15m", "主方案_15m.png"),
    ("替代方案60m", "替代方案_60m.png"),
    ("替代方案30m", "替代方案_30m.png"),
    ("替代方案15m", "替代方案_15m.png"),
)
IMAGE_KEYS = DAILY_IMAGE_KEYS + MINUTE_IMAGE_KEYS
IMAGE_FILENAMES = tuple(fn for _key, fn in IMAGE_KEYS)
# md 图片引用列表（带 图表/ 目录前缀；embed_report_images 与 md 自包含校验用）
CHART_IMAGE_PATHS = tuple("图表/" + fn for fn in IMAGE_FILENAMES)

# 网页占位符：键名 + "图路径"（如 主方案全景 → {{主方案全景图路径}}）
HTML_TOKENS = {key: "{{%s图路径}}" % key for key, _fn in IMAGE_KEYS}
IMAGE_PLACEHOLDERS = {token.strip("{}") for token in HTML_TOKENS.values()}

# ew_chart --out-auto 的方案与图型取值（日线全景绑定 scope；分钟图型免 scope，浪标签走 --path）
SCHEME_NAMES = ("主方案", "替代方案")
CHART_VIEWS = ("全景", "60m", "30m", "15m")
MINUTE_VIEWS = ("60m", "30m", "15m")

# 交付文档名模板（init_archive 创建、gen_report_md/gen_report_web 打印）
REPORT_MD_TPL = "分析报告_%s_%s_%s.md"
WEB_HTML_TPL = "网页报告_%s_%s_%s.html"

# 归档过程状态目录（D57/D66）：唯一允许写入归档根层的非交付目录
ARCHIVE_TMP_DIR = "临时文件"
ARCHIVE_TMP_MAX_BYTES = 5 * 1024 * 1024

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
